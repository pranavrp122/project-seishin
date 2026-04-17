"""Parakeet TDT 0.6b v2 ASR server, whisper-server compatible.

Drop-in replacement for whisper-server. Accepts POST /inference with a multipart
WAV file, returns {"text": "..."}. sei_engine.py's transcribe_audio() calls this
without modification.

Usage: python parakeet_server.py (via scripts/start_parakeet.sh which sets env).
"""
import io
import os
import time
import asyncio
import tempfile

import torch
# Match ears_daemon.py: hard VRAM cap so Parakeet can't balloon onto Fish Speech's memory.
torch.cuda.set_per_process_memory_fraction(0.094, 0)  # ~3.0 GB on 32 GB GPU

import numpy as np
import soundfile as sf
import nemo.collections.asr as nemo_asr
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import uvicorn

HOST = os.environ.get("PARAKEET_HOST", "127.0.0.1")
PORT = int(os.environ.get("PARAKEET_PORT", "9876"))
TARGET_RATE = 16000  # Parakeet expects 16 kHz mono

app = FastAPI()

# --- Model load (CPU -> half -> CUDA, same pattern as ears_daemon.py) ---
print("[parakeet] loading nvidia/parakeet-tdt-0.6b-v2 ...", flush=True)
_t = time.perf_counter()
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v2", map_location="cpu")
model = model.half().cuda()
model.train(False)  # inference mode (equivalent to .eval())
print(f"[parakeet] loaded in {time.perf_counter() - _t:.1f}s", flush=True)

# --- Warmup: one silent inference to trigger CUDA graph compilation ---
print("[parakeet] warming up...", flush=True)
_warm_audio = np.zeros(TARGET_RATE, dtype=np.float32)  # 1s of silence
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as _tmp:
    sf.write(_tmp.name, _warm_audio, TARGET_RATE)
    _warmup_path = _tmp.name
with torch.inference_mode():
    _ = model.transcribe([_warmup_path], batch_size=1, verbose=False)
os.unlink(_warmup_path)
print("[parakeet] warmup done, ready", flush=True)


def _decode_to_16k_mono_float32(wav_bytes: bytes) -> np.ndarray:
    """Accept any WAV (8/16/24/32 bit, mono/stereo, any rate), return float32 mono @ 16 kHz."""
    audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != TARGET_RATE:
        # Simple linear resample (cheap; Parakeet is tolerant). Upgrade to scipy if quality matters.
        from math import ceil
        ratio = TARGET_RATE / sr
        new_len = int(ceil(len(audio) * ratio))
        idx = np.linspace(0, len(audio) - 1, new_len).astype(np.int64)
        audio = audio[idx]
    return audio.astype(np.float32)


@app.post("/inference")
async def inference(
    file: UploadFile = File(...),
    response_format: str = Form("json"),
    language: str = Form("en"),
    temperature: str = Form("0.0"),
    no_speech_thold: str = Form("0.3"),
    logprob_thold: str = Form("-1.5"),
):
    """Whisper-server compatible: multipart WAV in, {"text": ...} out. Ignores whisper-specific tunables."""
    t0 = time.perf_counter()
    try:
        wav_bytes = await file.read()
        audio = _decode_to_16k_mono_float32(wav_bytes)

        # NeMo's transcribe() expects a file path. Use a tempfile on tmpfs for speed.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, TARGET_RATE)
            tmp_path = tmp.name

        # NeMo's transcribe is sync and holds the GIL briefly; run in thread.
        def _run():
            with torch.inference_mode():
                return model.transcribe([tmp_path], batch_size=1, verbose=False)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _run)

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # NeMo returns list[Hypothesis] in recent versions, list[str] in older ones.
        text = ""
        if result and len(result) > 0:
            first = result[0]
            if isinstance(first, str):
                text = first
            elif hasattr(first, "text"):
                text = first.text
            elif isinstance(first, list) and len(first) > 0 and hasattr(first[0], "text"):
                text = first[0].text
            else:
                text = str(first)

        text = (text or "").strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"[parakeet] {elapsed_ms:.0f}ms -> '{text[:80]}'", flush=True)
        return JSONResponse({"text": text})
    except Exception as e:
        print(f"[parakeet] ERROR: {e}", flush=True)
        return JSONResponse({"text": "", "error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "parakeet-tdt-0.6b-v2"}


if __name__ == "__main__":
    print(f"[parakeet] serving on http://{HOST}:{PORT}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
