"""End-to-end scenario test for the follow-up base/derived cache fix.

Reproduces the exact store() call sequence sei_engine produces during the
bug scenario, then runs the target-resolution logic and asserts the 16-row
base report — not a 3-row derived — is the target.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from session_cache import SessionCache


def _resolve_followup_target(session_cache: SessionCache, op_spec_report_id: str | None = None):
    """Mirror of base-first target resolution in sei_engine.py follow_up_on_previous."""
    bases = session_cache.base_reports()
    all_cached = session_cache.all_reports()
    explicit = session_cache.get(op_spec_report_id) if op_spec_report_id else None
    return (
        explicit
        or session_cache.get_latest_base()
        or (max(bases, key=lambda r: r.get("row_count", 0)) if bases else None)
        or session_cache.get_latest()
    )


def _rows(n, prefix="row"):
    return [{"name": f"{prefix}{i}", "rating": i, "lead_time": i * 2} for i in range(n)]


def test_scenario_missing_col_fallback_does_not_displace_base():
    """Bug scenario: base 16 rows -> derived 3 rows (fallback) -> target should still be base."""
    cache = SessionCache()
    base_id = cache.store({"results": _rows(16, "sup")}, query="get all suppliers", sql="SELECT ...", kind="base")
    cache.store({"results": _rows(3, "sup_top3")}, query="which 3 lowest lead times", sql="", kind="derived")

    target = _resolve_followup_target(cache, op_spec_report_id=None)
    assert target is not None
    assert target["row_count"] == 16
    assert target["report_id"] == base_id
    assert target["kind"] == "base"


def test_scenario_multiple_base_reports_latest_wins():
    """Two topic bases (suppliers then invoices) — latest base wins; ignores old derived."""
    cache = SessionCache()
    cache.store({"results": _rows(16, "sup")}, query="all suppliers", sql="", kind="base")
    invoice_id = cache.store({"results": _rows(3, "inv")}, query="all invoices", sql="", kind="base")
    cache.store({"results": _rows(2, "sup_sub")}, query="top 2 suppliers", sql="", kind="derived")

    target = _resolve_followup_target(cache, op_spec_report_id=None)
    assert target["report_id"] == invoice_id
    assert target["kind"] == "base"


def test_explicit_report_id_honored_even_if_derived():
    """User explicitly references the derived report -> op_spec.report_id wins."""
    cache = SessionCache()
    cache.store({"results": _rows(16, "sup")}, query="all suppliers", sql="", kind="base")
    derived_id = cache.store({"results": _rows(3, "top3")}, query="top 3", sql="", kind="derived")

    target = _resolve_followup_target(cache, op_spec_report_id=derived_id)
    assert target["report_id"] == derived_id
    assert target["kind"] == "derived"


def test_no_base_falls_back_to_any_report():
    """Only derived reports exist -> resolution still returns something (edge case)."""
    cache = SessionCache()
    d_id = cache.store({"results": _rows(3)}, query="q", sql="", kind="derived")
    target = _resolve_followup_target(cache, op_spec_report_id=None)
    assert target is not None
    assert target["report_id"] == d_id


def test_deliver_report_result_accepts_cache_kind():
    """Engine's deliver_report_result must accept cache_kind param with default 'base'."""
    import inspect
    os.environ.setdefault("SEI_DEV_MODE", "1")
    import sei_engine
    sig = inspect.signature(sei_engine.deliver_report_result)
    assert "cache_kind" in sig.parameters
    assert sig.parameters["cache_kind"].default == "base"


def test_all_fallback_sites_tag_derived():
    """Static regression guard: every call_report_api inside follow_up_on_previous
    is either preceded by active_report_kind='derived' or is the cache-expired
    path (target_report is None) which legitimately becomes a new base."""
    import re
    with open(os.path.join(os.path.dirname(__file__), "..", "scripts", "sei_engine.py")) as f:
        src = f.read()

    start = src.index('elif intent == "follow_up_on_previous" and session_cache.all_reports()')
    end_match = re.search(
        r'\n                elif intent == "follow_up_on_previous" and not session_cache\.all_reports',
        src[start:],
    )
    assert end_match, "couldn't find end of follow_up_on_previous region"
    region = src[start : start + end_match.start()]

    lines = region.split("\n")
    spawn_idxs = [i for i, ln in enumerate(lines) if "asyncio.create_task(call_report_api(" in ln]
    assert len(spawn_idxs) >= 3, f"expected >=3 fallback sites, got {len(spawn_idxs)}"

    for i in spawn_idxs:
        # Widen: walk back up to 25 lines looking for either the derived tag
        # (fallback displaces nothing) or the cache-expired guard (legit new base).
        window = "\n".join(lines[max(0, i - 25) : i + 1])
        assert (
            'active_report_kind = "derived"' in window
            or "if target_report is None" in window
        ), f"fallback site at region line {i} missing derived tag or cache-expired guard:\n{window}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
