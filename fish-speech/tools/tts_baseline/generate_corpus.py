#!/usr/bin/env python3
"""Generate baseline and adversarial audio corpora from Fish Speech TTS API.

Produces WAV files for each prompt in prompts.json, along with per-corpus
metadata capturing timing and audio statistics. Reusable across phases for
regeneration after pipeline changes.

Usage:
    python tools/tts_baseline/generate_corpus.py --corpus all
    python tools/tts_baseline/generate_corpus.py --corpus baseline --output-dir /custom/path
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import ormsgpack
import requests
import soundfile as sf

API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"
SAMPLE_RATE = 44100
DEFAULT_OUTPUT_DIR = "/home/prana/tts-test/outputs"

# Shared TTS parameters matching existing test_subchunk.py baseline
TTS_PARAMS = {
    "reference_id": REFERENCE_ID,
    "format": "wav",
    "temperature": 0.7,
    "top_p": 0.8,
    "repetition_penalty": 1.2,
    "max_new_tokens": 1024,
    "chunk_length": 200,
    "streaming": True,
}


def load_prompts(prompts_path: str) -> dict:
    """Load prompt definitions from JSON file."""
    with open(prompts_path, "r") as f:
        return json.load(f)


def generate_clip(prompt: dict, output_path: Path) -> dict | None:
    """Generate a single TTS clip via the Fish Speech API.

    Returns metadata dict on success, None on failure.
    """
    text = prompt["text"]
    clip_id = prompt["id"]
    category = prompt["category"]

    print(f"  [{clip_id}] {category}: {text[:70]}...")

    payload = {**TTS_PARAMS, "text": text}
    packed = ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC)

    t0 = time.time()
    t_first = None

    try:
        response = requests.post(
            API_URL,
            data=packed,
            headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
            stream=True,
            timeout=120,
        )
    except requests.exceptions.RequestException as e:
        print(f"    ERROR: Connection failed: {e}")
        return None

    if response.status_code != 200:
        print(f"    ERROR {response.status_code}: {response.text[:200]}")
        return None

    raw_bytes = b""
    for chunk in response.iter_content(chunk_size=None):
        raw_bytes += chunk
        if t_first is None and len(raw_bytes) > 44:
            t_first = time.time()

    # Extract PCM data after 44-byte WAV header
    pcm_data = raw_bytes[44:]
    if len(pcm_data) == 0:
        print(f"    ERROR: Empty PCM data for {clip_id}")
        return None

    # Convert int16 PCM to float32 and write WAV
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    wav_path = output_path / f"{clip_id}_{category}.wav"
    sf.write(str(wav_path), samples, SAMPLE_RATE, format="wav")

    duration_s = len(samples) / SAMPLE_RATE
    ttfa_ms = ((t_first - t0) * 1000) if t_first else ((time.time() - t0) * 1000)
    total_s = time.time() - t0

    print(f"    -> {duration_s:.1f}s audio, TTFA {ttfa_ms:.0f}ms, total {total_s:.1f}s, saved {wav_path}")

    return {
        "id": clip_id,
        "category": category,
        "text": text,
        "duration_s": round(duration_s, 3),
        "ttfa_ms": round(ttfa_ms, 1),
        "total_s": round(total_s, 3),
        "sample_rate": SAMPLE_RATE,
        "num_samples": len(samples),
        "file": wav_path.name,
    }


def generate_corpus(corpus_name: str, prompts: list[dict], output_dir: Path) -> list[dict]:
    """Generate all clips for a named corpus, returning metadata list."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 60}")
    print(f"Generating {corpus_name} corpus ({len(prompts)} prompts)")
    print(f"Output: {output_dir}")
    print(f"{'=' * 60}")

    metadata = []
    for prompt in prompts:
        result = generate_clip(prompt, output_dir)
        if result:
            metadata.append(result)
        else:
            print(f"    SKIPPED: {prompt['id']} (generation failed)")

    # Save corpus metadata
    meta_path = output_dir / "corpus_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"\nSaved metadata: {meta_path} ({len(metadata)} clips)")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio corpora")
    parser.add_argument(
        "--corpus",
        choices=["baseline", "adversarial", "postfx", "all"],
        default="all",
        help="Which corpus to generate (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    # Locate prompts.json relative to this script
    script_dir = Path(__file__).resolve().parent
    prompts_path = script_dir / "prompts.json"
    if not prompts_path.exists():
        print(f"ERROR: prompts.json not found at {prompts_path}")
        sys.exit(1)

    prompts = load_prompts(str(prompts_path))
    base_dir = Path(args.output_dir)
    all_metadata = {}

    if args.corpus in ("baseline", "all"):
        meta = generate_corpus(
            "baseline",
            prompts["baseline"],
            base_dir / "baseline_corpus",
        )
        all_metadata["baseline"] = meta

    if args.corpus in ("adversarial", "all"):
        meta = generate_corpus(
            "adversarial",
            prompts["adversarial"],
            base_dir / "adversarial_corpus",
        )
        all_metadata["adversarial"] = meta

    if args.corpus in ("postfx", "all"):
        meta = generate_corpus(
            "postfx",
            prompts["baseline"],  # Same prompts as baseline for A/B comparison
            base_dir / "postfx_corpus",
        )
        all_metadata["postfx"] = meta

    # Summary
    print(f"\n{'=' * 60}")
    print("GENERATION COMPLETE")
    print(f"{'=' * 60}")
    for name, meta in all_metadata.items():
        if meta:
            avg_ttfa = sum(m["ttfa_ms"] for m in meta) / len(meta)
            avg_dur = sum(m["duration_s"] for m in meta) / len(meta)
            total_dur = sum(m["duration_s"] for m in meta)
            print(f"  {name}: {len(meta)} clips, avg TTFA {avg_ttfa:.0f}ms, avg dur {avg_dur:.1f}s, total {total_dur:.1f}s")


if __name__ == "__main__":
    main()
