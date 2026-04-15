#!/usr/bin/env bash
# =============================================================================
# setup.sh -- Build Docker environment for Gemma 4 26B-A4B NVFP4 + TurboQuant
#
# Strategy:
#   Stage 1 (baseline): gemma4-cu130 image + NVFP4 patch (no TQ)
#   Stage 2 (TQ native): Build from Alberto-Codes' branch with Gemma 4 TQ support
#
# The TQ pip plugin (Alberto-Codes/turboquant-vllm) is NOT viable for Gemma 4
# because head_dim=512 is unsupported and it conflicts with modelopt page sizes.
# Instead we build from Alberto-Codes' fork of vibhavagarwal5's TQ PR branch,
# which has native heterogeneous head_dim support tested on Gemma 4 26B-A4B.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HOME/models/gemma4-26b-a4b-nvfp4"
HF_CACHE="$HOME/.cache/huggingface"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Phase 1: Download model (if not already present)
# ---------------------------------------------------------------------------
setup_model() {
    info "Checking model at $MODEL_DIR ..."

    if [[ -d "$MODEL_DIR" ]] && ls "$MODEL_DIR"/model*.safetensors &>/dev/null; then
        info "Model files already present. Skipping download."
    else
        info "Downloading Gemma 4 26B-A4B NVFP4 (~16.5 GB) ..."
        mkdir -p "$MODEL_DIR"
        huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 \
            --local-dir "$MODEL_DIR"
    fi

    # Verify the critical patch file
    if [[ ! -f "$MODEL_DIR/gemma4_patched.py" ]]; then
        error "gemma4_patched.py not found in model directory!"
        error "This file is required to fix NVFP4 MoE scale key mapping."
        error "Without it, 91% of weights silently skip quantization."
        exit 1
    fi
    info "gemma4_patched.py found."
}

# ---------------------------------------------------------------------------
# Phase 2a: Pull baseline Docker image (NVFP4 + FP8 KV)
# ---------------------------------------------------------------------------
setup_baseline_image() {
    info "--- Stage 1: Baseline image (NVFP4 + FP8 KV) ---"

    # Try v0.19.0-cu130 first (latest stable + CUDA 13.0 for SM120)
    # Fallback to gemma4-cu130 then nightly
    local IMAGE=""
    for tag in "v0.19.0-cu130" "gemma4-cu130" "latest-cu130" "cu130-nightly"; do
        info "Trying vllm/vllm-openai:$tag ..."
        if docker pull "vllm/vllm-openai:$tag" 2>/dev/null; then
            IMAGE="vllm/vllm-openai:$tag"
            break
        fi
        warn "Tag $tag not available, trying next..."
    done

    if [[ -z "$IMAGE" ]]; then
        error "No suitable cu130 Docker image found!"
        error "Available cu130 tags on Docker Hub:"
        error "  vllm/vllm-openai:gemma4-cu130"
        error "  vllm/vllm-openai:latest-cu130"
        error "  vllm/vllm-openai:v0.19.0-x86_64-cu130-ubuntu2404"
        exit 1
    fi

    info "Baseline image ready: $IMAGE"
    echo "$IMAGE" > "$SCRIPT_DIR/.baseline-image"
}

# ---------------------------------------------------------------------------
# Phase 2b: Build TurboQuant Docker image from Alberto-Codes' branch
# ---------------------------------------------------------------------------
setup_tq_image() {
    info "--- Stage 2: TurboQuant image (NVFP4 + TQ KV) ---"

    local BUILD_DIR="$SCRIPT_DIR/build-tq"
    mkdir -p "$BUILD_DIR"

    # Determine base image
    local BASE_IMAGE
    if [[ -f "$SCRIPT_DIR/.baseline-image" ]]; then
        BASE_IMAGE=$(cat "$SCRIPT_DIR/.baseline-image")
    else
        BASE_IMAGE="vllm/vllm-openai:gemma4-cu130"
    fi

    info "Building TQ image from Alberto-Codes/vllm feat/gemma4-heterogeneous-tq branch"
    info "Base image: $BASE_IMAGE"

    # Clone the specific branch with TurboQuant + Gemma 4 heterogeneous head_dim support.
    # This branch is based on vibhavagarwal5's feature/turboquant-kv-cache (PR #38479)
    # with Alberto-Codes' additions for Gemma 4:
    #   - FA head_dim>256 guard with SDPA fallback for d=512 global layers
    #   - TQFullAttentionSpec with real_page_size_bytes override
    #   - Per-layer head_dim in KV cache specs
    #   - Shared KV layer support (for Gemma 4 E4B, not needed for 26B-A4B)
    if [[ ! -d "$BUILD_DIR/vllm-tq" ]]; then
        info "Cloning Alberto-Codes/vllm (feat/gemma4-heterogeneous-tq) ..."
        git clone --depth 1 --branch feat/gemma4-heterogeneous-tq \
            https://github.com/Alberto-Codes/vllm.git \
            "$BUILD_DIR/vllm-tq"
    else
        info "TQ source already cloned. Pulling latest..."
        cd "$BUILD_DIR/vllm-tq" && git pull --ff-only || true
    fi

    # Generate Dockerfile that overlays TQ code onto the base image.
    # We overlay only the changed files rather than rebuilding all of vLLM,
    # because a full build requires CUDA nvcc compilation (~30+ min).
    # The TQ changes are pure Python + Triton kernels (no C++/CUDA compilation).
    info "Generating Dockerfile..."
    cat > "$BUILD_DIR/Dockerfile.tq" << 'DOCKERFILE'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# TurboQuant files from Alberto-Codes/vllm feat/gemma4-heterogeneous-tq
# These overlay on top of the base vLLM installation.

# Find the vLLM site-packages path
# In the official Docker images this is /usr/local/lib/python3.12/dist-packages/vllm
ENV VLLM_PATH=/usr/local/lib/python3.12/dist-packages/vllm

# Copy TurboQuant quantization module (new directory)
COPY vllm-tq/vllm/model_executor/layers/quantization/turboquant/ \
     ${VLLM_PATH}/model_executor/layers/quantization/turboquant/

# Copy TurboQuant attention backend (new file)
COPY vllm-tq/vllm/v1/attention/backends/turboquant_attn.py \
     ${VLLM_PATH}/v1/attention/backends/turboquant_attn.py

# Copy TurboQuant Triton kernels (new files)
COPY vllm-tq/vllm/v1/attention/ops/triton_tq_decode.py \
     ${VLLM_PATH}/v1/attention/ops/triton_tq_decode.py
COPY vllm-tq/vllm/v1/attention/ops/triton_tq_store.py \
     ${VLLM_PATH}/v1/attention/ops/triton_tq_store.py

# Overlay modified files (these have TQ hooks added to existing code)
COPY vllm-tq/vllm/v1/attention/backends/registry.py \
     ${VLLM_PATH}/v1/attention/backends/registry.py
COPY vllm-tq/vllm/v1/core/kv_cache_utils.py \
     ${VLLM_PATH}/v1/core/kv_cache_utils.py
COPY vllm-tq/vllm/v1/core/single_type_kv_cache_manager.py \
     ${VLLM_PATH}/v1/core/single_type_kv_cache_manager.py
COPY vllm-tq/vllm/v1/kv_cache_interface.py \
     ${VLLM_PATH}/v1/kv_cache_interface.py
COPY vllm-tq/vllm/v1/worker/gpu_model_runner.py \
     ${VLLM_PATH}/v1/worker/gpu_model_runner.py
COPY vllm-tq/vllm/config/cache.py \
     ${VLLM_PATH}/config/cache.py
COPY vllm-tq/vllm/engine/arg_utils.py \
     ${VLLM_PATH}/engine/arg_utils.py
COPY vllm-tq/vllm/model_executor/layers/attention/attention.py \
     ${VLLM_PATH}/model_executor/layers/attention/attention.py
COPY vllm-tq/vllm/model_executor/models/config.py \
     ${VLLM_PATH}/model_executor/models/config.py
COPY vllm-tq/vllm/platforms/cuda.py \
     ${VLLM_PATH}/platforms/cuda.py
COPY vllm-tq/vllm/utils/torch_utils.py \
     ${VLLM_PATH}/utils/torch_utils.py
DOCKERFILE

    info "Building Docker image: vllm-gemma4-tq ..."
    docker build \
        --build-arg BASE_IMAGE="$BASE_IMAGE" \
        -f "$BUILD_DIR/Dockerfile.tq" \
        -t vllm-gemma4-tq \
        "$BUILD_DIR"

    info "TQ image built: vllm-gemma4-tq"
    echo "vllm-gemma4-tq" > "$SCRIPT_DIR/.tq-image"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
usage() {
    echo "Usage: $0 [model|baseline|tq|all]"
    echo ""
    echo "Commands:"
    echo "  model     Download the NVFP4 model from HuggingFace"
    echo "  baseline  Pull the vLLM cu130 Docker image (Stage 1)"
    echo "  tq        Build the TurboQuant Docker image (Stage 2)"
    echo "  all       Do everything (default)"
}

CMD="${1:-all}"
case "$CMD" in
    model)    setup_model ;;
    baseline) setup_baseline_image ;;
    tq)       setup_model; setup_tq_image ;;
    all)      setup_model; setup_baseline_image; setup_tq_image ;;
    -h|--help) usage ;;
    *) error "Unknown command: $CMD"; usage; exit 1 ;;
esac

info "Setup complete."
