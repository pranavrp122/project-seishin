"""Tests for the deliver_report_result cache_result flag fix.

Verifies that fallback API calls within follow-up paths do NOT displace
the base report in session_cache.
"""

import asyncio
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# sei_engine.py requires SEI_AUTH_TOKEN or SEI_DEV_MODE at import time
os.environ.setdefault("SEI_DEV_MODE", "1")

from session_cache import SessionCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEI_ENGINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "sei_engine.py"
)


def _make_report(n_rows: int, prefix: str = "row") -> dict:
    """Build a fake report dict with n_rows results."""
    return {
        "summary": "",
        "results": [{"name": f"{prefix}_{i}", "value": i} for i in range(n_rows)],
        "row_count": n_rows,
        "sql": f"SELECT * FROM t LIMIT {n_rows}",
    }


class FakeTask:
    """Minimal stand-in for asyncio.Task with a pre-set result."""

    def __init__(self, result_dict: dict):
        self._result = result_dict

    def result(self):
        return self._result


class FakeWebSocket:
    """Records messages sent via websocket.send()."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, data: str):
        self.sent.append(json.loads(data))


async def _noop_llm(ws, messages, cancel_event):
    return "ok"


async def _noop_tts(ws, text, tts_client, cancel_event):
    pass


# ---------------------------------------------------------------------------
# Import deliver_report_result with heavy deps monkeypatched
# ---------------------------------------------------------------------------

@pytest.fixture
def _patch_sei_engine(monkeypatch):
    """Patch LLM/TTS helpers so deliver_report_result runs without servers."""
    import sei_engine

    monkeypatch.setattr(sei_engine, "handle_llm_response_text_only", _noop_llm)
    monkeypatch.setattr(sei_engine, "tts_full_response", _noop_tts)


@pytest.fixture
def cache():
    return SessionCache(ttl_seconds=300)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_result_true_stores(_patch_sei_engine, cache):
    """Default path: report with results gets stored in session_cache."""
    from sei_engine import deliver_report_result

    ws = FakeWebSocket()
    task = FakeTask(_make_report(16))
    await deliver_report_result(
        ws, task, [], None, query="all suppliers", session_cache=cache, cache_result=True
    )
    assert len(cache.all_reports()) == 1
    assert cache.get_latest()["row_count"] == 16


@pytest.mark.asyncio
async def test_cache_result_false_skips_store(_patch_sei_engine, cache):
    """cache_result=False delivers but does NOT store in session_cache."""
    from sei_engine import deliver_report_result

    ws = FakeWebSocket()
    task = FakeTask(_make_report(3))
    await deliver_report_result(
        ws, task, [], None, query="lowest 3", session_cache=cache, cache_result=False
    )
    # Report was sent to websocket but NOT cached
    assert any(m.get("type") == "report_log" for m in ws.sent)
    assert len(cache.all_reports()) == 0


@pytest.mark.asyncio
async def test_empty_results_never_stored(_patch_sei_engine, cache):
    """Even with cache_result=True, empty results list is not stored."""
    from sei_engine import deliver_report_result

    ws = FakeWebSocket()
    empty_report = {"summary": "", "results": [], "row_count": 0, "sql": "SELECT 1"}
    task = FakeTask(empty_report)
    await deliver_report_result(
        ws, task, [], None, query="nothing", session_cache=cache, cache_result=True
    )
    assert len(cache.all_reports()) == 0


@pytest.mark.asyncio
async def test_base_report_survives_fallback_delivery(_patch_sei_engine, cache):
    """Store a 16-row base, deliver a 3-row fallback with cache_result=False,
    verify session_cache still only contains the 16-row base."""
    from sei_engine import deliver_report_result

    # Pre-populate: the original base report
    cache.store(
        _make_report(16, "supplier"),
        query="all 16 suppliers",
        sql="SELECT * FROM suppliers",
    )
    assert cache.get_latest()["row_count"] == 16

    # Deliver a fallback 3-row result (should NOT be cached)
    ws = FakeWebSocket()
    task = FakeTask(_make_report(3, "top"))
    await deliver_report_result(
        ws, task, [], None, query="lowest 3 lead times",
        session_cache=cache, cache_result=False,
    )

    # Cache still has only the original base report
    assert len(cache.all_reports()) == 1
    latest = cache.get_latest()
    assert latest["row_count"] == 16
    assert latest["query"] == "all 16 suppliers"

    # max row_count across all cached reports is 16
    max_rows = max(r["row_count"] for r in cache.all_reports())
    assert max_rows == 16


def test_all_fallback_sites_set_cache_flag():
    """Static check: every create_task(call_report_api(...)) inside the
    follow_up_on_previous region that fires while cached data exists is
    preceded (within 3 lines) by active_report_cache = False.

    There are 4 total call_report_api sites in the region:
      - 3 fallback sites (error, missing-column, zero-result) that fire when
        a target report exists => MUST set active_report_cache = False
      - 1 cache-expired site (target_report is None) => flag not needed
        because there is no base report to protect
    """
    with open(SEI_ENGINE_PATH) as f:
        lines = f.readlines()

    # Find the follow-up region boundaries
    region_start = None
    region_end = None
    for i, line in enumerate(lines):
        if 'elif intent == "follow_up_on_previous" and session_cache.all_reports()' in line:
            region_start = i
        elif region_start is not None and re.match(r'\s+elif intent ==', line) and i > region_start:
            region_end = i
            break

    assert region_start is not None, "Could not find follow_up_on_previous region start"
    assert region_end is not None, "Could not find follow_up_on_previous region end"

    # Find all create_task(call_report_api(...)) lines in the region
    task_pattern = re.compile(r'asyncio\.create_task\(call_report_api\(')
    flag_pattern = re.compile(r'active_report_cache\s*=\s*False')
    # The cache-expired branch is identifiable by "target_report is None" nearby
    cache_expired_pattern = re.compile(r'target_report is None')

    task_lines = []
    for i in range(region_start, region_end):
        if task_pattern.search(lines[i]):
            task_lines.append(i)

    assert len(task_lines) >= 3, (
        f"Expected at least 3 fallback call_report_api sites, found {len(task_lines)} "
        f"at lines {[l + 1 for l in task_lines]}"
    )

    # Separate cache-expired sites (flag not needed) from real fallback sites
    flagged_count = 0
    cache_expired_count = 0
    for tl in task_lines:
        # Check if this site is inside the "target_report is None" branch
        # by looking 15 lines back for the pattern
        context_window = "".join(lines[max(tl - 15, region_start):tl])
        is_cache_expired = bool(cache_expired_pattern.search(context_window))

        if is_cache_expired:
            # No base report to protect — flag not required
            cache_expired_count += 1
            continue

        # Real fallback: MUST have the flag within 3 preceding lines
        window = "".join(lines[max(tl - 3, region_start):tl])
        assert flag_pattern.search(window), (
            f"Line {tl + 1}: create_task(call_report_api(...)) is NOT preceded "
            f"by 'active_report_cache = False' within 3 lines. "
            f"Window:\n{''.join(lines[max(tl-3, region_start):tl+1])}"
        )
        flagged_count += 1

    assert flagged_count == 3, (
        f"Expected exactly 3 flagged fallback sites, found {flagged_count}"
    )
    assert cache_expired_count >= 1, "Expected at least 1 cache-expired site"
