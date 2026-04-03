#!/home/prana/fish-speech/fish_env/bin/python
"""Generate test audio samples by sending requests to a local Fish Audio S2 Pro API server.

Reads test_batch.json for test sentences, uses master_seed.wav/txt as reference,
and saves generated WAV files to test_audio/.
"""

import json
import sys
import time
from pathlib import Path

import ormsgpack
import requests

# Add fish-speech to path for schema imports
sys.path.insert(0, "/home/prana/fish-speech")
from fish_speech.utils.schema import ServeReferenceAudio, ServeTTSRequest

API_URL = "http://127.0.0.1:8080/v1/tts"
TIMEOUT = 120


def load_inputs(base_dir: Path) -> tuple[list[dict], bytes, str]:
    """Load test batch, reference audio, and reference transcript."""
    batch_path = base_dir / "test_batch.json"
    seed_audio_path = base_dir / "master_seed.wav"
    seed_text_path = base_dir / "master_seed.txt"

    with open(batch_path, "r") as f:
        batch = json.loads(f.read())

    ref_audio = seed_audio_path.read_bytes()
    ref_text = seed_text_path.read_text().strip()

    return batch, ref_audio, ref_text


def generate_sample(
    text: str, ref_audio: bytes, ref_text: str
) -> tuple[bytes | None, float]:
    """Send a TTS request and return (wav_bytes, elapsed_seconds)."""
    req = ServeTTSRequest(
        text=text,
        references=[ServeReferenceAudio(audio=ref_audio, text=ref_text)],
        format="wav",
        use_memory_cache="on",
        max_new_tokens=1024,
        temperature=0.8,
        top_p=0.8,
        repetition_penalty=1.1,
    )

    start = time.time()
    response = requests.post(
        API_URL,
        data=ormsgpack.packb(req, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"content-type": "application/msgpack"},
        timeout=TIMEOUT,
    )
    elapsed = time.time() - start

    if response.status_code == 200:
        return response.content, elapsed
    else:
        raise RuntimeError(
            f"HTTP {response.status_code}: {response.text[:200]}"
        )


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    out_dir = base_dir / "test_audio"
    out_dir.mkdir(exist_ok=True)

    batch, ref_audio, ref_text = load_inputs(base_dir)

    print(f"Loaded {len(batch)} test sentences")
    print(f"Reference audio: {len(ref_audio):,} bytes")
    print(f"Reference text:  {ref_text[:60]}...")
    print(f"Output directory: {out_dir}")
    print("-" * 70)

    success = 0
    failed = 0

    for i, item in enumerate(batch, start=1):
        idx = f"{i:03d}"
        category = item["category"]
        tag = item["tag"]
        text = item["text"]
        preview = text[:50] + ("..." if len(text) > 50 else "")
        out_path = out_dir / f"{idx}.wav"

        print(f"\n[{idx}/{len(batch):03d}] cat={category}  tag={tag}")
        print(f"  text: {preview}")

        try:
            wav_bytes, elapsed = generate_sample(text, ref_audio, ref_text)
            out_path.write_bytes(wav_bytes)
            size_kb = len(wav_bytes) / 1024
            print(f"  saved: {out_path.name}  ({size_kb:.1f} KB, {elapsed:.1f}s)")
            success += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Done. {success} succeeded, {failed} failed out of {len(batch)} total.")


if __name__ == "__main__":
    main()
