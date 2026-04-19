"""Unit tests for JsonFileBackend persistence (D-20-09)."""

import json
import os
import stat
import time

import pytest
from session_cache import (
    SessionCache,
    JsonFileBackend,
    PersistenceBackend,
    DebouncedSaver,
    SEI_DATA_DIR,
    atomic_write_json,
    serialize_cache,
    deserialize_into_cache,
)


@pytest.fixture
def backend(tmp_path):
    """JsonFileBackend with path redirected to tmp_path for isolation."""
    b = JsonFileBackend()
    b.path = tmp_path / "memory.json"
    return b


@pytest.fixture
def cache():
    return SessionCache(ttl_seconds=600)


class TestJsonFileBackend:
    """Core save/load/clear behavior."""

    def test_load_missing_file_returns_empty(self, backend):
        assert backend.load() == {}

    def test_save_load_roundtrip(self, backend):
        state = {"version": 1, "reports": {"abc": {"query": "test"}}}
        backend.save(state)
        loaded = backend.load()
        assert loaded == state

    def test_clear_removes_file(self, backend):
        backend.save({"version": 1, "reports": {}})
        assert backend.path.exists()
        backend.clear()
        assert not backend.path.exists()

    def test_clear_on_missing_file_no_error(self, backend):
        backend.clear()  # should not raise

    def test_file_permissions_0600(self, backend):
        backend.save({"version": 1, "reports": {}})
        mode = stat.S_IMODE(os.stat(backend.path).st_mode)
        assert mode == 0o600

    def test_no_tmp_file_leftover(self, backend):
        backend.save({"version": 1, "reports": {}})
        parent_files = list(backend.path.parent.iterdir())
        # Only memory.json should exist, no .tmp files
        assert all(not f.suffix == ".tmp" for f in parent_files)


class TestAtomicWriteJson:
    """Atomic write creates parent dirs and sets permissions."""

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "memory.json"
        atomic_write_json(nested, {"test": True})
        assert nested.exists()

    def test_permissions_applied(self, tmp_path):
        path = tmp_path / "test.json"
        atomic_write_json(path, {"test": True}, mode=0o600)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600


class TestSerializeCache:
    """Metadata-only serialization with timestamp conversion."""

    def test_version_tag(self, cache):
        serialized = serialize_cache(cache)
        assert serialized["version"] == 1

    def test_empty_cache_serializes(self, cache):
        serialized = serialize_cache(cache)
        assert serialized["reports"] == {}

    def test_metadata_only_no_rows(self, cache):
        cache.store(
            {"results": [{"col1": "val1"}, {"col1": "val2"}]},
            query="test query",
            sql="SELECT 1",
            kind="base",
        )
        serialized = serialize_cache(cache)
        for rid, meta in serialized["reports"].items():
            assert "rows" not in meta
            assert meta["row_count"] == 2
            assert meta["query"] == "test query"
            assert meta["sql"] == "SELECT 1"

    def test_timestamp_converted_to_epoch(self, cache):
        cache.store(
            {"results": [{"a": 1}]},
            query="q",
            sql="s",
        )
        serialized = serialize_cache(cache)
        for rid, meta in serialized["reports"].items():
            ts = meta["timestamp"]
            # Epoch timestamps are large (> 1_000_000_000 for dates after 2001)
            assert ts > 1_000_000_000, f"Timestamp {ts} looks like monotonic, not epoch"

    def test_columns_serialized_as_list(self, cache):
        cache.store(
            {"results": [{"name": "a", "age": 1}]},
            query="q",
            sql="s",
        )
        serialized = serialize_cache(cache)
        for rid, meta in serialized["reports"].items():
            # Columns should be a list of column names (not the dict with types)
            assert isinstance(meta["columns"], list)
            assert "name" in meta["columns"]
            assert "age" in meta["columns"]


class TestDeserializeIntoCache:
    """Rehydration from serialized state."""

    def test_roundtrip_preserves_metadata(self, cache):
        cache.store(
            {"results": [{"x": 1}]},
            query="my query",
            sql="SELECT x",
            kind="base",
            origin_op="fetch",
        )
        serialized = serialize_cache(cache)

        new_cache = SessionCache(ttl_seconds=600)
        deserialize_into_cache(serialized, new_cache)

        reports = new_cache.all_reports()
        assert len(reports) == 1
        r = reports[0]
        assert r["query"] == "my query"
        assert r["sql"] == "SELECT x"
        assert r["kind"] == "base"

    def test_loaded_timestamps_use_current_monotonic(self, cache):
        cache.store({"results": [{"a": 1}]}, query="q", sql="s")
        serialized = serialize_cache(cache)

        new_cache = SessionCache(ttl_seconds=600)
        before = time.monotonic()
        deserialize_into_cache(serialized, new_cache)
        after = time.monotonic()

        reports = new_cache.all_reports()
        assert len(reports) == 1
        ts = reports[0]["timestamp"]
        assert before <= ts <= after, "Loaded timestamp should be current monotonic"


class TestSizeBound:
    """5MB limit drops oldest non-base reports."""

    def test_size_bound_enforced(self, backend):
        # Create a large state that exceeds 5MB
        big_reports = {}
        for i in range(500):
            big_reports[f"report_{i}"] = {
                "report_id": f"report_{i}",
                "query": "x" * 10000,
                "sql": "y" * 10000,
                "kind": "derived" if i > 0 else "base",
                "parent_report_id": None,
                "origin_op": "fetch",
                "timestamp": time.time() + i,
                "semantic_key": "",
                "columns": ["a", "b"],
                "row_count": 10,
            }
        state = {"version": 1, "reports": big_reports}
        raw_size = len(json.dumps(state, default=str))
        assert raw_size > 5_000_000, f"Test data too small: {raw_size}"

        # Save should enforce size bound
        backend.save(state)
        loaded = backend.load()
        loaded_size = len(json.dumps(loaded, default=str))
        assert loaded_size <= 5_000_000, f"Saved file too large: {loaded_size}"
        # Base report should be preserved
        assert any(
            r.get("kind") == "base" for r in loaded["reports"].values()
        )


class TestDebouncedSaver:
    """Dirty-flag + single-timer pattern."""

    def test_debounced_saver_exists(self):
        """DebouncedSaver can be instantiated."""
        backend = JsonFileBackend()
        saver = DebouncedSaver(backend, delay=2.0)
        assert saver._delay == 2.0


class TestAttachPersistence:
    """SessionCache.attach_persistence wires DebouncedSaver."""

    def test_attach_creates_saver(self, backend):
        cache = SessionCache()
        cache.attach_persistence(backend)
        assert cache._debounced_saver is not None
        assert cache._persistence_backend is backend
