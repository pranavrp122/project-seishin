"""Fish Audio S2 Pro: 5 clips via local API server using master_seed.wav as reference."""
import os, time, base64
from pathlib import Path

os.environ["HF_HUB_DISABLE_XET"] = "1"

import requests
import ormsgpack
import soundfile as sf
import numpy as np

REF_AUDIO = Path("/home/prana/project-seishin/dataset_pipeline/master_seed.wav")
REF_TEXT  = "Beautiful flowers always have thorns, and as for feeling protective... I sometimes get consumed by that, too. But I know that she's a softie deep down. After all, she and March are flowers that bloomed from the same seed."
OUT_DIR   = Path("/home/prana/tts-test/outputs/s2pro")
HF_REPO   = "EternalFlame549/archie-voice-test-clips"
HF_TOKEN  = "REDACTED_HF_TOKEN"
API_URL   = "http://127.0.0.1:8080/v1/tts"

# S2 Pro uses inline [tag] for emotion
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

# Load reference audio as bytes
ref_audio_bytes = REF_AUDIO.read_bytes()

results = []
for text, name in PROMPTS:
    print(f"  {name}: {text[:70]}...")
    t0 = time.time()

    payload = {
        "text": text,
        "references": [
            {
                "audio": ref_audio_bytes,
                "text": REF_TEXT,
            }
        ],
        "format": "wav",
        "temperature": 0.7,
        "top_p": 0.8,
        "repetition_penalty": 1.2,
        "max_new_tokens": 1024,
        "chunk_length": 200,
        "streaming": False,
    }

    response = requests.post(
        API_URL,
        data=ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        headers={"Content-Type": "application/msgpack", "Accept": "audio/wav"},
        timeout=120,
    )

    if response.status_code != 200:
        print(f"  ERROR {response.status_code}: {response.text[:200]}")
        continue

    out_path = OUT_DIR / f"s2pro_{name}.wav"
    out_path.write_bytes(response.content)

    # Get duration
    data, sr = sf.read(str(out_path))
    dur = len(data) / sr
    print(f"    -> {dur:.1f}s in {time.time()-t0:.1f}s")
    results.append(str(out_path))

print(f"\nGenerated {len(results)}/5 clips")
print("\nUploading to HuggingFace...")

from huggingface_hub import HfApi, create_repo
api = HfApi(token=HF_TOKEN)
create_repo(HF_REPO, token=HF_TOKEN, repo_type="dataset", exist_ok=True)
for fpath in results:
    p = Path(fpath)
    api.upload_file(
        path_or_fileobj=str(p),
        path_in_repo=f"model_comparison/s2pro/{p.name}",
        repo_id=HF_REPO,
        repo_type="dataset",
        token=HF_TOKEN,
    )
    print(f"  uploaded {p.name}")

print(f"\nDone: https://huggingface.co/datasets/{HF_REPO}/tree/main/model_comparison/s2pro")
