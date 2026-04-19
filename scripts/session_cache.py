"""Per-session in-memory report cache with TTL, lineage, and SessionMemory facade.

Exports:
    SessionCache  - storage engine: stores reports with lineage metadata,
                    derived-first eviction, compact summaries.
    SessionMemory - facade: record/resolve_target/summary_for_context/lineage/list.
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
    """Per-session in-memory report cache with TTL and lineage metadata."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._reports: dict[str, dict] = {}
        self._last_activity: float = time.monotonic()

    def store(
        self,
        report_data: dict,
        query: str,
        sql: str,
        kind: str = "base",
        parent_report_id: str | None = None,
        origin_op: str = "fetch",
        topic: str = "",
        derivation_summary: str = "",
    ) -> str:
        """Store a report with full lineage metadata, return its ID.

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

        # Enforce max cached reports — evict derived before base, oldest first
        while len(self._reports) >= _MAX_CACHED_REPORTS:
            # Sort by (is_base, timestamp): derived (False=0) evicts before base (True=1),
            # oldest timestamp evicts first within each group
            evict_id = min(
                self._reports,
                key=lambda rid: (
                    self._reports[rid].get("kind") == "base",
                    self._reports[rid]["timestamp"],
                ),
            )
            del self._reports[evict_id]

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
            "parent_report_id": parent_report_id,
            "origin_op": origin_op,
            "topic": topic,
            "derivation_summary": derivation_summary,
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
        """Compact one-line-per-report summary for context injection (D-08).

        No raw rows, no columns dict. Returns kind, topic, age, derivation_summary.
        """
        self._touch()
        self._evict_expired()
        now = time.monotonic()
        return [
            {
                "report_id": r["report_id"],
                "kind": r.get("kind", "base"),
                "topic": r.get("topic", ""),
                "row_count": r["row_count"],
                "age_seconds": round(now - r["timestamp"], 1),
                "derivation_summary": r.get("derivation_summary", ""),
                "query": r["query"][:80],
            }
            for r in self._reports.values()
        ]

    def lineage(self, report_id: str) -> list[dict]:
        """Walk parent_report_id chain from report up to the root base.

        Returns [child, ..., base]. Empty list if report not found.
        """
        self._touch()
        self._evict_expired()
        chain = []
        visited = set()
        current_id = report_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            report = self._reports.get(current_id)
            if report is None:
                break
            chain.append(report)
            current_id = report.get("parent_report_id")
        return chain

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


class SessionMemory:
    """Facade over SessionCache providing lineage-aware storage and LLM-driven target resolution.

    This is the universal public API (D-13) that all callers should use.
    """

    def __init__(self, cache: SessionCache):
        self._cache = cache

    def record(
        self,
        report_data: dict,
        *,
        kind: str = "base",
        parent_id: str | None = None,
        origin_op: str = "fetch",
        topic: str = "",
        query: str = "",
        sql: str = "",
        derivation_summary: str = "",
    ) -> str:
        """Store a report with full lineage metadata. Returns report_id."""
        report_id = self._cache.store(
            report_data,
            query=query,
            sql=sql,
            kind=kind,
            parent_report_id=parent_id,
            origin_op=origin_op,
            topic=topic,
            derivation_summary=derivation_summary,
        )
        rows = report_data.get("results") or report_data.get("rows", [])
        print(f"  [memory.store] kind={kind} origin_op={origin_op} parent={parent_id} rows={len(rows)}")
        return report_id

    async def resolve_target(self, user_text: str) -> dict | None:
        """LLM-driven target resolution across all cached reports (D-04/D-05/D-06).

        Returns the resolved target report dict, or None if cache is empty.
        """
        from intent_classifier import classify_followup_target
        import time as _time

        all_cached = self._cache.all_reports()
        if not all_cached:
            return None
        if len(all_cached) == 1:
            r = all_cached[0]
            print(f"  [memory.resolve] target={r['report_id']} kind={r.get('kind')} conf=1.0 reason=only_report")
            return r

        now = _time.monotonic()
        report_list = sorted(all_cached, key=lambda r: r.get("timestamp", 0), reverse=True)
        classifier_input = [
            {
                "report_id": r["report_id"],
                "query": r.get("query", ""),
                "kind": r.get("kind", "base"),
                "row_count": r.get("row_count", 0),
                "age_seconds": max(0.0, now - r.get("timestamp", now)),
                "derivation_summary": r.get("derivation_summary", ""),
            }
            for r in report_list[:10]
        ]
        decision = await classify_followup_target(user_text, classifier_input)

        chosen_id = decision.get("report_id", "")
        chosen = self._cache.get(chosen_id)
        # D-06: If LLM hallucinated an invalid id, fall back deterministically
        if chosen is None:
            latest_base = self._cache.get_latest_base()
            chosen = latest_base or (all_cached[0] if all_cached else None)
            fallback_id = chosen["report_id"] if chosen else "None"
            fallback_kind = chosen.get("kind") if chosen else "-"
            print(f"  [memory.resolve] target={fallback_id} kind={fallback_kind} conf=0.0 reason=fallback_invalid_id")
        else:
            conf = decision.get("confidence", 0)
            reason = decision.get("reason", "")
            print(f"  [memory.resolve] target={chosen_id} kind={chosen.get('kind')} conf={conf:.2f} reason={reason[:60]}")
        return chosen

    def summary_for_context(self) -> list[dict]:
        """Compact one-line-per-report summary for Gemma context (D-08)."""
        return self._cache.summary()

    def lineage(self, report_id: str) -> list[dict]:
        """Ancestor chain from report up to base (D-02)."""
        return self._cache.lineage(report_id)

    async def check_compatible_base(self, user_text: str) -> dict | None:
        """D-18: Check if a compatible live base report exists for a new data request.

        Uses a lightweight LLM call to determine if an existing cached base
        can answer the user's question without a fresh API call.
        Returns the compatible base report if found, None otherwise.
        """
        import time as _time
        from intent_classifier import classify_followup_target

        bases = self._cache.base_reports()
        if not bases:
            return None

        now = _time.monotonic()
        report_list = sorted(bases, key=lambda r: r.get("timestamp", 0), reverse=True)
        classifier_input = [
            {
                "report_id": r["report_id"],
                "query": r.get("query", ""),
                "kind": "base",
                "row_count": r.get("row_count", 0),
                "age_seconds": max(0.0, now - r.get("timestamp", now)),
                "topic": r.get("topic", ""),
            }
            for r in report_list[:5]
        ]

        decision = await classify_followup_target(user_text, classifier_input)

        if decision.get("confidence", 0) >= 0.7:
            matched = self._cache.get(decision.get("report_id", ""))
            if matched:
                print(f"  [memory.reuse] D-18 base reuse: {matched['report_id']} "
                      f"rows={matched['row_count']} for '{user_text[:50]}'")
                return matched

        return None

    def list(self, kind: str | None = None, topic: str | None = None) -> list[dict]:
        """List cached reports with optional filters."""
        reports = self._cache.all_reports()
        if kind:
            reports = [r for r in reports if r.get("kind") == kind]
        if topic:
            reports = [r for r in reports if topic.lower() in r.get("topic", "").lower()]
        return reports
