"""Test sub-chunk audio streaming vs baseline streaming."""
import time, struct
from pathlib import Path

import requests
import ormsgpack
import soundfile as sf
import numpy as np

OUT_DIR = Path("/home/prana/tts-test/outputs/subchunk_test")
API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"

PROMPTS = [
    ("[warm] I left the hallway light on because I know you're coming home late and I didn't want you walking into darkness.",
     "01_warm"),
    ("[exhausted] I forgot what day it is. I forgot what I ate for breakfast. I am running on autopilot. The autopilot is also exhausted and requesting permission to land immediately.",
     "02_exhausted"),
    ("[angry] Don't patronize me with that tone, I can hear it from here!",
     "03_angry"),
    ("[tender] Some mornings I wake up and just look at the ceiling feeling truly grateful that my life has you woven through every part.",
     "04_tender"),
    ("[professional] The lack of structured logging across our services makes incident investigation significantly harder. It is adding at least twenty minutes to our mean time to detect.",
     "05_professional"),
]

OUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_clip(text, name, sub_chunk_tokens, label):
    print(f"  [{label}] {name}: {text[:60]}...")
    t0 = time.time()
    t_first = None

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
        "sub_chunk_tokens": sub_chunk_tokens,
    }

    response = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        stream=True,
        timeout=120,
    )

    if response.status_code != 200:
        print(f"    ERROR {response.status_code}: {response.text[:200]}")
        return None

    raw_bytes = b""
    for chunk in response.iter_content(chunk_size=None):
        raw_bytes += chunk
        if t_first is None and len(raw_bytes) > 44:
            t_first = time.time()

    pcm_data = raw_bytes[44:]
    out_path = OUT_DIR / f"{label}_{name}.wav"
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(str(out_path), samples, 44100, format="wav")

    dur = len(samples) / 44100.0
    ttfa = (t_first - t0) if t_first else (time.time() - t0)
    total = time.time() - t0
    print(f"    -> {dur:.1f}s audio, TTFA {ttfa*1000:.0f}ms, total {total:.1f}s")
    return {"name": name, "label": label, "dur": dur, "ttfa_ms": ttfa * 1000, "total": total, "path": str(out_path)}


print("=" * 60)
print("SUB-CHUNK STREAMING TEST (sub_chunk_tokens=10)")
print("=" * 60)
subchunk_results = []
for text, name in PROMPTS:
    r = generate_clip(text, name, sub_chunk_tokens=10, label="subchunk")
    if r:
        subchunk_results.append(r)

print()
print("=" * 60)
print("BASELINE STREAMING TEST (sub_chunk_tokens=0)")
print("=" * 60)
baseline_results = []
for text, name in PROMPTS:
    r = generate_clip(text, name, sub_chunk_tokens=0, label="baseline")
    if r:
        baseline_results.append(r)

print()
print("=" * 60)
print("COMPARISON")
print("=" * 60)
print(f"{'Clip':<20} {'Sub-chunk TTFA':>15} {'Baseline TTFA':>15} {'Speedup':>10}")
print("-" * 60)
for sc, bl in zip(subchunk_results, baseline_results):
    speedup = bl["ttfa_ms"] / sc["ttfa_ms"] if sc["ttfa_ms"] > 0 else 0
    print(f"{sc['name']:<20} {sc['ttfa_ms']:>12.0f}ms {bl['ttfa_ms']:>12.0f}ms {speedup:>9.1f}x")

avg_sc = sum(r["ttfa_ms"] for r in subchunk_results) / len(subchunk_results) if subchunk_results else 0
avg_bl = sum(r["ttfa_ms"] for r in baseline_results) / len(baseline_results) if baseline_results else 0
print("-" * 60)
print(f"{'AVERAGE':<20} {avg_sc:>12.0f}ms {avg_bl:>12.0f}ms {avg_bl/avg_sc if avg_sc > 0 else 0:>9.1f}x")
print(f"\nOutput: {OUT_DIR}")
