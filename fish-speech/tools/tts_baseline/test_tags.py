"""Test Fish Speech S2-Pro inline tag responsiveness.

Generates A/B pairs (with tag vs without tag) for each of the 9 inline tags,
runs each pair 3 times to account for model stochasticity, and produces
measurements with pass/fail verdicts based on defined thresholds.

Output:
  - WAV files: /home/prana/tts-test/outputs/tag_tests/{tag}_{with|without}_run{N}.wav
  - Results:   /home/prana/tts-test/outputs/tag_tests/tag_results.json
  - Report:    /home/prana/tts-test/outputs/tag_tests/tag_report.md
"""

import json
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ormsgpack
import requests
import soundfile as sf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUT_DIR = Path("/home/prana/tts-test/outputs/tag_tests")
API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"
RUNS_PER_TAG = 3
SAMPLE_RATE = 44100

# ---------------------------------------------------------------------------
# Tag test case definitions
# ---------------------------------------------------------------------------

TAG_TESTS = [
    {
        "tag": "pause",
        "with_text": "I need to tell you something. [pause] It's about what happened yesterday.",
        "without_text": "I need to tell you something. It's about what happened yesterday.",
        "metric": "duration_diff",
        "threshold_desc": ">200ms diff",
    },
    {
        "tag": "inhale",
        "with_text": "[inhale] Ladies and gentlemen, I want to thank each and every one of you for being here tonight on this special occasion.",
        "without_text": "Ladies and gentlemen, I want to thank each and every one of you for being here tonight on this special occasion.",
        "metric": "rms_first_500ms",
        "threshold_desc": ">1.5x RMS first 500ms",
    },
    {
        "tag": "slow",
        "with_text": "The results are in and [slow] I regret to inform you that the project has been cancelled.",
        "without_text": "The results are in and I regret to inform you that the project has been cancelled.",
        "metric": "duration_ratio",
        "threshold_desc": ">5% longer",
    },
    {
        "tag": "fast",
        "with_text": "So basically [fast] what happened was the server crashed and we lost everything and nobody knew what to do [fast] but then Sarah fixed it.",
        "without_text": "So basically what happened was the server crashed and we lost everything and nobody knew what to do but then Sarah fixed it.",
        "metric": "duration_ratio_shorter",
        "threshold_desc": ">5% shorter",
    },
    {
        "tag": "short_pause",
        "with_text": "Well [short pause] I suppose that makes sense when you think about it.",
        "without_text": "Well I suppose that makes sense when you think about it.",
        "metric": "duration_diff_short",
        "threshold_desc": ">50ms diff, < [pause] diff",
    },
    {
        "tag": "emphasis",
        "with_text": "I told you [emphasis] not to touch that button under any circumstances.",
        "without_text": "I told you not to touch that button under any circumstances.",
        "metric": "rms_overall",
        "threshold_desc": ">1.2x RMS of segment",
    },
    {
        "tag": "low_volume",
        "with_text": "Everyone can hear me fine but [low volume] this next part is just between us.",
        "without_text": "Everyone can hear me fine but this next part is just between us.",
        "metric": "rms_second_half",
        "threshold_desc": "<0.8x RMS second half",
    },
    {
        "tag": "volume_up",
        "with_text": "I started off quiet but then [volume up] I realized everyone needed to hear this part clearly.",
        "without_text": "I started off quiet but then I realized everyone needed to hear this part clearly.",
        "metric": "rms_second_half",
        "threshold_desc": ">1.2x RMS second half",
    },
    {
        "tag": "whisper",
        "with_text": "[whisper] Don't look now but I think someone is watching us from across the room.",
        "without_text": "Don't look now but I think someone is watching us from across the room.",
        "metric": "rms_overall_lower",
        "threshold_desc": "<0.5x overall RMS",
    },
]

COMBINATION_TEST = {
    "tag": "combination",
    "with_text": "[inhale] I have an announcement. [pause] [slow] We are shutting down the program effective immediately.",
    "without_text": "I have an announcement. We are shutting down the program effective immediately.",
}


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
        "max_new_tokens": 1024,
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
# Measurement helpers
# ---------------------------------------------------------------------------


def audio_duration(samples: np.ndarray) -> float:
    """Duration in seconds."""
    return len(samples) / SAMPLE_RATE


def rms_energy(samples: np.ndarray) -> float:
    """Root mean square energy."""
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))


def rms_first_n_ms(samples: np.ndarray, ms: int = 500) -> float:
    """RMS of the first N milliseconds."""
    n_samples = int(SAMPLE_RATE * ms / 1000)
    segment = samples[:n_samples]
    return rms_energy(segment)


def rms_second_half(samples: np.ndarray) -> float:
    """RMS of the second half of the audio."""
    mid = len(samples) // 2
    return rms_energy(samples[mid:])


# ---------------------------------------------------------------------------
# Pass/fail evaluation
# ---------------------------------------------------------------------------


def evaluate_tag(tag: str, metric: str, runs_with: list, runs_without: list, pause_median_diff: float | None = None) -> dict:
    """Evaluate pass/fail for a tag based on its metric type.

    Returns a dict with result details including PASS/FAIL verdict.
    """
    durations_with = [audio_duration(s) for s in runs_with]
    durations_without = [audio_duration(s) for s in runs_without]
    median_dur_with = statistics.median(durations_with)
    median_dur_without = statistics.median(durations_without)
    duration_diff = median_dur_with - median_dur_without
    duration_diff_pct = (duration_diff / median_dur_without * 100) if median_dur_without > 0 else 0

    base = {
        "tag": tag,
        "median_duration_with": round(median_dur_with, 3),
        "median_duration_without": round(median_dur_without, 3),
        "duration_diff_s": round(duration_diff, 3),
        "duration_diff_pct": round(duration_diff_pct, 1),
        "runs_with_durations": [round(d, 3) for d in durations_with],
        "runs_without_durations": [round(d, 3) for d in durations_without],
    }

    if metric == "duration_diff":
        # [pause]: PASS if median duration_diff > 200ms
        passed = duration_diff > 0.2
        base["metric_name"] = "duration_diff_ms"
        base["metric_value"] = round(duration_diff * 1000, 1)
        base["threshold"] = ">200ms"

    elif metric == "rms_first_500ms":
        # [inhale]: PASS if median RMS of first 500ms > 1.5x without version
        rms_with_vals = [rms_first_n_ms(s, 500) for s in runs_with]
        rms_without_vals = [rms_first_n_ms(s, 500) for s in runs_without]
        median_rms_with = statistics.median(rms_with_vals)
        median_rms_without = statistics.median(rms_without_vals)
        ratio = median_rms_with / median_rms_without if median_rms_without > 0 else 0
        passed = ratio > 1.5
        base["metric_name"] = "rms_first_500ms_ratio"
        base["metric_value"] = round(ratio, 3)
        base["median_rms_with"] = round(median_rms_with, 6)
        base["median_rms_without"] = round(median_rms_without, 6)
        base["threshold"] = ">1.5x"

    elif metric == "duration_ratio":
        # [slow]: PASS if median duration_with > 1.05x duration_without
        ratio = median_dur_with / median_dur_without if median_dur_without > 0 else 0
        passed = ratio > 1.05
        base["metric_name"] = "duration_ratio"
        base["metric_value"] = round(ratio, 3)
        base["threshold"] = ">1.05x"

    elif metric == "duration_ratio_shorter":
        # [fast]: PASS if median duration_with < 0.95x duration_without
        ratio = median_dur_with / median_dur_without if median_dur_without > 0 else 0
        passed = ratio < 0.95
        base["metric_name"] = "duration_ratio"
        base["metric_value"] = round(ratio, 3)
        base["threshold"] = "<0.95x"

    elif metric == "duration_diff_short":
        # [short pause]: PASS if median duration_diff > 50ms AND < [pause] diff
        diff_ms = duration_diff * 1000
        passed = diff_ms > 50
        if pause_median_diff is not None:
            passed = passed and (diff_ms < pause_median_diff * 1000)
        base["metric_name"] = "duration_diff_ms"
        base["metric_value"] = round(diff_ms, 1)
        base["threshold"] = f">50ms, <{round(pause_median_diff * 1000, 1) if pause_median_diff else '?'}ms (pause diff)"

    elif metric == "rms_overall":
        # [emphasis]: PASS if median RMS > 1.2x without version
        rms_with_vals = [rms_energy(s) for s in runs_with]
        rms_without_vals = [rms_energy(s) for s in runs_without]
        median_rms_with = statistics.median(rms_with_vals)
        median_rms_without = statistics.median(rms_without_vals)
        ratio = median_rms_with / median_rms_without if median_rms_without > 0 else 0
        passed = ratio > 1.2
        base["metric_name"] = "rms_overall_ratio"
        base["metric_value"] = round(ratio, 3)
        base["median_rms_with"] = round(median_rms_with, 6)
        base["median_rms_without"] = round(median_rms_without, 6)
        base["threshold"] = ">1.2x"

    elif metric == "rms_second_half" and tag == "low_volume":
        # [low volume]: PASS if median RMS of second half < 0.8x without
        rms_with_vals = [rms_second_half(s) for s in runs_with]
        rms_without_vals = [rms_second_half(s) for s in runs_without]
        median_rms_with = statistics.median(rms_with_vals)
        median_rms_without = statistics.median(rms_without_vals)
        ratio = median_rms_with / median_rms_without if median_rms_without > 0 else 0
        passed = ratio < 0.8
        base["metric_name"] = "rms_second_half_ratio"
        base["metric_value"] = round(ratio, 3)
        base["median_rms_with"] = round(median_rms_with, 6)
        base["median_rms_without"] = round(median_rms_without, 6)
        base["threshold"] = "<0.8x"

    elif metric == "rms_second_half" and tag == "volume_up":
        # [volume up]: PASS if median RMS of second half > 1.2x without
        rms_with_vals = [rms_second_half(s) for s in runs_with]
        rms_without_vals = [rms_second_half(s) for s in runs_without]
        median_rms_with = statistics.median(rms_with_vals)
        median_rms_without = statistics.median(rms_without_vals)
        ratio = median_rms_with / median_rms_without if median_rms_without > 0 else 0
        passed = ratio > 1.2
        base["metric_name"] = "rms_second_half_ratio"
        base["metric_value"] = round(ratio, 3)
        base["median_rms_with"] = round(median_rms_with, 6)
        base["median_rms_without"] = round(median_rms_without, 6)
        base["threshold"] = ">1.2x"

    elif metric == "rms_overall_lower":
        # [whisper]: PASS if median overall RMS < 0.5x without
        rms_with_vals = [rms_energy(s) for s in runs_with]
        rms_without_vals = [rms_energy(s) for s in runs_without]
        median_rms_with = statistics.median(rms_with_vals)
        median_rms_without = statistics.median(rms_without_vals)
        ratio = median_rms_with / median_rms_without if median_rms_without > 0 else 0
        passed = ratio < 0.5
        base["metric_name"] = "rms_overall_ratio"
        base["metric_value"] = round(ratio, 3)
        base["median_rms_with"] = round(median_rms_with, 6)
        base["median_rms_without"] = round(median_rms_without, 6)
        base["threshold"] = "<0.5x"

    else:
        passed = False
        base["metric_name"] = "unknown"
        base["metric_value"] = 0
        base["threshold"] = "unknown"

    base["result"] = "PASS" if passed else "FAIL"
    return base


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


TAG_DISPLAY_NAMES = {
    "pause": "[pause]",
    "inhale": "[inhale]",
    "slow": "[slow]",
    "fast": "[fast]",
    "short_pause": "[short pause]",
    "emphasis": "[emphasis]",
    "low_volume": "[low volume]",
    "volume_up": "[volume up]",
    "whisper": "[whisper]",
}

PHASE_IMPLICATIONS = {
    "pause": {
        "phase": "Phase 3",
        "pass": "[pause] tag viable for pause injection",
        "fail": "Must rely on punctuation-only pauses",
    },
    "inhale": {
        "phase": "Phase 4",
        "pass": "[inhale] tag viable for breathing injection",
        "fail": "Skip breathing injection, model handles natively from reference",
    },
    "slow": {
        "phase": "Phase 3",
        "pass": "[slow] tag viable for speech rate variation",
        "fail": "Must rely on chunk-size manipulation for rate variation",
    },
    "fast": {
        "phase": "Phase 3",
        "pass": "[fast] tag viable for speech rate variation",
        "fail": "Must rely on chunk-size manipulation for rate variation",
    },
    "short_pause": {
        "phase": "Phase 3",
        "pass": "[short pause] viable for light hesitation injection",
        "fail": "Use punctuation commas for light pauses",
    },
    "emphasis": {
        "phase": "Phase 3",
        "pass": "[emphasis] viable for stress on key words",
        "fail": "Rely on model's natural prosodic stress",
    },
    "low_volume": {
        "phase": "Phase 4",
        "pass": "[low volume] viable for dynamic volume control",
        "fail": "Must use post-FX gain automation for quiet passages",
    },
    "volume_up": {
        "phase": "Phase 4",
        "pass": "[volume up] viable for dynamic volume control",
        "fail": "Must use post-FX gain automation for loud passages",
    },
    "whisper": {
        "phase": "Phase 4",
        "pass": "[whisper] viable for intimate/quiet speech style",
        "fail": "Skip whisper effect or attempt via post-FX low-pass + gain reduction",
    },
}


def generate_report(results: list, combo_result: dict | None) -> str:
    """Generate the tag_report.md from results JSON data."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# Inline Tag Responsiveness Report",
        f"Generated: {timestamp}",
        "Model: Fish Speech S2-Pro (reference: archie)",
        f"Runs per tag: {RUNS_PER_TAG} (median reported)",
        "",
        "## Summary",
        "",
        "| Tag | Result | Duration With (s) | Duration Without (s) | Diff (%) | Metric Value | Threshold |",
        "|-----|--------|-------------------|---------------------|----------|--------------|-----------|",
    ]

    for r in results:
        display = TAG_DISPLAY_NAMES.get(r["tag"], r["tag"])
        diff_str = f"{r['duration_diff_pct']:+.1f}%"
        metric_val = str(r.get("metric_value", ""))
        lines.append(
            f"| {display} | {r['result']} | {r['median_duration_with']:.2f} "
            f"| {r['median_duration_without']:.2f} | {diff_str} "
            f"| {metric_val} | {r.get('threshold', '')} |"
        )

    lines.append("")
    lines.append("## Detailed Results")
    lines.append("")

    for r in results:
        display = TAG_DISPLAY_NAMES.get(r["tag"], r["tag"])
        tag_key = r["tag"]
        test_def = next((t for t in TAG_TESTS if t["tag"] == tag_key), None)
        carrier = test_def["with_text"] if test_def else ""
        impl = PHASE_IMPLICATIONS.get(tag_key, {})

        lines.append(f"### {display}")
        lines.append(f"- Carrier: \"{carrier}\"")

        for i in range(RUNS_PER_TAG):
            w = r["runs_with_durations"][i] if i < len(r["runs_with_durations"]) else "?"
            wo = r["runs_without_durations"][i] if i < len(r["runs_without_durations"]) else "?"
            if isinstance(w, (int, float)) and isinstance(wo, (int, float)):
                diff = w - wo
                lines.append(f"- Run {i+1}: with={w:.3f}s, without={wo:.3f}s, diff={diff:.3f}s")
            else:
                lines.append(f"- Run {i+1}: with={w}, without={wo}")

        lines.append(f"- Median diff: {r['duration_diff_s']:.3f}s ({r['duration_diff_pct']:+.1f}%)")
        if "median_rms_with" in r:
            lines.append(f"- Metric ({r['metric_name']}): {r['metric_value']} (with RMS={r['median_rms_with']:.6f}, without RMS={r['median_rms_without']:.6f})")
        else:
            lines.append(f"- Metric ({r['metric_name']}): {r['metric_value']}")
        lines.append(f"- Result: **{r['result']}**")

        if impl:
            if r["result"] == "PASS":
                lines.append(f"- Implication for {impl['phase']}: {impl['pass']}")
            else:
                lines.append(f"- Implication for {impl['phase']}: {impl['fail']}")

        lines.append("")

    # Combination test
    if combo_result:
        lines.append("## Combination Test")
        lines.append(f"- Text: \"{COMBINATION_TEST['with_text']}\"")
        lines.append(f"- Duration (with tags): {combo_result['duration_with']:.3f}s")
        lines.append(f"- Duration (without tags): {combo_result['duration_without']:.3f}s")
        lines.append(f"- Duration diff: {combo_result['duration_diff']:.3f}s ({combo_result['diff_pct']:+.1f}%)")
        lines.append(f"- Observation: {combo_result.get('observation', 'Tags compose without errors; effect on audio characteristics documented above.')}")
        lines.append("")

    # Phase implications summary
    phase3_tags = [r for r in results if r["tag"] in ("pause", "slow", "fast", "short_pause", "emphasis")]
    phase4_tags = [r for r in results if r["tag"] in ("inhale", "low_volume", "volume_up", "whisper")]

    p3_pass = [TAG_DISPLAY_NAMES[r["tag"]] for r in phase3_tags if r["result"] == "PASS"]
    p3_fail = [TAG_DISPLAY_NAMES[r["tag"]] for r in phase3_tags if r["result"] == "FAIL"]
    p4_pass = [TAG_DISPLAY_NAMES[r["tag"]] for r in phase4_tags if r["result"] == "PASS"]
    p4_fail = [TAG_DISPLAY_NAMES[r["tag"]] for r in phase4_tags if r["result"] == "FAIL"]

    lines.append("## Implications for Subsequent Phases")
    lines.append("")
    lines.append(f"- **Phase 3 (Text Preprocessor):** {len(p3_pass)}/{len(phase3_tags)} rate/pause tags responsive. "
                 f"Usable: {', '.join(p3_pass) if p3_pass else 'none'}. "
                 f"Non-responsive: {', '.join(p3_fail) if p3_fail else 'none'}.")
    lines.append(f"- **Phase 4 (Breathing/Volume):** {len(p4_pass)}/{len(phase4_tags)} breathing/volume tags responsive. "
                 f"Usable: {', '.join(p4_pass) if p4_pass else 'none'}. "
                 f"Non-responsive: {', '.join(p4_fail) if p4_fail else 'none'}.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    pause_median_diff = None

    for test in TAG_TESTS:
        tag = test["tag"]
        display = TAG_DISPLAY_NAMES.get(tag, tag)
        print(f"\n{'='*60}")
        print(f"Testing {display}")
        print(f"{'='*60}")

        runs_with = []
        runs_without = []

        for run in range(1, RUNS_PER_TAG + 1):
            print(f"  Run {run}/{RUNS_PER_TAG}...")

            # Generate "with tag" version
            print(f"    Generating WITH tag...")
            samples_with = generate_audio(test["with_text"])
            path_with = OUT_DIR / f"{tag}_with_run{run}.wav"
            save_wav(samples_with, path_with)
            dur_with = audio_duration(samples_with)
            print(f"    -> {dur_with:.3f}s saved to {path_with.name}")
            runs_with.append(samples_with)

            # Generate "without tag" version
            print(f"    Generating WITHOUT tag...")
            samples_without = generate_audio(test["without_text"])
            path_without = OUT_DIR / f"{tag}_without_run{run}.wav"
            save_wav(samples_without, path_without)
            dur_without = audio_duration(samples_without)
            print(f"    -> {dur_without:.3f}s saved to {path_without.name}")
            runs_without.append(samples_without)

        # Evaluate
        result = evaluate_tag(
            tag=tag,
            metric=test["metric"],
            runs_with=runs_with,
            runs_without=runs_without,
            pause_median_diff=pause_median_diff,
        )

        # Store pause diff for short_pause comparison
        if tag == "pause":
            pause_median_diff = result["duration_diff_s"]

        result["threshold_desc"] = test["threshold_desc"]
        all_results.append(result)
        print(f"  => {display}: {result['result']} (metric={result['metric_value']}, threshold={result['threshold']})")

    # Combination test
    print(f"\n{'='*60}")
    print("Testing combination: [inhale] + [pause] + [slow]")
    print(f"{'='*60}")

    combo_durations_with = []
    combo_durations_without = []
    for run in range(1, RUNS_PER_TAG + 1):
        print(f"  Run {run}/{RUNS_PER_TAG}...")
        samples_combo = generate_audio(COMBINATION_TEST["with_text"])
        path_combo = OUT_DIR / f"combination_with_run{run}.wav"
        save_wav(samples_combo, path_combo)
        combo_durations_with.append(audio_duration(samples_combo))

        samples_combo_without = generate_audio(COMBINATION_TEST["without_text"])
        path_combo_without = OUT_DIR / f"combination_without_run{run}.wav"
        save_wav(samples_combo_without, path_combo_without)
        combo_durations_without.append(audio_duration(samples_combo_without))

    median_combo_with = statistics.median(combo_durations_with)
    median_combo_without = statistics.median(combo_durations_without)
    combo_diff = median_combo_with - median_combo_without
    combo_diff_pct = (combo_diff / median_combo_without * 100) if median_combo_without > 0 else 0

    combo_result = {
        "duration_with": round(median_combo_with, 3),
        "duration_without": round(median_combo_without, 3),
        "duration_diff": round(combo_diff, 3),
        "diff_pct": round(combo_diff_pct, 1),
        "observation": "Tags compose without errors; combined effect on duration and prosody documented.",
    }
    print(f"  Combination: with={median_combo_with:.3f}s, without={median_combo_without:.3f}s, diff={combo_diff:.3f}s")

    # Save results JSON
    results_path = OUT_DIR / "tag_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    # Generate and save report
    report = generate_report(all_results, combo_result)
    report_path = OUT_DIR / "tag_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for r in all_results if r["result"] == "PASS")
    failed = sum(1 for r in all_results if r["result"] == "FAIL")
    print(f"  Tags tested: {len(all_results)}")
    print(f"  PASS: {passed}")
    print(f"  FAIL: {failed}")
    for r in all_results:
        display = TAG_DISPLAY_NAMES.get(r["tag"], r["tag"])
        print(f"    {display}: {r['result']}")


if __name__ == "__main__":
    main()
