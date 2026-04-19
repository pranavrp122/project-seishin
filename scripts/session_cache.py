"""Per-session in-memory report cache with TTL and overlap detection.

Exports:
    SessionCache - stores multiple reports keyed by report_id with rows,
                   column metadata, original query, SQL, and timestamp.
"""

import time
import uuid

_MAX_CACHED_REPORTS = 10

_STOP_WORDS = {
    "data", "show", "from", "with", "that", "this", "what", "about",
    "report", "pull", "give", "tell", "into", "some", "more", "just",
    "only", "like", "them", "those", "these",
}


class SessionCache:
    """Per-session in-memory report cache with TTL."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._reports: dict[str, dict] = {}
        self._last_activity: float = time.monotonic()

    def store(self, report_data: dict, query: str, sql: str, kind: str = "base") -> str:
        """Store a report, return its ID.

        kind="base": original data pulls from new_data_request. Follow-up
            operations resolve their target from base reports only.
        kind="derived": fallback API calls inside follow-up paths, op_chain
            outputs, cross-report compare outputs. Kept around so the op_spec
            model can still reference them by id, but never eligible as the
            base-report target for a new follow-up.
        """
        import traceback
        rows_preview = len(report_data.get("results") or report_data.get("rows", []))
        caller = "".join(traceback.format_stack()[-3:-1]).strip().replace("\n", " | ")
        print(f"  [cache.store] kind={kind} query={query!r:.40} rows={rows_preview} caller={caller[-120:]}")
        self._touch()
        self._evict_expired()

        # Enforce max cached reports
        while len(self._reports) >= _MAX_CACHED_REPORTS:
            oldest_id = min(self._reports, key=lambda rid: self._reports[rid]["timestamp"])
            del self._reports[oldest_id]

        report_id = uuid.uuid4().hex[:8]
        rows = report_data.get("results") or report_data.get("rows", [])
        self._reports[report_id] = {
            "report_id": report_id,
            "rows": rows,
            "columns": self._extract_columns(rows),
            "row_count": len(rows),
            "query": query,
            "sql": sql,
            "kind": kind,
            "timestamp": time.monotonic(),
        }
        return report_id

    def get(self, report_id: str) -> dict | None:
        """Get a cached report by ID, or None if expired/missing."""
        self._touch()
        self._evict_expired()
        return self._reports.get(report_id)

    def get_latest(self) -> dict | None:
        """Get most recently stored report."""
        self._touch()
        self._evict_expired()
        if not self._reports:
            return None
        return max(self._reports.values(), key=lambda r: r["timestamp"])

    def all_reports(self) -> list[dict]:
        """All non-expired cached reports."""
        self._touch()
        self._evict_expired()
        return list(self._reports.values())

    def base_reports(self) -> list[dict]:
        """Non-expired reports tagged as base (eligible as follow-up targets)."""
        self._touch()
        self._evict_expired()
        return [r for r in self._reports.values() if r.get("kind", "base") == "base"]

    def get_latest_base(self) -> dict | None:
        """Most recent base report, or None."""
        bases = self.base_reports()
        if not bases:
            return None
        return max(bases, key=lambda r: r["timestamp"])

    def derived_reports(self) -> list[dict]:
        """Non-expired reports tagged as derived."""
        self._touch()
        self._evict_expired()
        return [r for r in self._reports.values() if r.get("kind") == "derived"]

    def get_latest_derived(self) -> dict | None:
        """Most recent derived report, or None."""
        deriveds = self.derived_reports()
        if not deriveds:
            return None
        return max(deriveds, key=lambda r: r["timestamp"])

    def summary(self) -> list[dict]:
        """Compact summary for Gemma context injection. No raw rows."""
        self._touch()
        self._evict_expired()
        return [
            {
                "report_id": r["report_id"],
                "query": r["query"],
                "columns": r["columns"],
                "row_count": r["row_count"],
            }
            for r in self._reports.values()
        ]

    def find_overlapping(self, query_text: str) -> list[dict] | None:
        """Check if any cached report covers similar data (keyword overlap).

        Returns matching reports if 2+ significant words overlap, else None.
        """
        self._touch()
        self._evict_expired()
        if not self._reports:
            return None

        query_words = {
            w for w in query_text.lower().split()
            if len(w) > 3 and w not in _STOP_WORDS
        }
        if not query_words:
            return None

        overlaps = []
        for r in self._reports.values():
            cached_words = {
                w for w in r["query"].lower().split()
                if len(w) > 3 and w not in _STOP_WORDS
            }
            shared = query_words & cached_words
            if len(shared) >= 2:
                overlaps.append(r)

        return overlaps if overlaps else None

    def _touch(self):
        self._last_activity = time.monotonic()

    def _evict_expired(self):
        now = time.monotonic()
        expired = [
            rid for rid, r in self._reports.items()
            if now - r["timestamp"] > self.ttl
        ]
        for rid in expired:
            del self._reports[rid]

    @staticmethod
    def _extract_columns(rows: list[dict]) -> dict[str, str]:
        """Infer column names and types from first row.

        Checks bool BEFORE int since bool is a subclass of int in Python.
        """
        if not rows:
            return {}
        first = rows[0]
        col_types = {}
        for k, v in first.items():
            if isinstance(v, bool):
                col_types[k] = "boolean"
            elif isinstance(v, (int, float)):
                col_types[k] = "number"
            else:
                col_types[k] = "string"
        return col_types
