#!/usr/bin/env bash
# vLLM startup script — deployed to /home/ubuntu/vllm.sh on the instance.
# Called by systemd on boot and by start_gpu.sh.
set -euo pipefail

MODEL_DIR="/home/ubuntu/models/gemma4-fp8"
PORT=8000
CONTAINER_NAME="vllm-gemma4"

docker run \
    --name "$CONTAINER_NAME" \
    --gpus all \
    --ipc=host \
    -p "${PORT}:${PORT}" \
    --shm-size=8gb \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    -v "$MODEL_DIR":/model:ro \
    vllm/vllm-openai:latest \
    /model \
        --served-model-name gemma-4 \
        --host 0.0.0.0 \
        --port "$PORT" \
        --dtype auto \
        --kv-cache-dtype fp8 \
        --gpu-memory-utilization 0.98 \
        --max-model-len 131072 \
        --max-num-seqs 4 \
        --enable-auto-tool-choice \
        --tool-call-parser gemma4 \
        --api-key "${VLLM_API_KEY}" \
        --trust-remote-code
