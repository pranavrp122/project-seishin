#!/usr/bin/env python3
"""F0 pitch analysis for TTS baseline corpus using pyworld DIO + StoneMask.

Computes per-clip and corpus-wide F0 statistics including voiced ratio,
mean/std/min/max F0, coefficient of variation, and contour shape classification.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyworld as pw
import soundfile as sf


def classify_contour(cv: float) -> str:
    """Classify F0 contour shape by coefficient of variation."""
    if cv < 0.10:
        return "flat"
    elif cv <= 0.25:
        return "moderate"
    else:
        return "expressive"


def analyze_clip(wav_path: str, frame_period: float = 5.0) -> dict:
    """Analyze F0 for a single WAV file using pyworld DIO + StoneMask.

    Args:
        wav_path: Path to WAV file (expects 44100Hz)
        frame_period: Frame period in milliseconds for DIO extraction

    Returns:
        Dictionary of per-clip F0 statistics
    """
    data, sr = sf.read(wav_path)
    data = data.astype(np.float64)

    # Extract F0 with DIO then refine with StoneMask
    f0, timeaxis = pw.dio(data, sr, frame_period=frame_period)
    f0 = pw.stonemask(data, f0, timeaxis, sr)

    # Separate voiced frames (F0 > 0)
    voiced_f0 = f0[f0 > 0]
    total_frames = len(f0)
    voiced_frames = len(voiced_f0)

    if voiced_frames == 0:
        return {
            "file": os.path.basename(wav_path),
            "voiced_frames": 0,
            "total_frames": total_frames,
            "voiced_ratio": 0.0,
            "f0_mean_hz": 0.0,
            "f0_std_hz": 0.0,
            "f0_min_hz": 0.0,
            "f0_max_hz": 0.0,
            "f0_range_hz": 0.0,
            "f0_cv": 0.0,
            "f0_contour_shape": "flat",
        }

    f0_mean = float(np.mean(voiced_f0))
    f0_std = float(np.std(voiced_f0))
    f0_min = float(np.min(voiced_f0))
    f0_max = float(np.max(voiced_f0))
    f0_cv = f0_std / f0_mean if f0_mean > 0 else 0.0

    return {
        "file": os.path.basename(wav_path),
        "voiced_frames": int(voiced_frames),
        "total_frames": int(total_frames),
        "voiced_ratio": round(voiced_frames / total_frames, 4),
        "f0_mean_hz": round(f0_mean, 2),
        "f0_std_hz": round(f0_std, 2),
        "f0_min_hz": round(f0_min, 2),
        "f0_max_hz": round(f0_max, 2),
        "f0_range_hz": round(f0_max - f0_min, 2),
        "f0_cv": round(f0_cv, 4),
        "f0_contour_shape": classify_contour(f0_cv),
    }


def compute_corpus_summary(per_clip: list) -> dict:
    """Compute corpus-wide F0 aggregates from per-clip results."""
    # Filter out clips with no voiced frames
    voiced_clips = [c for c in per_clip if c["voiced_frames"] > 0]
    if not voiced_clips:
        return {
            "clip_count": len(per_clip),
            "voiced_clip_count": 0,
            "f0_mean_across_clips_hz": 0.0,
            "f0_mean_std_hz": 0.0,
            "f0_std_across_clips_hz": 0.0,
            "f0_std_std_hz": 0.0,
            "mean_cv": 0.0,
            "contour_shapes": {"flat": 0, "moderate": 0, "expressive": 0},
        }

    means = np.array([c["f0_mean_hz"] for c in voiced_clips])
    stds = np.array([c["f0_std_hz"] for c in voiced_clips])
    cvs = np.array([c["f0_cv"] for c in voiced_clips])

    shapes = {"flat": 0, "moderate": 0, "expressive": 0}
    for c in voiced_clips:
        shapes[c["f0_contour_shape"]] += 1

    return {
        "clip_count": len(per_clip),
        "voiced_clip_count": len(voiced_clips),
        "f0_mean_across_clips_hz": round(float(np.mean(means)), 2),
        "f0_mean_std_hz": round(float(np.std(means)), 2),
        "f0_std_across_clips_hz": round(float(np.mean(stds)), 2),
        "f0_std_std_hz": round(float(np.std(stds)), 2),
        "mean_cv": round(float(np.mean(cvs)), 4),
        "contour_shapes": shapes,
    }


def main():
    parser = argparse.ArgumentParser(description="F0 pitch analysis for TTS corpus")
    parser.add_argument(
        "--input-dir",
        default="/home/prana/tts-test/outputs/baseline_corpus",
        help="Directory containing WAV files to analyze",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: f0_analysis.json in input dir)",
    )
    parser.add_argument(
        "--frame-period",
        type=float,
        default=5.0,
        help="Frame period in ms for DIO extraction (default: 5.0)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or str(input_dir / "f0_analysis.json")

    # Find all WAV files, sorted for reproducibility
    wav_files = sorted(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"Error: no WAV files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing F0 for {len(wav_files)} WAV files in {input_dir}")
    print(f"Frame period: {args.frame_period}ms")
    print()

    per_clip = []
    for wav_path in wav_files:
        print(f"  Processing {wav_path.name}...", end=" ", flush=True)
        result = analyze_clip(str(wav_path), frame_period=args.frame_period)
        per_clip.append(result)
        print(
            f"F0={result['f0_mean_hz']:.1f}Hz, "
            f"std={result['f0_std_hz']:.1f}Hz, "
            f"CV={result['f0_cv']:.3f} ({result['f0_contour_shape']})"
        )

    corpus_summary = compute_corpus_summary(per_clip)

    output_data = {
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_rate": 44100,
        "frame_period_ms": args.frame_period,
        "per_clip": per_clip,
        "corpus_summary": corpus_summary,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\nSaved F0 analysis to {output_path}")

    # Print summary
    cs = corpus_summary
    print(f"\n--- Corpus F0 Summary ({cs['clip_count']} clips) ---")
    print(f"  Mean F0:  {cs['f0_mean_across_clips_hz']:.1f} Hz (+/- {cs['f0_mean_std_hz']:.1f})")
    print(f"  Mean Std: {cs['f0_std_across_clips_hz']:.1f} Hz (+/- {cs['f0_std_std_hz']:.1f})")
    print(f"  Mean CV:  {cs['mean_cv']:.4f}")
    print(f"  Contour shapes: {cs['contour_shapes']}")


if __name__ == "__main__":
    main()
