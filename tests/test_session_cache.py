"""Scarce-case unit tests for SessionCache."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from session_cache import SessionCache


def _make_report(rows=None, key="results"):
    """Helper to build report_data dicts."""
    if rows is None:
        rows = [
            {"name": "Alice", "age": 30, "active": True},
            {"name": "Bob", "age": 25, "active": False},
        ]
    return {key: rows}


class TestStoreAndRetrieve:
    def test_store_and_retrieve(self):
        cache = SessionCache()
        rid = cache.store(_make_report(), "show users", "SELECT * FROM users")
        report = cache.get(rid)
        assert report is not None
        assert report["report_id"] == rid
        assert report["query"] == "show users"
        assert report["sql"] == "SELECT * FROM users"
        assert report["row_count"] == 2
        assert len(report["rows"]) == 2
        assert "name" in report["columns"]
        assert "timestamp" in report

    def test_store_multiple_reports(self):
        cache = SessionCache()
        ids = set()
        for i in range(3):
            rid = cache.store(
                _make_report([{"x": i}]), f"query {i}", f"SQL {i}"
            )
            ids.add(rid)
        assert len(ids) == 3
        assert len(cache.all_reports()) == 3

    def test_get_latest(self):
        cache = SessionCache()
        cache.store(_make_report([{"x": 1}]), "first", "sql1")
        cache.store(_make_report([{"x": 2}]), "second", "sql2")
        latest = cache.get_latest()
        assert latest is not None
        assert latest["query"] == "second"

    def test_get_missing_id(self):
        cache = SessionCache()
        assert cache.get("nonexistent") is None


class TestSummary:
    def test_summary_excludes_rows(self):
        cache = SessionCache()
        cache.store(_make_report(), "test query", "sql")
        summaries = cache.summary()
        assert len(summaries) == 1
        s = summaries[0]
        assert "rows" not in s
        assert "report_id" in s
        assert "query" in s
        assert "columns" in s
        assert "row_count" in s


class TestEmptyCache:
    def test_empty_cache(self):
        cache = SessionCache()
        assert cache.all_reports() == []
        assert cache.get_latest() is None
        assert cache.summary() == []


class TestEdgeCases:
    def test_single_row_report(self):
        cache = SessionCache()
        rid = cache.store(
            _make_report([{"name": "Solo", "val": 42}]), "one row", "sql"
        )
        report = cache.get(rid)
        assert report["row_count"] == 1
        assert report["columns"] == {"name": "string", "val": "number"}

    def test_empty_rows_report(self):
        cache = SessionCache()
        rid = cache.store({"results": []}, "empty", "sql")
        report = cache.get(rid)
        assert report["row_count"] == 0
        assert report["columns"] == {}

    def test_ttl_expiry(self):
        cache = SessionCache(ttl_seconds=1)
        rid = cache.store(_make_report(), "expiring", "sql")
        assert cache.get(rid) is not None
        time.sleep(1.5)
        assert cache.get(rid) is None

    def test_column_type_inference(self):
        rows = [{"i": 10, "f": 3.14, "b": True, "s": "hello"}]
        cache = SessionCache()
        rid = cache.store({"results": rows}, "types", "sql")
        cols = cache.get(rid)["columns"]
        assert cols["i"] == "number"
        assert cols["f"] == "number"
        assert cols["b"] == "boolean"  # bool before int
        assert cols["s"] == "string"

    def test_max_reports_cap(self):
        cache = SessionCache()
        for i in range(11):
            cache.store(_make_report([{"x": i}]), f"q{i}", f"s{i}")
        assert len(cache.all_reports()) == 10

    def test_store_accepts_rows_key(self):
        """Store report with 'rows' key format (executor output)."""
        cache = SessionCache()
        rid = cache.store({"rows": [{"a": 1}]}, "rows key", "sql")
        report = cache.get(rid)
        assert report["row_count"] == 1
        assert report["rows"] == [{"a": 1}]


class TestOverlapDetection:
    def test_overlap_detection_match(self):
        cache = SessionCache()
        cache.store(
            _make_report(), "warehouse capacity data analysis", "sql"
        )
        result = cache.find_overlapping("what's the warehouse capacity breakdown")
        assert result is not None
        assert len(result) >= 1

    def test_overlap_detection_no_match(self):
        cache = SessionCache()
        cache.store(_make_report(), "warehouse capacity data", "sql")
        result = cache.find_overlapping("customer order history")
        assert result is None

    def test_overlap_stopword_filtering(self):
        """Queries sharing only stopwords/short words should not overlap."""
        cache = SessionCache()
        cache.store(_make_report(), "show data from report", "sql")
        # "show data from table" shares only stopwords/short words
        result = cache.find_overlapping("show data from table")
        assert result is None


class TestUndoStackSimulation:
    """Simulate the undo pattern: store original -> execute op -> store result -> verify original retrievable."""

    def test_undo_stack_push_pop(self):
        """Store 3 follow-up ops, verify each pre-op report is still retrievable by ID."""
        cache = SessionCache()
        # Original report
        rid0 = cache.store(
            _make_report([{"name": "Alpha", "val": 100}, {"name": "Beta", "val": 200}]),
            "original query", "sql0"
        )
        # Simulate 3 follow-up ops storing results
        rid1 = cache.store(_make_report([{"name": "Alpha", "val": 100}]), "follow-up 1", "sql1")
        rid2 = cache.store(_make_report([{"name": "Beta", "val": 200}]), "follow-up 2", "sql2")
        rid3 = cache.store(_make_report([{"name": "Alpha", "val": 100}]), "follow-up 3", "sql3")

        # All pre-op reports still retrievable (simulating undo)
        assert cache.get(rid0) is not None
        assert cache.get(rid0)["query"] == "original query"
        assert cache.get(rid1) is not None
        assert cache.get(rid2) is not None
        assert cache.get(rid3) is not None

    def test_undo_stack_cap_at_five(self):
        """Simulate undo stack capped at 5 entries."""
        undo_stack = []
        max_undo = 5
        for i in range(6):
            undo_stack.append(f"report_{i}")
            if len(undo_stack) > max_undo:
                undo_stack.pop(0)
        assert len(undo_stack) == 5
        assert undo_stack[0] == "report_1"  # oldest (report_0) dropped
        assert undo_stack[-1] == "report_5"

    def test_undo_expired_report(self):
        """Store a report with short TTL, verify undo fails gracefully after expiry."""
        cache = SessionCache(ttl_seconds=1)
        rid_original = cache.store(
            _make_report([{"name": "Original", "val": 1}]),
            "original", "sql"
        )
        rid_followup = cache.store(
            _make_report([{"name": "FollowUp", "val": 2}]),
            "follow-up", "sql"
        )
        # Both available immediately
        assert cache.get(rid_original) is not None
        assert cache.get(rid_followup) is not None

        # Wait for expiry
        time.sleep(1.5)

        # After TTL, undo should fail (original expired)
        assert cache.get(rid_original) is None
        assert cache.get(rid_followup) is None
