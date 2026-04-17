#!/bin/bash
# Start the Parakeet TDT 0.6b v2 ASR server (drop-in replacement for whisper-server).
# Binds to 127.0.0.1:9876 — same contract sei_engine expects via SEI_ASR_URL.
#
# Deps: nemo_toolkit[asr] + torch (system python), fastapi + uvicorn + python-multipart,
#       soundfile, numpy. Uses system python since NeMo is installed there.

set -euo pipefail

cd "$(dirname "$0")/.."

export PARAKEET_HOST="${PARAKEET_HOST:-127.0.0.1}"
export PARAKEET_PORT="${PARAKEET_PORT:-9876}"

# CUDA 13 toolkit path (matches Fish Speech startup convention)
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/home/prana/cuda13-toolkit/targets/x86_64-linux/lib"

# Silence HuggingFace tokenizer fork warnings
export TOKENIZERS_PARALLELISM=false

# Use project venv only if it has nemo installed; otherwise fall back to system python.
if [ -x ".venv/bin/python" ] && .venv/bin/python -c "import nemo" 2>/dev/null; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "[start_parakeet] $PY scripts/parakeet_server.py on ${PARAKEET_HOST}:${PARAKEET_PORT}"
exec "$PY" scripts/parakeet_server.py
