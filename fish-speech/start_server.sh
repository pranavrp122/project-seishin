#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export ENABLE_SM120=1
export CUDA_HOME="/home/prana/cuda13-toolkit/targets/x86_64-linux"
export PATH="/home/prana/cuda13-toolkit/bin:$PATH"
export LD_LIBRARY_PATH="/home/prana/cuda13-toolkit/targets/x86_64-linux/lib:/usr/local/lib/ollama/mlx_cuda_v13:${LD_LIBRARY_PATH:-}"

CHECKPOINT="checkpoints/s2-pro"

exec .venv/bin/python3 tools/api_server.py \
  --llama-checkpoint-path "$CHECKPOINT" \
  --decoder-checkpoint-path "$CHECKPOINT/codec.pth" \
  --decoder-config-name modded_dac_vq \
  --device cuda \
  --compile \
  --listen 127.0.0.1:8080 \
  "$@"
