#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Project Seishin — Phase 1
# vLLM server launcher for Qwen 3.5 35B-A3B (NVFP4 / Blackwell)
#
# Run from WSL2. Assumes:
#   - CUDA 12.6+ installed
#   - vllm installed: pip install vllm
#   - Model downloaded or accessible via HuggingFace cache
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

MODEL="Qwen/Qwen2.5-35B-Instruct-GPTQ-Int4"
PORT=8000
GPU_MEMORY_UTIL=0.88        # Leave ~12% headroom on 5090 (32GB)
MAX_MODEL_LEN=8192           # Context window
TENSOR_PARALLEL=1            # Single GPU (5090)
DTYPE="auto"                 # Let vLLM pick FP8/NVFP4 per capability
SPECULATIVE_MODEL="Qwen/Qwen2.5-0.5B-Instruct"  # Drafter for speculative decoding

echo "═══════════════════════════════════════════════"
echo "  Project Seishin — vLLM Launcher"
echo "  Model: $MODEL"
echo "  Port:  $PORT"
echo "═══════════════════════════════════════════════"

# CUDA Graph + Prefix Cache flags (Blackwell optimizations)
export VLLM_USE_CUDA_GRAPH=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn

python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --port "$PORT" \
  --dtype "$DTYPE" \
  --gpu-memory-utilization "$GPU_MEMORY_UTIL" \
  --max-model-len "$MAX_MODEL_LEN" \
  --tensor-parallel-size "$TENSOR_PARALLEL" \
  --enable-prefix-caching \
  --enable-cuda-graph \
  --kv-cache-dtype "fp8" \
  --speculative-model "$SPECULATIVE_MODEL" \
  --speculative-num-speculative-tokens 5 \
  --trust-remote-code \
  --served-model-name "Qwen/Qwen2.5-35B-Instruct-GPTQ-Int4" \
  2>&1 | tee logs/vllm.log
