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


CONFIGS = [
    ("N=5", 5, "n5"),
    ("N=10", 10, "n10"),
    ("Baseline (N=0)", 0, "baseline"),
]

all_results = {}
for config_name, n, label in CONFIGS:
    print("=" * 70)
    print(f"{config_name} (sub_chunk_tokens={n})")
    print("=" * 70)
    all_results[label] = []
    for text, name in PROMPTS:
        r = generate_clip(text, name, sub_chunk_tokens=n, label=label)
        if r:
            all_results[label].append(r)
    print()

print("=" * 70)
print("COMPARISON")
print("=" * 70)
print(f"{'Clip':<20} {'N=5 TTFA':>12} {'N=10 TTFA':>12} {'Baseline':>12} {'N=5 speedup':>12}")
print("-" * 70)
for i in range(len(PROMPTS)):
    n5 = all_results["n5"][i] if i < len(all_results["n5"]) else None
    n10 = all_results["n10"][i] if i < len(all_results["n10"]) else None
    bl = all_results["baseline"][i] if i < len(all_results["baseline"]) else None
    if n5 and n10 and bl:
        speedup = bl["ttfa_ms"] / n5["ttfa_ms"] if n5["ttfa_ms"] > 0 else 0
        print(f"{n5['name']:<20} {n5['ttfa_ms']:>9.0f}ms {n10['ttfa_ms']:>9.0f}ms {bl['ttfa_ms']:>9.0f}ms {speedup:>11.1f}x")

for label in ["n5", "n10", "baseline"]:
    results = all_results[label]
    avg = sum(r["ttfa_ms"] for r in results) / len(results) if results else 0
    all_results[f"{label}_avg"] = avg

print("-" * 70)
print(f"{'AVERAGE':<20} {all_results['n5_avg']:>9.0f}ms {all_results['n10_avg']:>9.0f}ms {all_results['baseline_avg']:>9.0f}ms {all_results['baseline_avg']/all_results['n5_avg'] if all_results['n5_avg'] > 0 else 0:>11.1f}x")
print(f"\nOutput: {OUT_DIR}")
