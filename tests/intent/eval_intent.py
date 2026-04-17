#!/usr/bin/env python3
"""Intent classifier evaluation harness.

Runs all examples from golden_set.json through classify_intent() and reports
per-intent accuracy, latency percentiles, and failure details.

Usage:
    python3 tests/intent/eval_intent.py
    python3 tests/intent/eval_intent.py --verbose
    python3 tests/intent/eval_intent.py --category adversarial
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add scripts/ to sys.path so we can import intent_classifier
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from intent_classifier import classify_intent


def load_golden_set(category_filter: str | None = None) -> list[dict]:
    """Load golden_set.json, optionally filtering by category."""
    golden_path = Path(__file__).resolve().parent / "golden_set.json"
    with open(golden_path) as f:
        examples = json.load(f)
    if category_filter:
        examples = [ex for ex in examples if ex.get("category") == category_filter]
    return examples


def percentile(sorted_values: list[float], pct: float) -> float:
    """Calculate percentile from a sorted list of values."""
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * pct / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


async def evaluate_single(
    example: dict, verbose: bool = False
) -> dict:
    """Evaluate a single example and return the result record."""
    text = example["text"]
    has_active_report = example.get("has_active_report", False)
    expected = example["expected_intent"]

    start = time.perf_counter()
    result = await classify_intent(text, [], has_active_report)
    elapsed_ms = (time.perf_counter() - start) * 1000

    got_intent = result["intent"]
    confidence = result.get("confidence", 0.0)
    passed = got_intent == expected

    record = {
        "text": text,
        "expected": expected,
        "got": got_intent,
        "confidence": confidence,
        "latency_ms": elapsed_ms,
        "passed": passed,
        "category": example.get("category", "unknown"),
    }

    if verbose:
        status = "PASS" if passed else "FAIL"
        print(
            f"  [{status}] \"{text}\" -- expected: {expected}, "
            f"got: {got_intent} (conf={confidence:.2f}, {elapsed_ms:.0f}ms)"
        )

    return record


async def main():
    parser = argparse.ArgumentParser(description="Intent classifier evaluation harness")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print each example as it runs"
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=["natural", "adversarial", "edge_case"],
        help="Filter examples by category",
    )
    args = parser.parse_args()

    examples = load_golden_set(args.category)
    if not examples:
        print(f"No examples found for category: {args.category}")
        sys.exit(1)

    total = len(examples)
    results = []

    print(f"Running {total} examples through classify_intent()...\n")

    for i, example in enumerate(examples):
        record = await evaluate_single(example, verbose=args.verbose)
        results.append(record)
        # Brief pause between calls to avoid overwhelming the LLM
        if i < total - 1:
            await asyncio.sleep(0.1)

    # Aggregate results
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    accuracy = (passed / total * 100) if total > 0 else 0.0

    # Per-intent breakdown
    intent_stats: dict[str, dict[str, int]] = {}
    for r in results:
        intent = r["expected"]
        if intent not in intent_stats:
            intent_stats[intent] = {"total": 0, "passed": 0}
        intent_stats[intent]["total"] += 1
        if r["passed"]:
            intent_stats[intent]["passed"] += 1

    # Latency stats
    latencies = sorted(r["latency_ms"] for r in results)
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p_max = max(latencies) if latencies else 0.0

    # Category breakdown
    category_stats: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0}
        category_stats[cat]["total"] += 1
        if r["passed"]:
            category_stats[cat]["passed"] += 1

    # Print report
    print("\n=== Intent Classifier Evaluation ===")
    print(f"Total: {total} | Pass: {passed} | Fail: {failed} | Accuracy: {accuracy:.1f}%")
    print()
    print("Per-intent breakdown:")
    for intent in sorted(intent_stats.keys()):
        s = intent_stats[intent]
        pct = (s["passed"] / s["total"] * 100) if s["total"] > 0 else 0.0
        print(f"  {intent:30s} {s['passed']}/{s['total']} ({pct:.1f}%)")
    print()
    print(f"Latency (p50/p95/max): {p50:.0f}ms / {p95:.0f}ms / {p_max:.0f}ms")
    print()

    # Print failures
    failures = [r for r in results if not r["passed"]]
    if failures:
        print("Failures:")
        for f in failures:
            print(
                f"  [FAIL] \"{f['text']}\" -- expected: {f['expected']}, "
                f"got: {f['got']} (conf={f['confidence']:.2f})"
            )
    else:
        print("No failures!")
    print()

    print("Category breakdown:")
    for cat in sorted(category_stats.keys()):
        s = category_stats[cat]
        pct = (s["passed"] / s["total"] * 100) if s["total"] > 0 else 0.0
        print(f"  {cat:15s} {s['passed']}/{s['total']} ({pct:.1f}%)")

    # Exit code: 0 if accuracy >= 95%, 1 otherwise
    threshold = 95.0
    print(f"\nAccuracy threshold: {threshold}%")
    if accuracy >= threshold:
        print(f"PASSED ({accuracy:.1f}% >= {threshold}%)")
        sys.exit(0)
    else:
        print(f"FAILED ({accuracy:.1f}% < {threshold}%)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
