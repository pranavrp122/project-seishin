"""Fish Audio S2 Pro: 5 clips via streaming API using master_seed.wav as reference."""
import os, time, struct
from pathlib import Path

os.environ["HF_HUB_DISABLE_XET"] = "1"

import requests
import ormsgpack
import soundfile as sf
import numpy as np

OUT_DIR = Path("/home/prana/tts-test/outputs/s2pro_streaming")
HF_REPO = "EternalFlame549/archie-voice-test-clips"
HF_TOKEN = os.environ.get("HF_TOKEN", "")
API_URL = "http://127.0.0.1:8080/v1/tts"
REFERENCE_ID = "archie"  # Pre-registered reference, avoids re-encoding VQ each request

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

results = []
for text, name in PROMPTS:
    print(f"  {name}: {text[:70]}...")
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
    }

    response = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        stream=True,
        timeout=120,
    )

    if response.status_code != 200:
        print(f"  ERROR {response.status_code}: {response.text[:200]}")
        continue

    # Collect streamed audio
    raw_bytes = b""
    for chunk in response.iter_content(chunk_size=8192):
        if t_first is None and len(raw_bytes) > 44:
            t_first = time.time()
        raw_bytes += chunk

    # Strip the streaming WAV header (44 bytes with 0xFFFFFFFF sizes)
    # and write a proper WAV file with correct sizes
    pcm_data = raw_bytes[44:]  # skip streaming header
    out_path = OUT_DIR / f"s2pro_streaming_{name}.wav"

    # Write proper WAV with soundfile
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(str(out_path), samples, 44100, format="wav")

    dur = len(samples) / 44100.0
    ttfa = (t_first - t0) if t_first else (time.time() - t0)
    total = time.time() - t0
    print(f"    -> {dur:.1f}s audio, TTFA {ttfa*1000:.0f}ms, total {total:.1f}s")
    results.append(str(out_path))

print(f"\nGenerated {len(results)}/5 streaming clips")
print("\nUploading to HuggingFace...")

from huggingface_hub import HfApi, create_repo
api = HfApi(token=HF_TOKEN)
create_repo(HF_REPO, token=HF_TOKEN, repo_type="dataset", exist_ok=True)
for fpath in results:
    p = Path(fpath)
    api.upload_file(
        path_or_fileobj=str(p),
        path_in_repo=f"model_comparison/s2pro_streaming/{p.name}",
        repo_id=HF_REPO,
        repo_type="dataset",
        token=HF_TOKEN,
    )
    print(f"  uploaded {p.name}")

print(f"\nDone: https://huggingface.co/datasets/{HF_REPO}/tree/main/model_comparison/s2pro_streaming")
