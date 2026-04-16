#!/usr/bin/env bash
# =============================================================================
# run.sh -- Launch vLLM serving Gemma 4 26B-A4B NVFP4
#
# Usage:
#   ./run.sh baseline   -- NVFP4 + FP8 KV cache (Stage 1, known working)
#   ./run.sh tq         -- NVFP4 + TurboQuant KV cache (Stage 2, experimental)
#   ./run.sh stop       -- Stop and remove the container
#   ./run.sh logs       -- Follow container logs
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HOME/models/gemma4-26b-a4b-nvfp4"
HF_CACHE="$HOME/.cache/huggingface"
CONTAINER_NAME="vllm-gemma4"
PORT=8000

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    # Check model exists
    if [[ ! -f "$MODEL_DIR/config.json" ]]; then
        error "Model not found at $MODEL_DIR"
        error "Run: ./setup.sh model"
        exit 1
    fi

    # Check patch file
    if [[ ! -f "$MODEL_DIR/gemma4_patched.py" ]]; then
        error "gemma4_patched.py not found in $MODEL_DIR"
        exit 1
    fi

    # Check GPU
    if ! nvidia-smi &>/dev/null; then
        error "nvidia-smi not available. Is the GPU accessible?"
        exit 1
    fi

    # Stop existing container if running
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        warn "Container $CONTAINER_NAME already running. Stopping..."
        docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME"
    elif docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
        docker rm "$CONTAINER_NAME"
    fi

    # Show GPU state
    info "GPU status:"
    nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader
}

# ---------------------------------------------------------------------------
# Stage 1: NVFP4 + FP8 KV cache (baseline)
# ---------------------------------------------------------------------------
run_baseline() {
    local IMAGE
    if [[ -f "$SCRIPT_DIR/.baseline-image" ]]; then
        IMAGE=$(cat "$SCRIPT_DIR/.baseline-image")
    else
        IMAGE="vllm/vllm-openai:gemma4-cu130"
    fi

    info "=== Stage 1: NVFP4 + FP8 KV cache (baseline) ==="
    info "Image: $IMAGE"
    info "Model: $MODEL_DIR"

    docker run -d \
        --name "$CONTAINER_NAME" \
        --gpus all \
        --ipc=host \
        -p "127.0.0.1:${PORT}:${PORT}" \
        --shm-size=8gb \
        --ulimit memlock=-1 \
        --ulimit stack=67108864 \
        -e VLLM_NVFP4_GEMM_BACKEND=marlin \
        -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
        -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
        -v "$MODEL_DIR":/model:ro \
        -v "$HF_CACHE":/root/.cache/huggingface:ro \
        -v "$MODEL_DIR/gemma4_patched.py":/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py:ro \
        "$IMAGE" \
        /model \
            --served-model-name gemma-4 \
            --host 0.0.0.0 \
            --port "$PORT" \
            --quantization modelopt \
            --dtype auto \
            --kv-cache-dtype fp8 \
            --gpu-memory-utilization 0.70 \
            --max-model-len 32768 \
            --max-num-seqs 1 \
            --moe-backend marlin \
            --trust-remote-code

    info "Container started: $CONTAINER_NAME"
    info "Waiting for server to be ready..."
    wait_for_server
}

# ---------------------------------------------------------------------------
# Stage 2: NVFP4 + TurboQuant KV cache
# ---------------------------------------------------------------------------
run_tq() {
    local IMAGE
    if [[ -f "$SCRIPT_DIR/.tq-image" ]]; then
        IMAGE=$(cat "$SCRIPT_DIR/.tq-image")
    else
        IMAGE="vllm-gemma4-tq"
    fi

    # Check if TQ image exists
    if ! docker image inspect "$IMAGE" &>/dev/null; then
        error "TQ image '$IMAGE' not found. Run: ./setup.sh tq"
        exit 1
    fi

    info "=== Stage 2: NVFP4 + TurboQuant KV cache ==="
    info "Image: $IMAGE"
    info "Model: $MODEL_DIR"
    info "KV cache: tq-k8v4 (FP8 keys + 4-bit values)"
    info "Skip layers: sliding_window (only compress 5 global layers)"

    # Notes on the flags:
    #   --kv-cache-dtype turboquant_k8v4
    #     FP8 keys + 4-bit values. Safest quality preset (2.6x compression).
    #     Alternative: turboquant_4bit_nc (3.8x, slightly lower quality)
    #
    #   --kv-cache-dtype-skip-layers "sliding_window"
    #     Skip TQ for the 25 sliding window layers (head_dim=256, capped at 1024 tokens).
    #     Only compress the 5 global attention layers (head_dim=512, scale with context).
    #     This is the safest config for Gemma 4's heterogeneous architecture.
    #
    #     NOTE: Alberto-Codes' branch may handle this automatically for Gemma 4.
    #     If --kv-cache-dtype-skip-layers causes an error, try removing it and let
    #     the branch's heterogeneous head_dim support handle both layer types.
    #
    #   Potential blocker:
    #     ModelOptNvFp4Config.KVCacheMethodCls defaults to ModelOptFp8KVCacheMethod.
    #     The CLI --kv-cache-dtype should override this via CacheConfig, but if it
    #     doesn't, see TROUBLESHOOTING.md or try the fallback command below.

    docker run -d \
        --name "$CONTAINER_NAME" \
        --gpus all \
        --ipc=host \
        -p "127.0.0.1:${PORT}:${PORT}" \
        --shm-size=8gb \
        --ulimit memlock=-1 \
        --ulimit stack=67108864 \
        -e VLLM_NVFP4_GEMM_BACKEND=marlin \
        -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
        -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
        -e TQ_BOUNDARY_LAYERS=0 \
        -v "$MODEL_DIR":/model:ro \
        -v "$HF_CACHE":/root/.cache/huggingface:ro \
        -v "$MODEL_DIR/gemma4_patched.py":/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py:ro \
        "$IMAGE" \
        /model \
            --served-model-name gemma-4 \
            --host 0.0.0.0 \
            --port "$PORT" \
            --quantization modelopt \
            --dtype auto \
            --kv-cache-dtype tq-k8v4 \
            --gpu-memory-utilization 0.60 \
            --max-model-len 32768 \
            --max-num-seqs 1 \
            --moe-backend marlin \
            --trust-remote-code

    info "Container started: $CONTAINER_NAME"
    info "Waiting for server to be ready..."
    wait_for_server
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
wait_for_server() {
    local max_wait=300  # 5 minutes (model load + CUDA graph warmup)
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        # Check if container died
        if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
            error "Container exited! Check logs:"
            error "  docker logs $CONTAINER_NAME"
            docker logs --tail 50 "$CONTAINER_NAME" 2>&1
            exit 1
        fi

        # Check if server is responding
        if curl -sf "http://localhost:$PORT/health" &>/dev/null; then
            info "Server is ready! (took ${elapsed}s)"
            info "  API: http://localhost:$PORT/v1"
            info "  Health: http://localhost:$PORT/health"
            info "  Metrics: http://localhost:$PORT/metrics"
            echo ""
            info "Quick test:"
            info "  ./test.sh quick"
            info ""
            info "VRAM after load:"
            nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
            return 0
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        # Show progress every 30s
        if (( elapsed % 30 == 0 )); then
            info "Still waiting... (${elapsed}s elapsed)"
            # Show last log line for progress
            docker logs --tail 1 "$CONTAINER_NAME" 2>&1 | head -1
        fi
    done

    error "Server did not start within ${max_wait}s"
    error "Check logs: docker logs $CONTAINER_NAME"
    exit 1
}

stop_container() {
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        info "Stopping $CONTAINER_NAME ..."
        docker stop "$CONTAINER_NAME"
        docker rm "$CONTAINER_NAME"
        info "Stopped."
    elif docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
        docker rm "$CONTAINER_NAME"
        info "Removed stopped container."
    else
        info "No container named $CONTAINER_NAME found."
    fi
}

show_logs() {
    docker logs -f "$CONTAINER_NAME"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 [baseline|tq|stop|logs]"
    echo ""
    echo "Commands:"
    echo "  baseline  Stage 1: NVFP4 + FP8 KV cache (known working)"
    echo "  tq        Stage 2: NVFP4 + TurboQuant KV cache (experimental)"
    echo "  stop      Stop and remove the container"
    echo "  logs      Follow container logs"
}

CMD="${1:-baseline}"
case "$CMD" in
    baseline) preflight; run_baseline ;;
    tq)       preflight; run_tq ;;
    stop)     stop_container ;;
    logs)     show_logs ;;
    -h|--help) usage ;;
    *) error "Unknown command: $CMD"; usage; exit 1 ;;
esac
