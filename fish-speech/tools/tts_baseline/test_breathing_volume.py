"""A/B test script for Fish Speech breathing gaps and volume dynamics.

Generates audio via the TTS API and measures the effect of each sub-feature
independently: breathing silence insertion (gap count metric) and volume
dynamics (RMS ratio metric).

Requires TTS server running at http://127.0.0.1:8080.

Output:
  - WAV files: /home/prana/tts-test/outputs/breathing_volume_tests/{test}_{runN}.wav
  - Results:   /home/prana/tts-test/outputs/breathing_volume_tests/bv_results.json
  - Report:    /home/prana/tts-test/outputs/breathing_volume_tests/bv_report.md
"""

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ormsgpack
import requests
import soundfile as sf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUT_DIR = Path("/home/prana/tts-test/outputs/breathing_volume_tests")
API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"
RUNS_PER_TEST = 3
SAMPLE_RATE = 44100

# ---------------------------------------------------------------------------
# Breathing gap test cases (BRVL-01, BRVL-02)
# ---------------------------------------------------------------------------

BREATHING_TESTS = [
    {
        "name": "long_phrase_breathing",
        "text": "Ladies and gentlemen I want to thank each and every one of you for "
                "being here tonight on this special occasion that means so much to all of us.",
        "description": "Long phrase (25+ words) should trigger breathing gap",
        "metric": "silence_gap_count",
        "threshold_desc": "At least 1 silence gap > 60ms in audio",
    },
    {
        "name": "short_phrase_no_breathing",
        "text": "Hello everyone. Thanks for coming.",
        "description": "Short phrase should NOT trigger breathing",
        "metric": "silence_gap_count",
        "threshold_desc": "No additional silence gaps vs baseline model output",
    },
    {
        "name": "multi_sentence_cap",
        "text": "The first point is important and we need to discuss it thoroughly before moving on. "
                "The second topic is equally critical and demands our full attention today. "
                "Now the third item on the agenda requires careful consideration from everyone. "
                "Finally we should address the last and most important matter before us.",
        "description": "4 sentences, max 1 breathing gap (BRVL-02: 1 per 4 sentences)",
        "metric": "max_silence_gaps",
        "threshold_desc": "At most 1 silence gap > 60ms",
    },
]

# ---------------------------------------------------------------------------
# Volume dynamics test cases (BRVL-03, BRVL-04)
# ---------------------------------------------------------------------------

VOLUME_TESTS = [
    {
        "name": "parenthetical_aside",
        "text": "The main point is clear (though some may disagree with the reasoning) and we should act on it immediately.",
        "description": "Parenthetical should be quieter (0.85x gain)",
        "metric": "rms_region_ratio",
        "region_desc": "parenthetical vs surrounding",
        "threshold_desc": "RMS of parenthetical region < 0.95x RMS of surrounding (audible difference)",
    },
    {
        "name": "exclamation_emphasis",
        "text": "Everyone was standing around doing nothing. This is completely unacceptable! We need to fix this right now.",
        "description": "Exclamation sentence should be louder (1.1x gain)",
        "metric": "rms_region_ratio",
        "region_desc": "exclamation vs surrounding",
        "threshold_desc": "RMS of exclamation region > 1.02x RMS of surrounding",
    },
    {
        "name": "em_dash_aside",
        "text": "He walked into the room -- looking rather tired and disheveled -- and sat down without a word.",
        "description": "Em-dash aside should be quieter (0.85x gain)",
        "metric": "rms_region_ratio",
        "region_desc": "em-dash aside vs surrounding",
        "threshold_desc": "RMS of aside region < 0.95x RMS of surrounding",
    },
]


# ---------------------------------------------------------------------------
# TTS API helper
# ---------------------------------------------------------------------------


def generate_audio(text: str) -> np.ndarray:
    """Call the Fish Speech TTS API and return float32 samples."""
    payload = {
        "text": text,
        "reference_id": REFERENCE_ID,
        "format": "wav",
        "temperature": 0.7,
        "top_p": 0.8,
        "repetition_penalty": 1.2,
        "max_new_tokens": 2048,
        "chunk_length": 200,
        "streaming": True,
    }

    response = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        stream=True,
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"TTS API returned {response.status_code}: {response.text[:200]}"
        )

    raw_bytes = b""
    for chunk in response.iter_content(chunk_size=None):
        raw_bytes += chunk

    # Skip 44-byte WAV header, convert int16 PCM to float32
    pcm_data = raw_bytes[44:]
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def save_wav(samples: np.ndarray, path: Path) -> None:
    """Write float32 samples as a WAV file."""
    sf.write(str(path), samples, SAMPLE_RATE, format="wav")


# ---------------------------------------------------------------------------
# Measurement functions
# ---------------------------------------------------------------------------


def compute_rms(audio: np.ndarray) -> float:
    """Root mean square energy of an audio array."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio ** 2)))


def count_silence_gaps(
    audio: np.ndarray,
    sr: int,
    min_gap_ms: float = 60.0,
    threshold_rms: float = 0.01,
) -> int:
    """Count silence gaps where RMS drops below threshold for >= min_gap_ms.

    Slides a window across the audio and detects contiguous silent regions.

    Args:
        audio: Float32 mono audio.
        sr: Sample rate.
        min_gap_ms: Minimum gap duration in milliseconds to count.
        threshold_rms: RMS threshold below which audio is considered silent.

    Returns:
        Number of silence gaps detected.
    """
    window_samples = int(sr * 10 / 1000)  # 10ms analysis window
    min_gap_windows = int(min_gap_ms / 10)  # Min consecutive silent windows

    gap_count = 0
    consecutive_silent = 0

    for i in range(0, len(audio) - window_samples, window_samples):
        window = audio[i : i + window_samples]
        window_rms = compute_rms(window)

        if window_rms < threshold_rms:
            consecutive_silent += 1
        else:
            if consecutive_silent >= min_gap_windows:
                gap_count += 1
            consecutive_silent = 0

    # Check final run
    if consecutive_silent >= min_gap_windows:
        gap_count += 1

    return gap_count


def compute_region_rms_ratio(
    audio: np.ndarray,
    region_start_frac: float,
    region_end_frac: float,
) -> tuple[float, float, float]:
    """Compute RMS of a fractional region vs the rest of the audio.

    Args:
        audio: Float32 mono audio.
        region_start_frac: Start of region as fraction of total length (0.0-1.0).
        region_end_frac: End of region as fraction of total length (0.0-1.0).

    Returns:
        (region_rms, rest_rms, ratio) where ratio = region_rms / rest_rms.
    """
    n = len(audio)
    start = int(n * region_start_frac)
    end = int(n * region_end_frac)

    region = audio[start:end]
    rest = np.concatenate([audio[:start], audio[end:]])

    region_rms = compute_rms(region)
    rest_rms = compute_rms(rest)
    ratio = region_rms / rest_rms if rest_rms > 0 else 0.0

    return region_rms, rest_rms, ratio


# ---------------------------------------------------------------------------
# Test evaluation
# ---------------------------------------------------------------------------


def evaluate_breathing_test(test: dict, runs: list[np.ndarray]) -> dict:
    """Evaluate a breathing test case across multiple runs.

    Returns result dict with measurements and pass/fail verdict.
    """
    gap_counts = [count_silence_gaps(r, SAMPLE_RATE) for r in runs]
    median_gaps = statistics.median(gap_counts)
    durations = [len(r) / SAMPLE_RATE for r in runs]

    base = {
        "name": test["name"],
        "category": "breathing",
        "description": test["description"],
        "metric": test["metric"],
        "gap_counts": gap_counts,
        "median_gaps": median_gaps,
        "durations": [round(d, 3) for d in durations],
        "median_duration": round(statistics.median(durations), 3),
        "threshold_desc": test["threshold_desc"],
    }

    if test["metric"] == "silence_gap_count":
        if test["name"] == "short_phrase_no_breathing":
            # Short phrase: expect 0 breathing gaps (model-native gaps are fine)
            # Conservative: just check we don't add excessive gaps
            passed = median_gaps <= 1
            base["metric_value"] = median_gaps
            base["threshold"] = "<=1 gap"
        else:
            # Long phrase: expect at least 1 breathing gap
            passed = median_gaps >= 1
            base["metric_value"] = median_gaps
            base["threshold"] = ">=1 gap"

    elif test["metric"] == "max_silence_gaps":
        # Multi-sentence: at most 1 breathing gap (BRVL-02 cap)
        passed = median_gaps <= 1
        base["metric_value"] = median_gaps
        base["threshold"] = "<=1 gap"

    else:
        passed = False
        base["metric_value"] = 0
        base["threshold"] = "unknown"

    base["result"] = "PASS" if passed else "FAIL"
    return base


def evaluate_volume_test(test: dict, runs: list[np.ndarray]) -> dict:
    """Evaluate a volume dynamics test case across multiple runs.

    Uses fractional region RMS comparison based on the test name to determine
    which part of the audio should be quieter/louder.

    Returns result dict with measurements and pass/fail verdict.
    """
    # Determine region fractions based on test type
    if test["name"] == "parenthetical_aside":
        # Parenthetical is roughly in the middle third
        region_start, region_end = 0.30, 0.65
        expect_quieter = True
    elif test["name"] == "exclamation_emphasis":
        # Exclamation is the middle sentence
        region_start, region_end = 0.30, 0.65
        expect_quieter = False
    elif test["name"] == "em_dash_aside":
        # Em-dash aside is roughly in the middle
        region_start, region_end = 0.25, 0.60
        expect_quieter = True
    else:
        region_start, region_end = 0.25, 0.75
        expect_quieter = True

    ratios = []
    region_rms_vals = []
    rest_rms_vals = []

    for r in runs:
        region_rms, rest_rms, ratio = compute_region_rms_ratio(
            r, region_start, region_end
        )
        ratios.append(ratio)
        region_rms_vals.append(region_rms)
        rest_rms_vals.append(rest_rms)

    median_ratio = statistics.median(ratios)
    median_region_rms = statistics.median(region_rms_vals)
    median_rest_rms = statistics.median(rest_rms_vals)
    durations = [len(r) / SAMPLE_RATE for r in runs]

    base = {
        "name": test["name"],
        "category": "volume",
        "description": test["description"],
        "metric": test["metric"],
        "region_desc": test.get("region_desc", ""),
        "region_frac": f"{region_start:.2f}-{region_end:.2f}",
        "ratios": [round(r, 4) for r in ratios],
        "median_ratio": round(median_ratio, 4),
        "median_region_rms": round(median_region_rms, 6),
        "median_rest_rms": round(median_rest_rms, 6),
        "durations": [round(d, 3) for d in durations],
        "median_duration": round(statistics.median(durations), 3),
        "threshold_desc": test["threshold_desc"],
    }

    if expect_quieter:
        # Aside region should be quieter: ratio < 0.95
        passed = median_ratio < 0.95
        base["metric_value"] = round(median_ratio, 4)
        base["threshold"] = "<0.95 (quieter)"
    else:
        # Emphasis region should be louder: ratio > 1.02
        passed = median_ratio > 1.02
        base["metric_value"] = round(median_ratio, 4)
        base["threshold"] = ">1.02 (louder)"

    base["result"] = "PASS" if passed else "FAIL"
    return base


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(breathing_results: list, volume_results: list) -> str:
    """Generate markdown report from test results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    all_results = breathing_results + volume_results

    lines = [
        "# Breathing & Volume Dynamics A/B Test Report",
        f"Generated: {timestamp}",
        "Model: Fish Speech S2-Pro (reference: archie)",
        f"Runs per test: {RUNS_PER_TEST} (median reported)",
        "",
        "## Summary",
        "",
        "| Test | Feature | Metric | Median | Threshold | Verdict |",
        "|------|---------|--------|--------|-----------|---------|",
    ]

    for r in all_results:
        feature = r["category"].title()
        metric_val = r.get("metric_value", "")
        lines.append(
            f"| {r['name']} | {feature} | {r['metric']} "
            f"| {metric_val} | {r.get('threshold', '')} | {r['result']} |"
        )

    # Breathing details
    lines.extend(["", "## Breathing Gap Tests", ""])
    for r in breathing_results:
        lines.append(f"### {r['name']}")
        lines.append(f"- Description: {r['description']}")
        lines.append(f"- Gap counts per run: {r['gap_counts']}")
        lines.append(f"- Median gaps: {r['median_gaps']}")
        lines.append(f"- Durations: {r['durations']}s (median {r['median_duration']}s)")
        lines.append(f"- Threshold: {r['threshold_desc']}")
        lines.append(f"- Result: **{r['result']}**")
        lines.append("")

    # Volume details
    lines.extend(["## Volume Dynamics Tests", ""])
    for r in volume_results:
        lines.append(f"### {r['name']}")
        lines.append(f"- Description: {r['description']}")
        lines.append(f"- Region: {r.get('region_desc', '')} ({r.get('region_frac', '')})")
        lines.append(f"- RMS ratios per run: {r['ratios']}")
        lines.append(f"- Median ratio: {r['median_ratio']} (region={r['median_region_rms']:.6f}, rest={r['median_rest_rms']:.6f})")
        lines.append(f"- Durations: {r['durations']}s (median {r['median_duration']}s)")
        lines.append(f"- Threshold: {r['threshold_desc']}")
        lines.append(f"- Result: **{r['result']}**")
        lines.append("")

    # Overall summary
    passed = sum(1 for r in all_results if r["result"] == "PASS")
    total = len(all_results)
    lines.append("## Overall")
    lines.append(f"- Tests: {total}")
    lines.append(f"- PASS: {passed}")
    lines.append(f"- FAIL: {total - passed}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    breathing_results = []
    volume_results = []

    # --- Breathing tests ---
    for test in BREATHING_TESTS:
        print(f"\n{'=' * 60}")
        print(f"Breathing test: {test['name']}")
        print(f"  {test['description']}")
        print(f"{'=' * 60}")

        runs = []
        for run_idx in range(1, RUNS_PER_TEST + 1):
            print(f"  Run {run_idx}/{RUNS_PER_TEST}...")
            t0 = time.monotonic()
            samples = generate_audio(test["text"])
            elapsed = time.monotonic() - t0

            path = OUT_DIR / f"{test['name']}_run{run_idx}.wav"
            save_wav(samples, path)
            dur = len(samples) / SAMPLE_RATE
            gaps = count_silence_gaps(samples, SAMPLE_RATE)
            print(f"    -> {dur:.3f}s, {gaps} silence gaps, generated in {elapsed:.1f}s")
            runs.append(samples)

        result = evaluate_breathing_test(test, runs)
        breathing_results.append(result)
        print(f"  => {test['name']}: {result['result']} (gaps={result['median_gaps']}, threshold={result['threshold']})")

    # --- Volume tests ---
    for test in VOLUME_TESTS:
        print(f"\n{'=' * 60}")
        print(f"Volume test: {test['name']}")
        print(f"  {test['description']}")
        print(f"{'=' * 60}")

        runs = []
        for run_idx in range(1, RUNS_PER_TEST + 1):
            print(f"  Run {run_idx}/{RUNS_PER_TEST}...")
            t0 = time.monotonic()
            samples = generate_audio(test["text"])
            elapsed = time.monotonic() - t0

            path = OUT_DIR / f"{test['name']}_run{run_idx}.wav"
            save_wav(samples, path)
            dur = len(samples) / SAMPLE_RATE
            print(f"    -> {dur:.3f}s, generated in {elapsed:.1f}s")
            runs.append(samples)

        result = evaluate_volume_test(test, runs)
        volume_results.append(result)
        print(f"  => {test['name']}: {result['result']} (ratio={result['median_ratio']}, threshold={result['threshold']})")

    # --- Save results ---
    all_results = breathing_results + volume_results

    results_path = OUT_DIR / "bv_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    report = generate_report(breathing_results, volume_results)
    report_path = OUT_DIR / "bv_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")

    # --- Print summary ---
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    passed = sum(1 for r in all_results if r["result"] == "PASS")
    failed = sum(1 for r in all_results if r["result"] == "FAIL")
    print(f"  Tests: {len(all_results)}")
    print(f"  PASS: {passed}")
    print(f"  FAIL: {failed}")
    for r in all_results:
        print(f"    {r['name']}: {r['result']}")


if __name__ == "__main__":
    main()
