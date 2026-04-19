"""Per-session in-memory report cache with TTL, lineage, and SessionMemory facade.

Exports:
    SessionCache  - storage engine: stores reports with lineage metadata,
                    derived-first eviction, compact summaries.
    SessionMemory - facade: record/resolve_target/summary_for_context/lineage/list.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Protocol

_MAX_CACHED_REPORTS = 20

_STOP_WORDS = {
    "data", "show", "from", "with", "that", "this", "what", "about",
    "report", "pull", "give", "tell", "into", "some", "more", "just",
    "only", "like", "them", "those", "these",
}

import re as _re

# Filler words that don't carry topic meaning. Kept minimal; tokens surviving this
# filter should be the semantic nouns/adjectives that identify what the user wants.
_SEMANTIC_STOP_WORDS = {
    "the", "a", "an", "our", "all", "me", "you", "can", "could", "would",
    "please", "get", "pull", "show", "tell", "give", "grab", "fetch", "find",
    "about", "on", "for", "of", "to", "some", "any", "every", "also",
    "data", "info", "information", "stuff", "things",
}

# Simple English plural/singular trim: drops trailing "s"/"es" so "supplier" ≡ "suppliers".
# Not linguistically rigorous but good enough for short business nouns.
_PLURAL_RE = _re.compile(r"(es|s)$")


def _normalize_tokens(query: str) -> frozenset[str]:
    tokens = []
    for raw in query.lower().split():
        t = _re.sub(r"[^\w]", "", raw)
        if not t or t in _SEMANTIC_STOP_WORDS:
            continue
        stem = _PLURAL_RE.sub("", t) if len(t) > 4 else t
        tokens.append(stem)
    return frozenset(tokens)


def _semantic_key(query: str) -> str:
    # Stable string form of the normalized token set, for storage alongside reports.
    return " ".join(sorted(_normalize_tokens(query)))


class SessionCache:
    """Per-session in-memory report cache with TTL and lineage metadata."""

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._reports: dict[str, dict] = {}
        self._last_activity: float = time.monotonic()
        self._cap: int = _MAX_CACHED_REPORTS
        self._persistence_backend: PersistenceBackend | None = None
        self._debounced_saver: DebouncedSaver | None = None

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

        # Enforce max cached reports — only evict derived, never base
        while len(self._reports) >= self._cap:
            derived_ids = [
                rid for rid, r in self._reports.items()
                if r.get("kind") != "base"
            ]
            if not derived_ids:
                # All base — grow cap instead of evicting
                self._cap += 5
                print(f"  [memory.cap_grow] new_cap={self._cap}")
                break
            evict_id = min(derived_ids, key=lambda rid: self._reports[rid]["timestamp"])
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
            "semantic_key": _semantic_key(query) if kind == "base" else "",
        }
        if self._debounced_saver is not None:
            self._debounced_saver.mark_dirty(lambda: serialize_cache(self))
        return report_id

    def _import_with_id(self, report_id: str, meta: dict, now: float) -> None:
        """Import a persisted report preserving its original ID (WR-03)."""
        self._reports[report_id] = {
            "report_id": report_id,
            "rows": [],
            "columns": meta.get("columns", []),
            "row_count": meta.get("row_count", 0),
            "query": meta.get("query", ""),
            "sql": meta.get("sql", ""),
            "kind": meta.get("kind", "base"),
            "parent_report_id": meta.get("parent_report_id"),
            "origin_op": meta.get("origin_op", "fetch"),
            "topic": meta.get("topic", ""),
            "derivation_summary": meta.get("derivation_summary", ""),
            "timestamp": now,
            "semantic_key": meta.get("semantic_key", ""),
        }

    def get(self, report_id: str) -> dict | None:
        """Get a cached report by ID, or None if expired/missing."""
        self._touch()
        self._evict_expired()
        report = self._reports.get(report_id)
        if report is not None:
            report["timestamp"] = time.monotonic()
        return report

    def get_latest(self) -> dict | None:
        """Get most recently stored report."""
        self._touch()
        self._evict_expired()
        if not self._reports:
            return None
        report = max(self._reports.values(), key=lambda r: r["timestamp"])
        report["timestamp"] = time.monotonic()
        return report

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
        report = max(bases, key=lambda r: r["timestamp"])
        report["timestamp"] = time.monotonic()
        return report

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

    def attach_persistence(self, backend: PersistenceBackend, delay: float = 2.0) -> None:
        """Wire a persistence backend with debounced saving on store()."""
        self._persistence_backend = backend
        self._debounced_saver = DebouncedSaver(backend, delay=delay)

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

    async def resolve_target(self, user_text: str, op_context: dict | None = None, history: list[dict] | None = None) -> dict | None:
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
                "columns": r.get("columns", {}),
            }
            for r in report_list[:10]
        ]
        decision = await classify_followup_target(user_text, classifier_input, op_context=op_context, history=history)

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
            if chosen is not None:
                chosen["_resolve_confidence"] = conf
        if chosen is not None:
            chosen["timestamp"] = time.monotonic()
        return chosen

    def summary_for_context(self) -> list[dict]:
        """Compact one-line-per-report summary for Gemma context (D-08)."""
        return self._cache.summary()

    def lineage(self, report_id: str) -> list[dict]:
        """Ancestor chain from report up to base (D-02)."""
        return self._cache.lineage(report_id)

    def find_semantic_duplicate(self, query: str) -> dict | None:
        """Fast zero-LLM check: does a cached base cover this query's topic tokens?

        Matches when the cached base's token set is a subset of the query's tokens,
        or vice versa. Both directions handle rephrases: a terse new query
        ("get suppliers") should reuse a richer cached base ("all supplier data"),
        and a richer new query ("pull up the full supplier listing") should reuse
        a terser cached one ("suppliers").
        """
        q_tokens = _normalize_tokens(query)
        if not q_tokens:
            return None
        best = None
        best_overlap = 0
        for r in self._cache.base_reports():
            r_key = r.get("semantic_key", "")
            r_tokens = frozenset(r_key.split()) if r_key else frozenset()
            if not r_tokens:
                continue
            overlap = len(q_tokens & r_tokens)
            if overlap == 0:
                continue
            # Subset in either direction is a strong match.
            if q_tokens <= r_tokens or r_tokens <= q_tokens:
                if overlap > best_overlap:
                    best = r
                    best_overlap = overlap
        if best is not None:
            best["timestamp"] = time.monotonic()
            print(f"  [memory.semantic_dedup] matched {best['report_id']} overlap={best_overlap} for {query!r:.40}")
            return best
        return None

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


# ---------------------------------------------------------------------------
# Persistence layer (D-20-09)
# ---------------------------------------------------------------------------

SEI_DATA_DIR = Path.home() / ".sei"


class PersistenceBackend(Protocol):
    """Abstract persistence contract for session memory."""

    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...
    def clear(self) -> None: ...


def atomic_write_json(path: Path, data: dict, mode: int = 0o600) -> None:
    """Write JSON atomically: temp file in same dir + os.replace(). Sets permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, default=str)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)


_METADATA_FIELDS = (
    "report_id", "query", "sql", "kind", "parent_report_id",
    "origin_op", "timestamp", "semantic_key", "columns", "row_count",
)


class JsonFileBackend:
    """File-based persistence at ~/.sei/memory.json with atomic writes and 0600 perms."""

    def __init__(self) -> None:
        self.path: Path = SEI_DATA_DIR / "memory.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"[persistence] Corrupt memory.json, resetting: {exc}")
            return {}

    def save(self, state: dict) -> None:
        # Enforce 5MB size bound before writing
        raw = json.dumps(state, default=str)
        if len(raw) > 5_000_000:
            state = _enforce_size_bound(state)
        atomic_write_json(self.path, state)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def _enforce_size_bound(state: dict) -> dict:
    """Drop oldest non-base reports until serialized JSON is under 5MB."""
    reports = dict(state.get("reports", {}))
    while True:
        # Check for non-base reports before expensive serialization (WR-04)
        non_base = [
            (rid, r) for rid, r in reports.items()
            if r.get("kind") != "base"
        ]
        if not non_base:
            break  # Only base reports left, cannot trim further
        raw = json.dumps({"version": state.get("version", 1), "reports": reports}, default=str)
        if len(raw) <= 5_000_000:
            break
        # Find oldest non-base report
        oldest_rid = min(non_base, key=lambda x: x[1].get("timestamp", 0))[0]
        del reports[oldest_rid]
    return {"version": state.get("version", 1), "reports": reports}


def serialize_cache(cache: SessionCache) -> dict:
    """Serialize a SessionCache to a persistence-ready dict (metadata only).

    Converts time.monotonic() timestamps to time.time() epoch values.
    Columns are serialized as a list of names (not the type-inference dict).
    """
    now_mono = time.monotonic()
    now_epoch = time.time()
    reports = {}
    for rid, report in cache._reports.items():
        meta = {}
        for field in _METADATA_FIELDS:
            val = report.get(field)
            if field == "timestamp" and val is not None:
                # Convert monotonic offset to epoch
                offset = now_mono - val
                meta["timestamp"] = now_epoch - offset
            elif field == "columns":
                # Store column names as a list, not the {name: type} dict
                cols = val
                if isinstance(cols, dict):
                    meta["columns"] = list(cols.keys())
                elif isinstance(cols, list):
                    meta["columns"] = cols
                else:
                    meta["columns"] = []
            else:
                meta[field] = val
        reports[rid] = meta
    return {"version": 1, "reports": reports}


def deserialize_into_cache(data: dict, cache: SessionCache) -> None:
    """Rehydrate a SessionCache from a persisted dict.

    Sets all loaded report timestamps to current time.monotonic() so TTL
    works correctly from load time (Pitfall 1: monotonic resets on reboot).
    """
    reports = data.get("reports", {})
    now = time.monotonic()
    for rid, meta in reports.items():
        # Import with original ID preserved to maintain parent_report_id lineage (WR-03)
        cache._import_with_id(rid, meta, now)


class DebouncedSaver:
    """Debounce persistence writes by N seconds after last cache mutation.

    Uses dirty-flag + single-pending-timer pattern (Pitfall 2).
    state_fn is called at save time for fresh state.
    """

    def __init__(self, backend: PersistenceBackend, delay: float = 2.0) -> None:
        self._backend = backend
        self._delay = delay
        self._handle: asyncio.TimerHandle | None = None
        self._dirty = False
        self._state_fn = None

    def mark_dirty(self, state_fn) -> None:
        """Schedule a save. state_fn() called at save time for fresh state."""
        self._dirty = True
        self._state_fn = state_fn
        if self._handle is not None:
            self._handle.cancel()
        try:
            loop = asyncio.get_running_loop()
            self._handle = loop.call_later(self._delay, self._fire)
        except RuntimeError:
            # No running event loop (e.g. in sync tests) -- save immediately
            self._fire()

    def _fire(self) -> None:
        if self._dirty and self._state_fn is not None:
            self._backend.save(self._state_fn())
            self._dirty = False
            self._handle = None
