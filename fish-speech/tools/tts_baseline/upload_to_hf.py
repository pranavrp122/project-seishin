#!/usr/bin/env python3
"""Upload baseline and adversarial corpora to HuggingFace.

Usage:
    python tools/tts_baseline/upload_to_hf.py
"""
import os

# Disable xet storage backend (workaround for root-owned xet cache dir)
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'
os.environ['HF_HUB_DISABLE_XET'] = '1'

from pathlib import Path
from huggingface_hub import HfApi

REPO_ID = "EternalFlame549/project-seishin-data"
BASE_DIR = Path("/home/prana/tts-test/outputs")

UPLOADS = [
    ("baseline_corpus", "humanism_baseline/baseline_corpus"),
    ("adversarial_corpus", "humanism_baseline/adversarial_corpus"),
]

def main():
    os.makedirs("/tmp/hf_xet_logs", exist_ok=True)
    api = HfApi()
    for local_name, remote_path in UPLOADS:
        local_path = BASE_DIR / local_name
        if not local_path.exists():
            print(f"SKIP: {local_path} does not exist")
            continue
        print(f"Uploading {local_path} -> {REPO_ID}/{remote_path} ...")
        result = api.upload_folder(
            folder_path=str(local_path),
            path_in_repo=remote_path,
            repo_id=REPO_ID,
            repo_type="dataset",
        )
        print(f"  Done: {result}")
    print("All uploads complete.")

if __name__ == "__main__":
    main()
