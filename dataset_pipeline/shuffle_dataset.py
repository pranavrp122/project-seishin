"""
Shuffle dataset pairs from audio/ into audio_shuffled/.
Copies all WAV+LAB pairs with random.seed(42), renaming them
so shuffled index i maps to original file at shuffled_order[i].
Two-pass approach: copy with temp names, then rename to final names.
"""

import random
import shutil
from pathlib import Path

SRC = Path(__file__).parent / "audio"
DST = Path(__file__).parent / "audio_shuffled"
SEED = 42

def main():
    DST.mkdir(exist_ok=True)

    # Collect all WAV files (LAB pairs assumed to exist)
    wav_files = sorted(SRC.glob("*.wav"))
    total = len(wav_files)
    print(f"Found {total} WAV files in {SRC}")

    # Build shuffled order
    indices = list(range(total))
    random.seed(SEED)
    random.shuffle(indices)

    # Pass 1: copy with temp names to avoid collisions
    print("Pass 1: copying to temp names...")
    for new_idx, orig_idx in enumerate(indices):
        orig_wav = wav_files[orig_idx]
        orig_lab = orig_wav.with_suffix(".lab")
        tmp_wav = DST / f"tmp_{new_idx:04d}.wav"
        tmp_lab = DST / f"tmp_{new_idx:04d}.lab"
        shutil.copy2(orig_wav, tmp_wav)
        if orig_lab.exists():
            shutil.copy2(orig_lab, tmp_lab)
        if (new_idx + 1) % 1000 == 0:
            print(f"  {new_idx+1}/{total}", flush=True)

    # Pass 2: rename tmp_ to final names
    print("Pass 2: renaming to final names...")
    for new_idx in range(total):
        tmp_wav = DST / f"tmp_{new_idx:04d}.wav"
        tmp_lab = DST / f"tmp_{new_idx:04d}.lab"
        final_wav = DST / f"{new_idx+1:04d}.wav"
        final_lab = DST / f"{new_idx+1:04d}.lab"
        tmp_wav.rename(final_wav)
        if tmp_lab.exists():
            tmp_lab.rename(final_lab)

    wav_count = len(list(DST.glob("*.wav")))
    lab_count = len(list(DST.glob("*.lab")))
    print(f"\nDone. {wav_count} WAVs, {lab_count} LABs in {DST}")
    print(f"Seed: {SEED}")

if __name__ == "__main__":
    main()
