"""
Phase 5A — Loudness normalization for audio_shuffled/
Normalizes all WAV files to -23 LUFS (EBU R128) in-place.
Logs per-file stats and summary to logs/phase5a_loudness_norm.log
"""

import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

TARGET_LUFS = -23.0
AUDIO_DIR = Path(__file__).parent / "audio_shuffled"
LOG_PATH = Path(__file__).parent / "logs" / "phase5a_loudness_norm.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def normalize_file(path: Path, meter: pyln.Meter) -> tuple[float, float]:
    """Returns (original_lufs, new_lufs). Skips if already within 0.5 LU of target."""
    data, rate = sf.read(str(path))

    # pyloudnorm needs (samples, channels); soundfile returns that by default
    if data.ndim == 1:
        data_2d = data[:, np.newaxis]
    else:
        data_2d = data

    # Need at least 0.4s for ITU-R BS.1770 gating
    if len(data) / rate < 0.4:
        return float("nan"), float("nan")

    loudness = meter.integrated_loudness(data_2d)

    if abs(loudness - TARGET_LUFS) < 0.5:
        return loudness, loudness  # already close enough

    gain_db = TARGET_LUFS - loudness
    gain_linear = 10 ** (gain_db / 20.0)
    normalized = data * gain_linear

    # Clip to [-1, 1] to avoid clipping distortion
    if np.max(np.abs(normalized)) > 1.0:
        peak = np.max(np.abs(normalized))
        normalized = normalized / peak  # peak-limit instead of hard clip

    sf.write(str(path), normalized, rate, subtype="PCM_16")

    # Verify
    data_check, _ = sf.read(str(path))
    if data_check.ndim == 1:
        data_check = data_check[:, np.newaxis]
    new_loudness = meter.integrated_loudness(data_check)

    return loudness, new_loudness


def main():
    wav_files = sorted(AUDIO_DIR.glob("*.wav"))
    total = len(wav_files)
    print(f"Found {total} WAV files in {AUDIO_DIR}", flush=True)

    start = time.time()
    stats = {"skipped_short": 0, "already_ok": 0, "normalized": 0, "errors": 0}
    original_loudnesses = []
    final_loudnesses = []

    with open(LOG_PATH, "w") as log:
        log.write(f"Phase 5A Loudness Normalization\n")
        log.write(f"Target: {TARGET_LUFS} LUFS\n")
        log.write(f"Files: {total}\n")
        log.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write("-" * 60 + "\n")

        for i, path in enumerate(wav_files):
            try:
                # Create meter per-file to handle varying sample rates
                info = sf.info(str(path))
                meter = pyln.Meter(info.samplerate)

                orig_lufs, new_lufs = normalize_file(path, meter)

                if np.isnan(orig_lufs):
                    stats["skipped_short"] += 1
                    log.write(f"SKIP_SHORT {path.name}\n")
                elif orig_lufs == new_lufs:
                    stats["already_ok"] += 1
                    original_loudnesses.append(orig_lufs)
                    final_loudnesses.append(new_lufs)
                    log.write(f"OK {path.name} {orig_lufs:.2f} LUFS\n")
                else:
                    stats["normalized"] += 1
                    original_loudnesses.append(orig_lufs)
                    final_loudnesses.append(new_lufs)
                    log.write(f"NORM {path.name} {orig_lufs:.2f} -> {new_lufs:.2f} LUFS\n")

            except Exception as e:
                stats["errors"] += 1
                log.write(f"ERROR {path.name}: {e}\n")
                traceback.print_exc()

            if (i + 1) % 500 == 0:
                elapsed = time.time() - start
                rate = (i + 1) / elapsed
                eta = (total - i - 1) / rate
                msg = f"Progress: {i+1}/{total} | {rate:.1f} files/s | ETA: {eta:.0f}s"
                print(msg, flush=True)
                log.write(f"# {msg}\n")
                log.flush()

        elapsed = time.time() - start

        summary_lines = [
            "",
            "=" * 60,
            "SUMMARY",
            f"Total files: {total}",
            f"Normalized:  {stats['normalized']}",
            f"Already OK:  {stats['already_ok']}",
            f"Too short:   {stats['skipped_short']}",
            f"Errors:      {stats['errors']}",
            f"Elapsed:     {elapsed:.1f}s",
        ]

        if original_loudnesses:
            summary_lines += [
                f"",
                f"Original loudness stats (LUFS):",
                f"  min={min(original_loudnesses):.2f}  max={max(original_loudnesses):.2f}  mean={np.mean(original_loudnesses):.2f}",
                f"Final loudness stats (LUFS):",
                f"  min={min(final_loudnesses):.2f}  max={max(final_loudnesses):.2f}  mean={np.mean(final_loudnesses):.2f}",
            ]

        for line in summary_lines:
            print(line)
            log.write(line + "\n")

    print(f"\nLog saved to: {LOG_PATH}")


if __name__ == "__main__":
    main()
