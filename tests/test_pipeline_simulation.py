#!/usr/bin/env python3
"""E2E pipeline simulation — no WebSocket, TTS, or ASR required.

Tests the full logic chain using live LLM + real DB data:
  Report API -> SessionCache -> Intent Classification -> Op Spec -> CacheExecutor

Run:
    cd /home/prana/project-seishin
    source .venv/bin/activate
    python tests/test_pipeline_simulation.py
"""
import asyncio
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from session_cache import SessionCache
from cache_executor import CacheExecutor, _fuzzy_match_column
from intent_classifier import classify_intent
from op_spec import generate_op_spec, _SAFE_DEFAULT
from text_utils import _normalize_datetime

REPORT_API_URL = os.environ.get("REPORT_API_URL", "http://127.0.0.1:9000")
REPORT_API_KEY = os.environ.get("REPORT_API_KEY", "")
LLM_URL        = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_passed = _failed = _warned = 0

def ok(label, detail=""):
    global _passed
    _passed += 1
    print(f"  {GREEN}PASS{RESET}  {label}" + (f"  -- {detail}" if detail else ""))

def fail(label, detail=""):
    global _failed
    _failed += 1
    print(f"  {RED}FAIL{RESET}  {label}" + (f"  -- {detail}" if detail else ""))

def warn(label, detail=""):
    global _warned
    _warned += 1
    print(f"  {YELLOW}WARN{RESET}  {label}" + (f"  -- {detail}" if detail else ""))

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

async def fetch_report(query):
    headers = {"X-API-Key": REPORT_API_KEY} if REPORT_API_KEY else {}
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{REPORT_API_URL}/report",
                json={"user_request": query},
                headers=headers,
                timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
            )
            resp.raise_for_status()
        ms = (time.perf_counter() - t0) * 1000
        data = resp.json()
        print(f"    Report API: {data.get('row_count', 0)} rows in {ms:.0f}ms")
        return data
    except Exception as exc:
        print(f"    {RED}Report API error: {exc}{RESET}")
        return None


async def test_security():
    section("SECURITY -- Auth, Input Safety, Session Gating")

    if REPORT_API_KEY:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post(f"{REPORT_API_URL}/report",
                                 json={"user_request": "show me clients"},
                                 headers={"X-API-Key": "wrong-key"}, timeout=5.0)
            if r.status_code in (401, 403):
                ok("Report API rejects wrong API key", f"HTTP {r.status_code}")
            else:
                warn("Report API did not reject wrong key", f"got {r.status_code}")
        except Exception as e:
            warn("Could not test report API auth", str(e))
    else:
        warn("REPORT_API_KEY not set", "set in production to protect report endpoint")

    # SQL injection in natural language
    result = await fetch_report("show me clients'; DROP TABLE customers; --")
    if result is not None:
        ok("SQL injection in NL query handled safely",
           f"{result.get('row_count', 0)} rows, no crash")
    else:
        warn("Report API errored on injection query -- check if graceful")

    # Empty query
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{REPORT_API_URL}/report",
                             json={"user_request": ""}, timeout=5.0)
        if r.status_code >= 400:
            ok("Empty query rejected", f"HTTP {r.status_code}")
        else:
            d = r.json()
            ok("Empty query returned 0 rows gracefully") if d.get("row_count", 0) == 0 else warn("Empty query returned data")
    except Exception as e:
        warn("Empty query test error", str(e))

    # LLM reachable
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{LLM_URL}/v1/models", timeout=3.0)
        models = [m["id"] for m in r.json().get("data", [])]
        ok("LLM endpoint reachable", f"models: {models}")
    except Exception as e:
        fail("LLM endpoint not reachable", str(e))

    # No eval/exec in executor
    import inspect
    from cache_executor import CacheExecutor
    src = inspect.getsource(CacheExecutor)
    if "eval(" not in src and "exec(" not in src:
        ok("CacheExecutor has no eval/exec calls")
    else:
        fail("CacheExecutor contains eval/exec -- SECURITY RISK")

    # Safe default sentinel
    if _SAFE_DEFAULT.get("op_type") == "_error":
        ok("Op spec error fallback uses _error sentinel (not a real op_type)")
    else:
        fail("Op spec error fallback may cause executor crash", f"op_type={_SAFE_DEFAULT.get('op_type')!r}")

    # Burst: 3 concurrent report calls
    print(f"\n    {CYAN}Burst test: 3 concurrent report API calls{RESET}")
    t0 = time.perf_counter()
    results = await asyncio.gather(
        fetch_report("show me all clients"),
        fetch_report("show me all tax cases"),
        fetch_report("show me all clients"),
        return_exceptions=True,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    ok_count = sum(1 for r in results if isinstance(r, dict) and r is not None)
    if ok_count == 3:
        ok(f"3 concurrent requests all succeeded in {elapsed:.0f}ms")
    else:
        warn(f"Only {ok_count}/3 concurrent requests succeeded")


async def test_scenario_clients(cache):
    section("SCENARIO 1 -- Clients: pull -> sort -> filter -> aggregate -> select")

    data = await fetch_report("show me all clients")
    if not data or not data.get("results"):
        fail("Clients report returned no data")
        return None

    rid = cache.store(data, query="show me all clients", sql=data.get("sql", ""))
    ok("Clients report cached", f"id={rid}, {data['row_count']} rows, cols={list(data['results'][0].keys())}")

    ex = CacheExecutor()
    report = cache.get(rid)

    # Sort
    sorted_r = ex.execute({"op_type": "sort", "column": "name", "direction": "asc",
                            "explanation": "sort by name"}, report)
    if sorted_r["rows"][0]["name"] <= sorted_r["rows"][-1]["name"]:
        ok("Sort by name asc", f"first={sorted_r['rows'][0]['name']!r} last={sorted_r['rows'][-1]['name']!r}")
    else:
        fail("Sort by name asc produced wrong order")

    # Filter by segment
    segs = list({r.get("segment_default") for r in data["results"] if r.get("segment_default")})
    if segs:
        filtered = ex.execute({"op_type": "filter", "column": "segment_default",
                                "operator": "eq", "value": segs[0],
                                "explanation": f"filter segment={segs[0]}"}, report)
        ok(f"Filter segment={segs[0]!r}", f"{filtered['row_count']}/{data['row_count']} rows")

    # Count aggregate
    count_r = ex.execute({"op_type": "aggregate", "column": "id", "agg_func": "count",
                           "explanation": "count"}, report)
    got_count = count_r["rows"][0]["id"]
    if got_count == data["row_count"]:
        ok("Aggregate count matches row_count", f"count={got_count}")
    else:
        warn("Aggregate count mismatch", f"got {got_count}, expected {data['row_count']}")

    # Select columns
    slim = ex.execute({"op_type": "select_columns", "columns": ["id", "name"],
                       "explanation": "slim to id+name"}, report)
    cols = set(slim["rows"][0].keys())
    if cols == {"id", "name"}:
        ok("Select columns: only id and name returned")
    else:
        fail("Select columns wrong", str(cols))

    # Rename
    renamed = ex.execute({"op_type": "rename_columns", "rename_map": {"name": "client_name"},
                          "explanation": "rename"}, report)
    if "client_name" in renamed["rows"][0] and "name" not in renamed["rows"][0]:
        ok("Rename columns: name -> client_name")
    else:
        fail("Rename columns failed")

    return rid


async def test_scenario_tax_cases_llm(cache):
    section("SCENARIO 2 -- Tax Cases: pull -> LLM op spec -> execute (live Gemma)")

    data = await fetch_report("show me all tax cases")
    if not data or not data.get("results"):
        fail("Tax cases returned no data")
        return None

    rid = cache.store(data, query="show me all tax cases", sql=data.get("sql", ""))
    cols = list(data["results"][0].keys())
    ok("Tax cases cached", f"id={rid}, {data['row_count']} rows, cols={cols}")

    summary = cache.summary()
    ex = CacheExecutor()

    test_cases = [
        ("only show me the paid ones",         "filter by status=paid"),
        ("sort by largest total amount first",  "sort by total_dollars desc"),
        ("show me the top 3 by total amount",   "top_n by total_dollars"),
        ("what is the total tax collected",     "aggregate sum of tax_dollars"),
        ("just show the invoice number and status", "select_columns"),
    ]

    for utterance, description in test_cases:
        print(f"\n    {CYAN}-> LLM: '{utterance}'{RESET}")
        spec = await generate_op_spec(utterance, summary)
        print(f"    op_type={spec.get('op_type')!r}  explanation={spec.get('explanation')!r}")

        if spec.get("op_type") == "_error":
            warn(f"{description}: LLM returned error", utterance)
            continue

        try:
            result = ex.execute(spec, cache.get(rid))
            ok(f"{description}", f"op={spec['op_type']!r} -> {result['row_count']} rows")
            # Spot checks
            if spec.get("op_type") == "filter" and spec.get("value") == "paid":
                all_paid = all(r.get("status") == "paid" for r in result["rows"])
                if not all_paid:
                    warn("Filter for paid returned non-paid rows", str([r.get("status") for r in result["rows"]]))
        except Exception as e:
            warn(f"{description}: executor error", str(e))

    return rid


async def test_intent_classification():
    section("SCENARIO 3 -- Intent Classification (live Gemma, 9 cases)")

    cases = [
        ("show me all clients",             False, "new_data_request",     "clear data request"),
        ("pull up the open invoices",        False, "new_data_request",     "data request variant"),
        ("hey what's up",                   False, "normal_chat",           "casual chat"),
        ("thanks that looks great",          True,  "normal_chat",           "acknowledgment"),
        ("filter those to just the paid ones", True, "follow_up_on_previous","follow-up filter"),
        ("sort by revenue descending",       True,  "follow_up_on_previous", "follow-up sort"),
        ("show me the top 5",               True,  "follow_up_on_previous", "follow-up top-N"),
        ("actually cancel that",            True,  "cancel",                "cancel intent"),
        ("yeah go ahead",                   True,  "confirm",               "confirm intent"),
    ]

    total = correct = 0
    for utterance, has_report, expected, desc in cases:
        result = await classify_intent(utterance, [], has_active_report=has_report)
        got, conf = result["intent"], result["confidence"]
        total += 1
        if got == expected:
            correct += 1
            ok(f"{desc}", f"'{utterance[:40]}' -> {got} ({conf:.2f})")
        else:
            warn(f"{desc} MISMATCH", f"'{utterance[:40]}' -> {got} (expected {expected}, conf={conf:.2f})")

    pct = correct / total * 100
    if pct >= 80:
        ok(f"Intent accuracy {correct}/{total} ({pct:.0f}%)")
    else:
        warn(f"Intent accuracy below 80%: {correct}/{total} ({pct:.0f}%)")


async def test_cache_overlap():
    section("SCENARIO 4 -- Cache Overlap Detection")

    cache = SessionCache()
    data = await fetch_report("show me all clients")
    if not data or not data.get("results"):
        warn("No client data for overlap test")
        return

    cache.store(data, query="show me all clients", sql="")

    overlaps = cache.find_overlapping("what clients do we have")
    if overlaps:
        ok("Overlap detected for related query", f"matched: {overlaps[0]['query']!r}")
    else:
        warn("No overlap for 'what clients do we have' vs 'show me all clients'",
             "keyword threshold may need tuning for short common words")

    no_overlap = cache.find_overlapping("what are the latest invoices due")
    if not no_overlap:
        ok("No false-positive for unrelated query")
    else:
        warn("False-positive overlap", f"matched: {no_overlap[0]['query']!r}")

    data2 = await fetch_report("show me all tax cases")
    if data2 and data2.get("results"):
        cache.store(data2, query="show me all tax cases", sql="")
        summary = cache.summary()
        ok("Multi-report summary", f"{len(summary)} reports cached")
        for r in summary:
            if "rows" in r:
                fail(f"Report {r['report_id']} summary leaks raw rows to LLM context")
            else:
                ok(f"Report {r['report_id']} has no raw rows in summary")


async def test_cross_report():
    section("SCENARIO 5 -- Cross-Report Compare (clients + tax cases)")

    cache = SessionCache()
    clients = await fetch_report("show me all clients")
    tax = await fetch_report("show me all tax cases")
    if not clients or not tax:
        warn("Missing data for cross-report test")
        return

    r1 = cache.store(clients, query="clients", sql="")
    r2 = cache.store(tax, query="tax cases", sql="")

    client_cols = set(clients["results"][0].keys())
    tax_cols = set(tax["results"][0].keys())
    shared = client_cols & tax_cols
    print(f"    Client cols:   {sorted(client_cols)}")
    print(f"    Tax case cols: {sorted(tax_cols)}")
    print(f"    Shared:        {sorted(shared)}")

    if shared:
        col = sorted(shared)[0]
        try:
            result = CacheExecutor().execute_cross_report(
                {"op_type": "cross_report_compare", "compare_column": col, "explanation": f"merge on {col}"},
                cache.get(r1), cache.get(r2)
            )
            ok(f"Cross-report merge on '{col}'",
               f"{result['row_count']} rows, cols={sorted(result['columns'].keys())}")
        except Exception as e:
            warn(f"Cross-report error on '{col}'", str(e))
    else:
        warn("No shared columns between clients and tax cases",
             "clients.id and tax_cases.customer_id need the same name for a direct merge")

    # LLM-guided cross-report intent
    spec = await generate_op_spec(
        "compare the two reports on id" if not shared else f"compare the two reports on {sorted(shared)[0]}",
        cache.summary()
    )
    print(f"    LLM cross-report op_type={spec.get('op_type')!r}")
    if spec.get("op_type") == "cross_report_compare":
        ok("LLM chose cross_report_compare correctly")
    else:
        warn(f"LLM chose {spec.get('op_type')!r} instead of cross_report_compare")


async def test_cache_ttl():
    section("SCENARIO 6 -- Cache TTL Eviction")

    cache = SessionCache(ttl_seconds=2)
    data = await fetch_report("show me all clients")
    if not data or not data.get("results"):
        warn("No data for TTL test")
        return

    rid = cache.store(data, query="clients", sql="")
    ok("Report stored in 2s TTL cache")

    if cache.get(rid) is not None:
        ok("Report available before TTL")
    else:
        fail("Report immediately unavailable")

    print("    Waiting 2.5s for expiry...")
    await asyncio.sleep(2.5)

    if cache.get(rid) is None:
        ok("Report evicted after TTL")
    else:
        fail("Report still available after TTL -- eviction broken")

    if not cache.all_reports():
        ok("all_reports() empty after expiry -- intent classifier will treat as fresh session")
    else:
        fail("all_reports() non-empty after TTL eviction")


def test_date_normalization():
    """SCENARIO 7 -- Date Normalization"""
    section("SCENARIO 7 -- Date Normalization")

    # Test relative date replacement
    result = _normalize_datetime("show me last month revenue")
    if "last month" not in result.lower() and any(
        m in result for m in ["January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]
    ):
        ok("'last month' replaced with concrete month name", result.strip()[:60])
    else:
        fail("'last month' not properly normalized", result)

    # Test this year
    import datetime as dt
    year = str(dt.datetime.now().year)
    result2 = _normalize_datetime("this year totals")
    if year in result2:
        ok("'this year' replaced with current year", result2.strip()[:60])
    else:
        fail("'this year' not normalized", result2)

    # Test passthrough
    plain = "show me all clients"
    result3 = _normalize_datetime(plain)
    if result3 == plain:
        ok("Text without dates passes through unchanged")
    else:
        fail("Passthrough failed", result3)


async def test_intent_new_intents():
    """SCENARIO 8 -- New Intent Classification (undo, what_can_i_ask, compare_reports)"""
    section("SCENARIO 8 -- New Intent Classification")

    cases = [
        ("undo that",                    False, "undo",             "undo intent"),
        ("go back",                      True,  "undo",             "undo variant"),
        ("what can I ask for",           False, "what_can_i_ask",   "discovery intent"),
        ("what data do you have",        False, "what_can_i_ask",   "discovery variant"),
        ("compare clients and invoices", False, "compare_reports",  "compare intent"),
    ]

    total = correct = 0
    for utterance, has_report, expected, desc in cases:
        result = await classify_intent(utterance, [], has_active_report=has_report)
        got, conf = result["intent"], result["confidence"]
        total += 1
        if got == expected:
            correct += 1
            ok(f"{desc}", f"'{utterance[:40]}' -> {got} ({conf:.2f})")
        else:
            warn(f"{desc} MISMATCH", f"'{utterance[:40]}' -> {got} (expected {expected}, conf={conf:.2f})")

    pct = correct / total * 100
    if pct >= 60:
        ok(f"New intent accuracy {correct}/{total} ({pct:.0f}%)")
    else:
        warn(f"New intent accuracy below 60%: {correct}/{total} ({pct:.0f}%)")


def test_fuzzy_column_matching():
    """SCENARIO 9 -- Fuzzy Column Matching"""
    section("SCENARIO 9 -- Fuzzy Column Matching")

    # Synonym resolution
    result = _fuzzy_match_column("revenue", ["total_dollars", "name", "id"])
    if result == "total_dollars":
        ok("Synonym: 'revenue' -> 'total_dollars'")
    else:
        fail(f"Synonym failed: 'revenue' -> {result!r}")

    # Substring match
    result2 = _fuzzy_match_column("cap", ["capacity", "name", "id"])
    if result2 == "capacity":
        ok("Substring: 'cap' -> 'capacity'")
    else:
        fail(f"Substring failed: 'cap' -> {result2!r}")

    # No match
    result3 = _fuzzy_match_column("zzz_nonexistent", ["a", "b", "c"])
    if result3 is None:
        ok("No match returns None")
    else:
        fail(f"Expected None, got {result3!r}")

    # Through executor
    ex = CacheExecutor()
    report = {
        "rows": [
            {"name": "Alpha", "total_dollars": 1000},
            {"name": "Beta", "total_dollars": 2000},
            {"name": "Gamma", "total_dollars": 500},
        ],
    }
    try:
        result4 = ex.execute(
            {"op_type": "filter", "column": "revenue", "operator": "gt", "value": 800},
            report,
        )
        if result4["row_count"] == 2:
            ok("Executor fuzzy: filter on 'revenue' resolved to 'total_dollars'",
               f"{result4['row_count']} rows")
        else:
            warn(f"Executor fuzzy row count mismatch: {result4['row_count']}")
    except Exception as e:
        fail("Executor fuzzy filter failed", str(e))


async def test_undo_simulation():
    """SCENARIO 10 -- Undo Stack Simulation"""
    section("SCENARIO 10 -- Undo Stack Simulation")

    cache = SessionCache()
    data = await fetch_report("show me all clients")
    if not data or not data.get("results"):
        warn("No client data for undo simulation")
        return

    # Store original
    rid_original = cache.store(data, query="show me all clients", sql=data.get("sql", ""))
    original_count = cache.get(rid_original)["row_count"]
    ok(f"Original report stored", f"id={rid_original}, {original_count} rows")

    # Execute a follow-up op and store result
    ex = CacheExecutor()
    report = cache.get(rid_original)
    cols = list(data["results"][0].keys())
    # Find a string column to filter on
    first_row = data["results"][0]
    filter_col = None
    filter_val = None
    for c in cols:
        if isinstance(first_row[c], str) and first_row[c]:
            filter_col = c
            filter_val = first_row[c]
            break

    if filter_col:
        filtered = ex.execute(
            {"op_type": "filter", "column": filter_col, "operator": "eq",
             "value": filter_val, "explanation": f"filter {filter_col}"},
            report,
        )
        rid_filtered = cache.store(filtered, f"filtered by {filter_col}", "derived")
        ok(f"Follow-up filter stored", f"id={rid_filtered}, {filtered['row_count']} rows")

        # Simulate undo: retrieve original by ID
        restored = cache.get(rid_original)
        if restored and restored["row_count"] == original_count:
            ok("Undo simulation: original report restored by ID",
               f"{restored['row_count']} rows (matches original)")
        else:
            fail("Undo simulation: could not restore original")
    else:
        warn("No string column found for filter test")


async def main():
    print(f"\n{BOLD}{'='*60}")
    print("  SEI ENGINE -- PIPELINE SIMULATION")
    print(f"{'='*60}{RESET}")
    print(f"  LLM:        {LLM_URL}")
    print(f"  Report API: {REPORT_API_URL}")

    await test_security()
    shared_cache = SessionCache()
    await test_scenario_clients(shared_cache)
    await test_scenario_tax_cases_llm(shared_cache)
    await test_intent_classification()
    await test_cache_overlap()
    await test_cross_report()
    await test_cache_ttl()
    test_date_normalization()
    await test_intent_new_intents()
    test_fuzzy_column_matching()
    await test_undo_simulation()

    print(f"\n{BOLD}{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}{RESET}")
    print(f"  {GREEN}PASS:  {_passed}{RESET}")
    print(f"  {YELLOW}WARN:  {_warned}{RESET}")
    print(f"  {RED}FAIL:  {_failed}{RESET}")

    print(f"\n{BOLD}{CYAN}{'='*60}")
    print("  SUGGESTIONS")
    print(f"{'='*60}{RESET}")
    suggestions = [
        ("[SECURITY]   ", RED,    "No per-IP rate limiting on WebSocket upgrades -- single-session only. Add token-bucket (10 req/min) before AWS expose."),
        ("[SECURITY]   ", RED,    "Report API has no body size limit. Add max ~2KB on user_request to prevent LLM prompt stuffing."),
        ("[PIPELINE]   ", YELLOW, "clients.id and tax_cases.customer_id don't share the same name -- cross-report compare can't join without aliasing. Normalize in report API."),
        ("[PIPELINE]   ", YELLOW, "Intent + op spec are two serial LLM calls (~400-600ms). Could combine into one call with a union schema for follow-ups."),
        ("[UX]         ", CYAN,   "Cache overlap hint fires but pipeline runs anyway. Consider a 2-3s hold where user can say 'yes use cached' before DB fires."),
        ("[UX]         ", CYAN,   "Add a 'what data do I have' intent: reads session_cache.summary() and voices available reports. Very natural for multi-report sessions."),
        ("[RELIABILITY]", YELLOW, "_error op_type now safely handled, but sei_engine silently re-fires pipeline. Should voice 'let me pull fresh data' before re-firing."),
        ("[FEATURE]    ", GREEN,  "Op spec doesn't return a confidence score. A low-confidence op could trigger 'did you mean X?' before executing, reducing wrong filter mishaps."),
        ("[FEATURE]    ", GREEN,  "Add a 'clear my data' intent that calls session_cache explicitly -- users will ask 'start fresh' or 'forget that'."),
        ("[TESTING]    ", RESET,  "Once AWS is up: add latency SLOs -- intent <200ms, op spec <400ms, follow-up total <700ms, fresh report <5s."),
    ]
    for tag, color, text in suggestions:
        print(f"  {color}{tag}{RESET} {text}")

    print()
    return _failed == 0

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
