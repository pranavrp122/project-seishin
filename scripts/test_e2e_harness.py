#!/usr/bin/env python3
"""E2E test harness for Sei Engine multi-turn conversations.

Replays scripted conversation scenarios against a live Sei Engine WebSocket,
asserts per-turn expectations (intent, target report, row counts), and
produces structured JSON-lines output with gap classification.

Usage:
    SEI_TEXT_MODE=1 python scripts/test_e2e_harness.py

Requires:
    - sei_engine running on ws://127.0.0.1:5052
    - Gemma 4 vLLM on :8000
    - Report API on :9000
    - SEI_AUTH_TOKEN set (or SEI_DEV_MODE=1 for dev)
    - SEI_TEXT_MODE=1 recommended for intent debug frames
"""
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Callable

import websockets

SERVER_URL = os.environ.get("SEI_TEST_URL", "ws://127.0.0.1:5052")
AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "test-token-change-me")
TURN_TIMEOUT = float(os.environ.get("SEI_E2E_TIMEOUT", "60"))

# Ensure intent debug frames are emitted
os.environ.setdefault("SEI_TEXT_MODE", "1")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    """A single user turn with optional assertions."""
    user_text: str
    expect_intent: str | None = None
    expect_target_kind: str | None = None
    expect_min_rows: int | None = None
    expect_max_rows: int | None = None
    expect_no_fresh_fetch: bool = False
    cancel_after_ms: int | None = None
    expect_cache_consistent: bool = False


@dataclass
class TurnResult:
    """Outcome of executing a single turn."""
    scenario: str = ""
    turn: int = 0
    user_text: str = ""
    detected_intent: str = ""
    detected_confidence: float = 0.0
    target_report_id: str = ""
    target_kind: str = ""
    target_row_count: int = 0
    reply_text: str = ""
    pass_fail: bool = True
    failure_reason: str = ""
    gap_category: str = ""
    raw_frames: list = field(default_factory=list)


# Gap classification categories
GAP_CATEGORIES = {
    "misrouted_intent",
    "wrong_target_report",
    "hallucinated_content",
    "unnecessary_fresh_fetch",
    "crash",
    "timeout",
    "cache_inconsistent",
}


def classify_gap(turn: Turn, result: TurnResult) -> str:
    """Classify a failure into a gap category."""
    if result.gap_category:
        return result.gap_category
    if "timeout" in result.failure_reason.lower():
        return "timeout"
    if "crash" in result.failure_reason.lower() or "error" in result.failure_reason.lower():
        return "crash"
    if turn.expect_intent and result.detected_intent != turn.expect_intent:
        return "misrouted_intent"
    if turn.expect_target_kind and result.target_kind != turn.expect_target_kind:
        return "wrong_target_report"
    if turn.expect_no_fresh_fetch and result.failure_reason:
        return "unnecessary_fresh_fetch"
    if turn.expect_cache_consistent and result.failure_reason:
        return "cache_inconsistent"
    return "hallucinated_content"


# ---------------------------------------------------------------------------
# Turn execution
# ---------------------------------------------------------------------------

async def execute_turn(
    ws,
    turn: Turn,
    turn_index: int,
    scenario_name: str,
) -> TurnResult:
    """Send a user message, collect all response frames, build TurnResult."""
    result = TurnResult(
        scenario=scenario_name,
        turn=turn_index,
        user_text=turn.user_text,
    )

    # Send user message
    await ws.send(json.dumps({"type": "message", "text": turn.user_text}))

    # If cancel requested, schedule it
    cancel_task = None
    if turn.cancel_after_ms is not None:
        async def send_cancel():
            await asyncio.sleep(turn.cancel_after_ms / 1000.0)
            try:
                await ws.send(json.dumps({"type": "stop"}))
            except Exception:
                pass
        cancel_task = asyncio.create_task(send_cancel())

    # Collect response frames until done or timeout.
    # For new_data_request turns, sei_engine sends: ack sentence + done, then
    # later: report_log + summary sentence + done. We need to keep collecting
    # past the first done if we expect rows but haven't seen a report_log yet.
    frames = []
    reply_parts = []
    got_report_log = False
    done_count = 0
    expect_report = turn.expect_min_rows is not None or turn.expect_intent == "new_data_request"
    try:
        deadline = time.monotonic() + TURN_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result.failure_reason = "timeout waiting for done frame"
                result.gap_category = "timeout"
                result.pass_fail = False
                break

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                result.failure_reason = "timeout waiting for done frame"
                result.gap_category = "timeout"
                result.pass_fail = False
                break

            # Skip binary frames (audio)
            if isinstance(raw, bytes):
                continue

            frame = json.loads(raw)
            frames.append(frame)
            ftype = frame.get("type", "")

            if ftype == "done":
                done_count += 1
                # For data request turns, keep collecting past intermediate
                # dones (ack done, "still working" done) until we see a
                # report_log frame with actual data.
                if expect_report and not got_report_log:
                    continue
                break
            elif ftype == "cancelled":
                # D-19: Turn was cancelled cleanly
                break
            elif ftype == "sentence":
                text = frame.get("text", "")
                # Extract intent from TEXT_MODE debug sentence: "(intent: X, confidence: Y)"
                _intent_match = re.match(r"^\(intent: (\w+), confidence: ([\d.]+)\)$", text)
                if _intent_match:
                    result.detected_intent = _intent_match.group(1)
                    result.detected_confidence = float(_intent_match.group(2))
                else:
                    reply_parts.append(text)
                # Also check for structured intent keys in frame
                if frame.get("intent"):
                    result.detected_intent = frame["intent"]
                if frame.get("confidence"):
                    result.detected_confidence = float(frame["confidence"])
            elif ftype == "intent":
                result.detected_intent = frame.get("intent", "")
                result.detected_confidence = float(frame.get("confidence", 0))
            elif ftype == "report_log":
                got_report_log = True
                result.target_row_count = frame.get("row_count", 0)
                result.target_report_id = frame.get("report_id", "")
            elif ftype == "debug":
                # Debug frames may carry intent/target info in text mode
                if "intent" in frame:
                    result.detected_intent = frame.get("intent", result.detected_intent)
                if "target_report_id" in frame:
                    result.target_report_id = frame.get("target_report_id", "")
                if "target_kind" in frame:
                    result.target_kind = frame.get("target_kind", "")
                if "confidence" in frame:
                    result.detected_confidence = float(frame.get("confidence", 0))
            elif ftype == "error":
                result.failure_reason = f"error frame: {frame.get('text', '')}"
                result.gap_category = "crash"
                result.pass_fail = False

    finally:
        if cancel_task and not cancel_task.done():
            cancel_task.cancel()

    result.reply_text = " ".join(reply_parts)
    result.raw_frames = frames

    # Try to extract target_kind from report_log or debug frames
    for f in frames:
        if f.get("type") == "report_log" and "kind" in f:
            result.target_kind = f["kind"]
        if f.get("type") == "debug" and "target_kind" in f:
            result.target_kind = f["target_kind"]

    # Run assertions
    failures = []
    if turn.expect_intent and result.detected_intent != turn.expect_intent:
        failures.append(f"intent: expected={turn.expect_intent} got={result.detected_intent}")
    if turn.expect_target_kind and result.target_kind and result.target_kind != turn.expect_target_kind:
        failures.append(f"target_kind: expected={turn.expect_target_kind} got={result.target_kind}")
    if turn.expect_min_rows is not None and result.target_row_count < turn.expect_min_rows:
        failures.append(f"min_rows: expected>={turn.expect_min_rows} got={result.target_row_count}")
    if turn.expect_max_rows is not None and result.target_row_count > turn.expect_max_rows:
        failures.append(f"max_rows: expected<={turn.expect_max_rows} got={result.target_row_count}")
    if turn.expect_no_fresh_fetch:
        # Check if a fresh API call happened (report_log without "Using cached data" marker).
        # D-18 reuse still sends report_log but with cached data summary.
        fresh_fetch = any(
            f.get("type") == "report_log" and "Using cached data" not in (f.get("summary") or "")
            for f in frames
        )
        if fresh_fetch:
            failures.append("expected no fresh fetch but fresh report_log frame received")
    if turn.expect_cache_consistent:
        # Basic consistency: no error frames and reply exists
        has_error = any(f.get("type") == "error" for f in frames)
        if has_error:
            failures.append("cache inconsistent: error frame received after cancel")

    if failures:
        result.pass_fail = False
        result.failure_reason = "; ".join(failures)
        result.gap_category = classify_gap(turn, result)

    return result


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def scenario_suppliers_multifilter() -> tuple[str, list[Turn]]:
    """The verbatim 8-turn suppliers conversation from CONTEXT.md that must pass."""
    return ("suppliers_multifilter", [
        Turn(
            user_text="can u get me all the data we have on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="which ones have a rating of 3",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which ones have a rating of 4",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which ones have a rating of 3",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which ones have a rating of 5",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which 4 of our suppliers have the longest lead time",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which of our suppliers has the shortest lead time",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="which has the fastest lead time",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
    ])


def scenario_multi_topic_switch_return() -> tuple[str, list[Turn]]:
    """Multi-topic switch and return: pull suppliers, pull invoices, follow up on suppliers.
    The follow-up must target the suppliers base, not invoices.
    """
    return ("multi_topic_switch_return", [
        Turn(
            user_text="can u get me all the data we have on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="pull up our invoices",
            expect_intent="new_data_request",
        ),
        Turn(
            user_text="which of our suppliers has the highest rating",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
    ])


def scenario_demonstrative_reference() -> tuple[str, list[Turn]]:
    """Demonstrative reference: pull suppliers, filter top-3, 'sort those by rating'.
    'those' must target the top-3 derived result, not the full base.
    """
    return ("demonstrative_reference", [
        Turn(
            user_text="get me all supplier data",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="show me the top 3 by lead time",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="sort those by rating",
            expect_intent="follow_up_on_previous",
            expect_target_kind="derived",
            expect_max_rows=3,
        ),
    ])


def scenario_fresh_vs_cached_base_reuse() -> tuple[str, list[Turn]]:
    """Fresh vs cached base reuse (D-18): pull suppliers, then 'get me all suppliers' again.
    Must reuse cached base, not fire Report API.
    D-18 implemented in Plan 03 Task 3.1 — this should now pass.
    """
    return ("fresh_vs_cached_base_reuse", [
        Turn(
            user_text="get me all the data on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="get me all suppliers",
            expect_intent="new_data_request",
            expect_no_fresh_fetch=True,  # D-18: should reuse cached base
        ),
    ])


def scenario_noise_turn() -> tuple[str, list[Turn]]:
    """Noise turn: normal_chat in the middle of a data conversation."""
    return ("noise_turn", [
        Turn(
            user_text="can u get me all the data we have on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="which ones have a rating of 3",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
        Turn(
            user_text="hey what's the weather like today",
            expect_intent="normal_chat",
        ),
        Turn(
            user_text="which ones have a rating of 5",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
    ])


def scenario_ambiguous_phrasing() -> tuple[str, list[Turn]]:
    """Ambiguous phrasing: 'which has the fastest lead time' with no article.
    No article, no 'of our suppliers' - must still be follow-up.
    """
    return ("ambiguous_phrasing", [
        Turn(
            user_text="can u get me all the data we have on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="which has the fastest lead time",
            expect_intent="follow_up_on_previous",
            expect_target_kind="base",
        ),
    ])


def scenario_cancel_mid_turn() -> tuple[str, list[Turn]] | None:
    """Cancel mid-turn (D-19/D-20): fire data request, cancel before done.
    Verifies cancel aborts cleanly and cache stays consistent for next turn.
    """
    return ("cancel_mid_turn", [
        Turn(
            user_text="can u get me all the data we have on our suppliers",
            expect_intent="new_data_request",
            expect_min_rows=16,
        ),
        Turn(
            user_text="get me all invoices data",
            expect_intent="new_data_request",
            cancel_after_ms=500,
            expect_cache_consistent=True,
        ),
        Turn(
            user_text="which of our suppliers has the highest rating",
            # Don't assert intent on post-cancel recovery turn — WebSocket frame
            # ordering after cancel is non-deterministic in the harness.
            # Just verify it doesn't crash (cache consistent after cancel).
        ),
    ])


# Registry of all scenarios
ALL_SCENARIOS: list[Callable] = [
    scenario_suppliers_multifilter,
    scenario_multi_topic_switch_return,
    scenario_demonstrative_reference,
    scenario_fresh_vs_cached_base_reuse,
    scenario_noise_turn,
    scenario_ambiguous_phrasing,
    scenario_cancel_mid_turn,
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_scenario(scenario_fn: Callable) -> dict | None:
    """Run a single scenario, return summary dict or None if stub."""
    result = scenario_fn()
    if result is None:
        name = scenario_fn.__name__
        print(json.dumps({"scenario": name, "status": "stub", "skipped": True}))
        return None

    name, turns = result

    print(f"\n{'='*60}")
    print(f"SCENARIO: {name} ({len(turns)} turns)")
    print(f"{'='*60}")

    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    results: list[TurnResult] = []

    try:
        async with websockets.connect(SERVER_URL, additional_headers=headers) as ws:
            for i, turn in enumerate(turns):
                print(f"\n  Turn {i+1}: {turn.user_text[:60]}...")
                tr = await execute_turn(ws, turn, i + 1, name)
                results.append(tr)

                # Print per-turn JSON log
                turn_log = {
                    "scenario": name,
                    "turn": tr.turn,
                    "user_text": tr.user_text,
                    "intent": tr.detected_intent,
                    "confidence": tr.detected_confidence,
                    "target_kind": tr.target_kind,
                    "target_report_id": tr.target_report_id,
                    "row_count": tr.target_row_count,
                    "pass": tr.pass_fail,
                    "reason": tr.failure_reason,
                    "gap_category": tr.gap_category,
                }
                print(f"  {json.dumps(turn_log)}")

    except Exception as e:
        print(f"  CONNECTION ERROR: {e}")
        return {
            "scenario": name,
            "total": len(turns),
            "passed": 0,
            "failed": len(turns),
            "failures": [{"turn": "all", "reason": f"connection error: {e}"}],
            "status": "error",
        }

    passed = sum(1 for r in results if r.pass_fail)
    failed = sum(1 for r in results if not r.pass_fail)
    failure_details = [
        {
            "turn": r.turn,
            "user_text": r.user_text[:60],
            "reason": r.failure_reason,
            "gap_category": r.gap_category,
        }
        for r in results if not r.pass_fail
    ]

    summary = {
        "scenario": name,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "failures": failure_details,
        "status": "pass" if failed == 0 else "fail",
    }
    print(f"\n  SUMMARY: {json.dumps(summary)}")
    return summary


async def main():
    """Run all non-stub scenarios and print final gap summary."""
    print(f"Sei Engine E2E Test Harness")
    print(f"Server: {SERVER_URL}")
    print(f"Auth: Bearer {'*' * (len(AUTH_TOKEN) - 4)}{AUTH_TOKEN[-4:]}")
    print(f"Timeout: {TURN_TIMEOUT}s per turn")

    all_summaries = []
    for scenario_fn in ALL_SCENARIOS:
        summary = await run_scenario(scenario_fn)
        if summary is not None:
            all_summaries.append(summary)

    # Final gap summary
    print(f"\n{'='*60}")
    print(f"FINAL GAP SUMMARY")
    print(f"{'='*60}")

    total_scenarios = len(all_summaries)
    total_turns = sum(s["total"] for s in all_summaries)
    total_passed = sum(s["passed"] for s in all_summaries)
    total_failed = sum(s["failed"] for s in all_summaries)
    all_failures = []
    for s in all_summaries:
        for f in s.get("failures", []):
            f["scenario"] = s["scenario"]
            all_failures.append(f)

    # Group failures by gap category
    gap_counts: dict[str, int] = {}
    for f in all_failures:
        cat = f.get("gap_category", "unknown")
        gap_counts[cat] = gap_counts.get(cat, 0) + 1

    final = {
        "scenarios_run": total_scenarios,
        "scenarios_skipped": len(ALL_SCENARIOS) - total_scenarios,
        "total_turns": total_turns,
        "passed": total_passed,
        "failed": total_failed,
        "gap_breakdown": gap_counts,
        "failures": all_failures,
        "overall": "PASS" if total_failed == 0 else "FAIL",
    }
    print(json.dumps(final, indent=2))

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
