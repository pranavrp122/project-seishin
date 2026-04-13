#!/usr/bin/env python3
"""Pause distribution analysis and combined baseline report for TTS corpus.

Detects pauses via RMS energy thresholding, computes per-clip and corpus-wide
pause statistics including duration histogram and location distribution.
Optionally generates a combined Markdown report merging F0 and pause data.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf


def detect_pauses(
    data: np.ndarray,
    sr: int,
    frame_ms: float = 10.0,
    min_pause_ms: float = 100.0,
) -> list:
    """Detect pauses in audio using RMS energy thresholding.

    Args:
        data: Audio samples (float64)
        sr: Sample rate
        frame_ms: Frame size in milliseconds (non-overlapping)
        min_pause_ms: Minimum pause duration to count (ignore micro-gaps)

    Returns:
        List of pause dicts with start_s, end_s, duration_ms, location
    """
    frame_size = int(sr * frame_ms / 1000.0)
    hop_size = frame_size

    # Compute RMS energy per frame
    n_frames = (len(data) - frame_size) // hop_size + 1
    rms = np.array([
        np.sqrt(np.mean(data[i * hop_size : i * hop_size + frame_size] ** 2))
        for i in range(n_frames)
    ])

    # Determine silence threshold: 10th percentile of non-zero RMS, floor at 0.01
    nonzero_rms = rms[rms > 0]
    if len(nonzero_rms) > 0:
        threshold = max(np.percentile(nonzero_rms, 10), 0.01)
    else:
        threshold = 0.01

    # Find silent frames
    is_silent = rms < threshold

    # Find contiguous silent runs
    audio_duration_s = len(data) / sr
    min_pause_frames = int(min_pause_ms / frame_ms)
    pauses = []

    in_pause = False
    pause_start = 0

    for i in range(len(is_silent)):
        if is_silent[i] and not in_pause:
            pause_start = i
            in_pause = True
        elif not is_silent[i] and in_pause:
            pause_len = i - pause_start
            if pause_len >= min_pause_frames:
                start_s = pause_start * frame_ms / 1000.0
                end_s = i * frame_ms / 1000.0
                duration_ms = (end_s - start_s) * 1000.0
                # Classify location
                position_ratio = (start_s + end_s) / 2.0 / audio_duration_s
                if position_ratio < 0.10:
                    location = "beginning"
                elif position_ratio > 0.90:
                    location = "end"
                else:
                    location = "middle"
                pauses.append({
                    "start_s": round(start_s, 3),
                    "end_s": round(end_s, 3),
                    "duration_ms": round(duration_ms, 1),
                    "location": location,
                })
            in_pause = False

    # Handle trailing pause
    if in_pause:
        pause_len = len(is_silent) - pause_start
        if pause_len >= min_pause_frames:
            start_s = pause_start * frame_ms / 1000.0
            end_s = len(is_silent) * frame_ms / 1000.0
            duration_ms = (end_s - start_s) * 1000.0
            position_ratio = (start_s + end_s) / 2.0 / audio_duration_s
            if position_ratio < 0.10:
                location = "beginning"
            elif position_ratio > 0.90:
                location = "end"
            else:
                location = "middle"
            pauses.append({
                "start_s": round(start_s, 3),
                "end_s": round(end_s, 3),
                "duration_ms": round(duration_ms, 1),
                "location": location,
            })

    return pauses


def analyze_clip_pauses(wav_path: str) -> dict:
    """Analyze pause distribution for a single WAV file.

    Returns:
        Dictionary of per-clip pause statistics
    """
    data, sr = sf.read(wav_path)
    data = data.astype(np.float64)
    audio_duration_s = len(data) / sr

    pauses = detect_pauses(data, sr)

    locations = {"beginning": 0, "middle": 0, "end": 0}
    durations = []
    for p in pauses:
        locations[p["location"]] += 1
        durations.append(p["duration_ms"])

    result = {
        "file": os.path.basename(wav_path),
        "audio_duration_s": round(audio_duration_s, 3),
        "pause_count": len(pauses),
        "pauses": pauses,
        "pause_locations": locations,
    }

    if durations:
        result.update({
            "total_pause_duration_ms": round(sum(durations), 1),
            "mean_pause_ms": round(float(np.mean(durations)), 1),
            "max_pause_ms": round(max(durations), 1),
            "min_pause_ms": round(min(durations), 1),
            "pause_rate_per_second": round(len(pauses) / audio_duration_s, 3),
        })
    else:
        result.update({
            "total_pause_duration_ms": 0.0,
            "mean_pause_ms": 0.0,
            "max_pause_ms": 0.0,
            "min_pause_ms": 0.0,
            "pause_rate_per_second": 0.0,
        })

    return result


def compute_pause_corpus_summary(per_clip: list) -> dict:
    """Compute corpus-wide pause aggregates."""
    counts = [c["pause_count"] for c in per_clip]
    mean_pauses = [c["mean_pause_ms"] for c in per_clip if c["pause_count"] > 0]

    # Duration histogram buckets
    all_durations = []
    all_locations = {"beginning": 0, "middle": 0, "end": 0}
    for c in per_clip:
        for p in c["pauses"]:
            all_durations.append(p["duration_ms"])
        for loc in ("beginning", "middle", "end"):
            all_locations[loc] += c["pause_locations"][loc]

    histogram = {
        "100-200ms": 0,
        "200-400ms": 0,
        "400-600ms": 0,
        "600-800ms": 0,
        "800ms+": 0,
    }
    for d in all_durations:
        if d < 200:
            histogram["100-200ms"] += 1
        elif d < 400:
            histogram["200-400ms"] += 1
        elif d < 600:
            histogram["400-600ms"] += 1
        elif d < 800:
            histogram["600-800ms"] += 1
        else:
            histogram["800ms+"] += 1

    summary = {
        "clip_count": len(per_clip),
        "total_pauses": len(all_durations),
        "mean_pause_count": round(float(np.mean(counts)), 2),
        "pause_count_std": round(float(np.std(counts)), 2),
        "duration_histogram": histogram,
        "pause_locations": all_locations,
    }

    if mean_pauses:
        summary["mean_pause_ms"] = round(float(np.mean(mean_pauses)), 1)
        summary["mean_pause_ms_std"] = round(float(np.std(mean_pauses)), 1)

    if all_durations:
        summary["overall_mean_duration_ms"] = round(float(np.mean(all_durations)), 1)
        summary["overall_min_duration_ms"] = round(min(all_durations), 1)
        summary["overall_max_duration_ms"] = round(max(all_durations), 1)
        total_audio = sum(c["audio_duration_s"] for c in per_clip)
        summary["mean_pause_rate_per_second"] = round(len(all_durations) / total_audio, 3) if total_audio > 0 else 0.0

    return summary


def generate_report(input_dir: Path, pause_data: dict, report_path: str):
    """Generate combined baseline report merging F0 and pause analyses."""
    f0_path = input_dir / "f0_analysis.json"
    if not f0_path.exists():
        print(f"Warning: F0 analysis not found at {f0_path}, report will skip F0 section")
        f0_data = None
    else:
        with open(f0_path) as f:
            f0_data = json.load(f)

    # Read corpus metadata for total duration
    meta_path = input_dir / "corpus_metadata.json"
    total_duration_s = 0.0
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        total_duration_s = sum(c.get("duration_s", 0) for c in meta)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    clip_count = pause_data["corpus_summary"]["clip_count"]

    lines = []
    lines.append("# Baseline Measurement Report")
    lines.append(f"Generated: {timestamp}")
    lines.append("Model: Fish Speech S2-Pro (reference: archie, 17.27s clip)")
    lines.append(f"Corpus: {clip_count} clips ({total_duration_s:.1f}s total text, "
                 f"{sum(c['audio_duration_s'] for c in pause_data['per_clip']):.1f}s total audio)")
    lines.append("")

    # F0 Statistics section
    if f0_data:
        cs = f0_data["corpus_summary"]
        lines.append("## F0 Statistics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Mean F0 (across clips) | {cs['f0_mean_across_clips_hz']:.1f} Hz (+/- {cs['f0_mean_std_hz']:.1f}) |")
        lines.append(f"| Mean F0 Std Dev | {cs['f0_std_across_clips_hz']:.1f} Hz (+/- {cs['f0_std_std_hz']:.1f}) |")
        lines.append(f"| Mean CV | {cs['mean_cv']:.4f} |")
        shapes = cs["contour_shapes"]
        lines.append(f"| Contour shapes | {shapes['flat']} flat, {shapes['moderate']} moderate, {shapes['expressive']} expressive |")
        lines.append("")

        lines.append("### Per-Clip F0")
        lines.append("")
        lines.append("| Clip | F0 Mean (Hz) | F0 Std (Hz) | CV | Shape |")
        lines.append("|------|--------------|-------------|-----|-------|")
        for clip in f0_data["per_clip"]:
            name = clip["file"].replace(".wav", "")
            lines.append(
                f"| {name} | {clip['f0_mean_hz']:.1f} | {clip['f0_std_hz']:.1f} | "
                f"{clip['f0_cv']:.3f} | {clip['f0_contour_shape']} |"
            )
        lines.append("")

    # Pause Distribution section
    ps = pause_data["corpus_summary"]
    lines.append("## Pause Distribution")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean pause count per clip | {ps['mean_pause_count']:.1f} (+/- {ps['pause_count_std']:.1f}) |")
    if "mean_pause_ms" in ps:
        lines.append(f"| Mean pause duration | {ps['mean_pause_ms']:.0f}ms (+/- {ps.get('mean_pause_ms_std', 0):.0f}ms) |")
    if "overall_min_duration_ms" in ps:
        lines.append(f"| Pause duration range | {ps['overall_min_duration_ms']:.0f}ms - {ps['overall_max_duration_ms']:.0f}ms |")
    if "mean_pause_rate_per_second" in ps:
        lines.append(f"| Mean pause rate | {ps['mean_pause_rate_per_second']:.3f} per second of audio |")
    lines.append("")

    # Duration histogram
    lines.append("### Duration Histogram")
    lines.append("")
    lines.append("| Range | Count | % |")
    lines.append("|-------|-------|---|")
    hist = ps["duration_histogram"]
    total_pauses = ps["total_pauses"]
    for bucket, count in hist.items():
        pct = (count / total_pauses * 100) if total_pauses > 0 else 0
        lines.append(f"| {bucket} | {count} | {pct:.0f}% |")
    lines.append("")

    # Pause locations
    lines.append("### Pause Locations")
    lines.append("")
    lines.append("| Location | Count | % |")
    lines.append("|----------|-------|---|")
    locs = ps["pause_locations"]
    total_locs = sum(locs.values())
    for loc_name, display in [("beginning", "Beginning (first 10%)"), ("middle", "Middle (10-90%)"), ("end", "End (last 10%)")]:
        count = locs[loc_name]
        pct = (count / total_locs * 100) if total_locs > 0 else 0
        lines.append(f"| {display} | {count} | {pct:.0f}% |")
    lines.append("")

    # Per-clip pauses table
    lines.append("### Per-Clip Pauses")
    lines.append("")
    lines.append("| Clip | Count | Mean (ms) | Max (ms) | Total (ms) |")
    lines.append("|------|-------|-----------|----------|------------|")
    for clip in pause_data["per_clip"]:
        name = clip["file"].replace(".wav", "")
        lines.append(
            f"| {name} | {clip['pause_count']} | {clip['mean_pause_ms']:.0f} | "
            f"{clip['max_pause_ms']:.0f} | {clip['total_pause_duration_ms']:.0f} |"
        )
    lines.append("")

    # Key observations
    lines.append("## Key Observations")
    lines.append("")
    if f0_data:
        mean_cv = f0_data["corpus_summary"]["mean_cv"]
        if mean_cv < 0.10:
            cv_desc = "flat -- limited pitch variation, may sound monotone"
        elif mean_cv <= 0.25:
            cv_desc = "moderate -- reasonable variation but room for more expressiveness"
        else:
            cv_desc = "expressive -- good pitch variation"
        lines.append(f"- **F0 variation:** Mean CV={mean_cv:.3f} ({cv_desc})")
        shapes = f0_data["corpus_summary"]["contour_shapes"]
        lines.append(f"- **Contour distribution:** {shapes['flat']} flat, {shapes['moderate']} moderate, "
                     f"{shapes['expressive']} expressive -- "
                     f"{'most clips show moderate variation, suggesting the model has basic prosody but lacks highly expressive speech' if shapes['moderate'] > shapes['expressive'] else 'good mix of expressiveness'}")

    # Pause behavior observations
    if total_pauses > 0:
        dominant_bucket = max(hist.items(), key=lambda x: x[1])
        lines.append(f"- **Pause behavior:** {total_pauses} pauses detected across {clip_count} clips. "
                     f"Most common duration: {dominant_bucket[0]} ({dominant_bucket[1]} pauses, "
                     f"{dominant_bucket[1]/total_pauses*100:.0f}%)")
        if locs["end"] > locs["beginning"]:
            lines.append("- **Pause placement:** More pauses at end of clips than beginning -- "
                         "may indicate trailing silence in TTS output")
        elif locs["middle"] > (locs["beginning"] + locs["end"]):
            lines.append("- **Pause placement:** Most pauses in middle of clips -- "
                         "natural inter-clause pausing detected")
    else:
        lines.append("- **Pause behavior:** No pauses >= 100ms detected -- model produces continuous speech "
                     "without natural pausing")

    lines.append("- These metrics serve as the regression baseline for Phase 2-5 A/B comparisons")
    lines.append("")

    # Files section
    lines.append("## Files")
    lines.append("")
    lines.append("- F0 data: f0_analysis.json")
    lines.append("- Pause data: pause_analysis.json")
    lines.append("- Audio: /home/prana/tts-test/outputs/baseline_corpus/*.wav")
    lines.append("")

    report_text = "\n".join(lines)
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"Report saved to {report_path} ({len(report_text)} chars)")


def main():
    parser = argparse.ArgumentParser(description="Pause distribution analysis for TTS corpus")
    parser.add_argument(
        "--input-dir",
        default="/home/prana/tts-test/outputs/baseline_corpus",
        help="Directory containing WAV files to analyze",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: pause_analysis.json in input dir)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Also generate combined baseline_report.md",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or str(input_dir / "pause_analysis.json")

    wav_files = sorted(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"Error: no WAV files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing pauses for {len(wav_files)} WAV files in {input_dir}")
    print(f"Minimum pause duration: 100ms")
    print()

    per_clip = []
    for wav_path in wav_files:
        print(f"  Processing {wav_path.name}...", end=" ", flush=True)
        result = analyze_clip_pauses(str(wav_path))
        per_clip.append(result)
        print(
            f"{result['pause_count']} pauses, "
            f"mean={result['mean_pause_ms']:.0f}ms, "
            f"total={result['total_pause_duration_ms']:.0f}ms"
        )

    corpus_summary = compute_pause_corpus_summary(per_clip)

    output_data = {
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_rate": 44100,
        "frame_ms": 10.0,
        "min_pause_ms": 100.0,
        "per_clip": per_clip,
        "corpus_summary": corpus_summary,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\nSaved pause analysis to {output_path}")

    # Print summary
    cs = corpus_summary
    print(f"\n--- Corpus Pause Summary ({cs['clip_count']} clips) ---")
    print(f"  Total pauses: {cs['total_pauses']}")
    print(f"  Mean per clip: {cs['mean_pause_count']:.1f} (+/- {cs['pause_count_std']:.1f})")
    if "mean_pause_ms" in cs:
        print(f"  Mean duration: {cs['mean_pause_ms']:.0f}ms (+/- {cs.get('mean_pause_ms_std', 0):.0f}ms)")
    print(f"  Histogram: {cs['duration_histogram']}")
    print(f"  Locations: {cs['pause_locations']}")

    if args.report:
        report_path = str(input_dir / "baseline_report.md")
        print(f"\nGenerating combined baseline report...")
        generate_report(input_dir, output_data, report_path)


if __name__ == "__main__":
    main()
