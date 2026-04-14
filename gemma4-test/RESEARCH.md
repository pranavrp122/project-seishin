# Research: Gemma 4 26B-A4B NVFP4 + TurboQuant KV Cache on RTX 5090

**Researched:** 2026-04-14
**Overall Confidence:** MEDIUM (combination of NVFP4 + TurboQuant is untested territory)

---

## Executive Summary

Running Gemma 4 26B-A4B with NVFP4 weights (~15.7 GB) and TurboQuant KV cache compression on an RTX 5090 (32 GB) is technically feasible but requires assembling several unmerged/community components. The NVFP4 model exists as a community quantization from bg-digitalservices, requiring a patched `gemma4.py` for vLLM. TurboQuant KV cache compression has three viable paths: the `turboquant-vllm` pip plugin (works today, simplest), the native vLLM PR #38479 (not yet merged, most complete), and the TurboQuant+ llama.cpp fork (Apple Silicon focus, not vLLM). The critical unknown is whether NVFP4 weight quantization (`--quantization modelopt`) and TurboQuant KV cache (`--kv-cache-dtype` or `--attention-backend CUSTOM`) can coexist in the same vLLM instance without conflicts. Nobody has publicly tested this exact combination.

**Recommendation:** Start with NVFP4 + FP8 KV cache (known working), then layer on TurboQuant via the pip plugin approach as a second step. This de-risks the integration.

---

## 1. Model: Gemma 4 26B-A4B NVFP4

### Source
- **HuggingFace:** `bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4`
- **License:** Apache 2.0 (no gating, no access requests needed)
- **Quantized by:** Mario Iseli using NVIDIA Model Optimizer v0.43 on DGX Spark

### Architecture
| Property | Value |
|----------|-------|
| Total params | 25.2B |
| Active params/token | 3.8B |
| Experts | 128 total, 8 active per token |
| Context window | 256K tokens |
| Attention layers | 5 global (head_dim=512, 4 KV heads) + 25 sliding window (head_dim=256, 4 KV heads, window=1024) |
| Modalities | Text, Image, Video |

### NVFP4 Specs
| Metric | BF16 | NVFP4 |
|--------|------|-------|
| Size on disk | ~49 GB | ~16.5 GB |
| Loaded VRAM | ~49 GB | ~15.7 GB |
| Tokens/sec (DGX Spark, 273 GB/s) | 23.3 | 48.2 |
| TTFT (ms) | 97 | 53 |
| Quality retention | 100% | 97.6% avg |

### Critical: The Patched gemma4.py

vLLM's Gemma 4 `expert_params_mapping` does not correctly map NVFP4 scale keys (`.weight_scale`, `.weight_scale_2`, `.input_scale`) to FusedMoE parameter names. The model repo includes a `gemma4_patched.py` that must replace the stock vLLM file.

**Without this patch, 91% of the model (all MoE expert weights) will silently fail to load quantized weights.**

Mount location (Docker):
```
/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py
```

For a venv install, find the equivalent path:
```bash
python -c "import vllm; print(vllm.__file__)" | sed 's/__init__.py/model_executor\/models\/gemma4.py/'
```

### Download
```bash
# Standard HuggingFace download
huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 --local-dir ./Gemma-4-26B-A4B-it-NVFP4

# Or via git lfs
git lfs install
git clone https://huggingface.co/bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4
```

---

## 2. TurboQuant: Three Approaches Compared

### Option A: turboquant-vllm Pip Plugin (RECOMMENDED FOR INITIAL TEST)

**Status:** Working today, published on PyPI
**Source:** https://github.com/Alberto-Codes/turboquant-vllm

| Property | Value |
|----------|-------|
| Installation | `pip install turboquant-vllm[vllm]` |
| Mechanism | vLLM plugin system, registers via entry points |
| Activation | `--attention-backend CUSTOM` |
| K/V config | `TQ4_K_BITS=4 TQ4_V_BITS=3` env vars |
| Validated models | Llama 3.1, Qwen2.5, Mistral, Phi-3/4, Gemma 2, Gemma 3, Molmo2 |
| Compression | 3.76x (K4/V4) |
| Cosine similarity | >0.98 (K4/V3), >0.994 (K4/V4) |
| head_dim support | 64, 96, 128, 256 |

**Pros:**
- Works with current vLLM release (no fork needed)
- Simple pip install
- Plugin architecture = no code changes
- Validated on Gemma 2 and Gemma 3

**Cons:**
- Gemma 4 MoE NOT explicitly validated (Gemma 2/3 only)
- head_dim=512 (Gemma 4 global layers) NOT in supported list
- Per-token decode latency +201% (significant overhead)
- Throughput -7.3% overall
- Unknown compatibility with `--quantization modelopt` flag

**Critical risk:** Gemma 4's global attention layers have head_dim=512, which is NOT in the validated head_dim list (64/96/128/256). This could cause crashes or silent quality degradation on those 5 layers.

### Option B: Native vLLM PR #38479 (BEST LONG-TERM, NOT YET MERGED)

**Status:** Open PR, actively being reviewed, has "ready" label but mergeable_state is "dirty"
**Source:** https://github.com/vllm-project/vllm/pull/38479
**Last updated:** 2026-04-14

| Property | Value |
|----------|-------|
| Activation | `--kv-cache-dtype turboquant_k8v4` (or t4nc, k3v4nc, t3nc) |
| Best preset | `turboquant_k8v4` (FP8 keys + 4-bit values, 2.6x compression) |
| Layer skipping | `--kv-cache-dtype-skip-layers 0,1,28,29` or `"sliding_window"` |
| Hybrid model support | Yes - auto-skips sliding window layers, tested on Nemotron hybrid |
| CUDAGraph support | Yes (static NUM_KV_SPLITS grid) |
| Validated models | Qwen2.5, Qwen3, Gemma 2, Gemma 3, Llama, Mistral, Phi-3/4, Molmo2, Nemotron |

**Presets (tested on Qwen3-4B):**

| Preset | Compression | GSM8K | NIAH | Throughput vs baseline |
|--------|-------------|-------|------|----------------------|
| `turboquant_k8v4` | 2.6x | 0.860 (base: 0.900) | 100% | 79-100% |
| `turboquant_4bit_nc` | 3.8x | 0.840 | 100% | 71-96% |
| `turboquant_k3v4_nc` | 4.3x | 0.780 | 100% | 69-88% |
| `turboquant_3bit_nc` | 4.9x | 0.720 | 100% | 68-86% |

**Pros:**
- Most complete implementation with Triton kernels
- Handles hybrid attention natively (auto-skips sliding window)
- Supports boundary layer protection
- CUDAGraph compatible
- Actively being reviewed by vLLM maintainers
- Tested on Blackwell hardware (RTX PRO 6000)

**Cons:**
- Not merged yet (PR is "dirty" = merge conflicts)
- Requires building vLLM from the PR branch
- 3-bit unpacking bug identified by code review (critical review comment)
- FP8 fallback conversion bug for older CUDA architectures (not relevant for Blackwell)
- head_dim=512 support unclear

**To use today:**
```bash
# Clone vLLM and checkout PR branch
git clone https://github.com/vllm-project/vllm.git
cd vllm
git fetch origin pull/38479/head:turboquant
git checkout turboquant
pip install -e .
```

### Option C: TurboQuant+ (llama.cpp fork, NOT vLLM)

**Status:** v1 complete, 511+ tests, Apple Silicon focused
**Source:** https://github.com/TheTom/turboquant_plus

This is a llama.cpp fork, NOT a vLLM integration. It's the most thoroughly researched implementation with excellent findings about asymmetric K/V compression. Gemma 4 26B-A4B has been tested via MLX-swift-lm with 79% MM-NIAH accuracy and 99% answer agreement with baseline.

**Relevant findings from this project:**
- Symmetric TurboQuant on already-quantized models = catastrophic (PPL 3556)
- Asymmetric K8/V-turbo4 is safe and effective
- Boundary layer protection (first/last 2 layers at higher precision) recovers 37-91% of quality gap
- V compression is essentially free (2-bit values, zero quality loss)
- K compression drives all degradation

**Not viable for our use case** (we need vLLM for the OpenAI-compatible API endpoint), but the research findings are invaluable for configuration decisions.

### Decision Matrix

| Criterion | Pip Plugin (A) | Native PR (B) | llama.cpp Fork (C) |
|-----------|---------------|---------------|---------------------|
| Works today | YES | NO (needs build from PR) | YES (but not vLLM) |
| Gemma 4 MoE tested | NO | NO (Gemma 2/3 only) | YES (via MLX) |
| head_dim=512 support | UNKNOWN | UNKNOWN | N/A |
| NVFP4 compatibility | UNKNOWN | UNKNOWN | N/A |
| Hybrid attention handling | NO (manual) | YES (auto-skip) | N/A |
| Sliding window skip | NO | YES | N/A |
| Decode overhead | +201% | +20-30% (Triton kernels) | N/A |
| Installation complexity | Low | High | N/A |

---

## 3. NVFP4 + TurboQuant Compatibility Analysis

### The Core Question

Can `--quantization modelopt` (NVFP4 weights) and TurboQuant KV cache coexist?

**Assessment: LIKELY YES, but untested. Confidence: LOW.**

Reasoning:
1. **Weight quantization and KV cache quantization operate on different memory domains.** Weight quantization affects model parameter storage and GEMM operations. KV cache quantization affects the attention cache storage/retrieval. They should be independent.
2. **vLLM architecture supports this separation.** The `--quantization` flag controls `QuantizationConfig` for weight loading. The `--kv-cache-dtype` flag controls cache allocation in the attention backend. These are different code paths.
3. **Precedent exists:** The HF model card already recommends `--quantization modelopt --kv-cache-dtype fp8` together. TurboQuant is just a different KV cache dtype.
4. **Nobody has tested it.** No search results show anyone running NVFP4 + TurboQuant together. The community tests use either BF16/AWQ weights + TurboQuant KV, or NVFP4 weights + FP8 KV.

### Potential Conflict Points

1. **Attention backend selection:** NVFP4 may force a specific attention backend (Marlin), while TurboQuant requires its own backend (TURBOQUANT or CUSTOM). These could conflict.
2. **The gemma4_patched.py:** This patch modifies `expert_params_mapping` for weight loading. It should not affect KV cache, but untested.
3. **Memory allocation:** vLLM's `--gpu-memory-utilization` controls the split between model weights and KV cache. With NVFP4's smaller weights, more memory is available for KV cache, which is favorable.
4. **Hybrid attention + TurboQuant page sizes:** Gemma 4's mixed head_dim (256 for sliding window, 512 for global) creates non-uniform KV cache specs. TurboQuant uses compact slot sizes that differ from BF16/FP8. vLLM requires compatible page sizes within a cache group.

### Recommended Approach: Staged Testing

**Stage 1: NVFP4 + FP8 KV (known working)**
```bash
vllm serve ./Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --kv-cache-dtype fp8 \
  --moe-backend marlin \
  --trust-remote-code \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --dtype auto
```
Verify: loads correctly, generates coherent text, measure VRAM baseline.

**Stage 2: NVFP4 + TurboQuant (pip plugin)**
```bash
pip install turboquant-vllm[vllm]
TQ4_K_BITS=4 TQ4_V_BITS=4 vllm serve ./Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --attention-backend CUSTOM \
  --moe-backend marlin \
  --trust-remote-code \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --dtype auto
```
Verify: loads, generates, measure VRAM delta vs FP8 KV.

**Stage 3: NVFP4 + TurboQuant (native PR, if plugin fails)**
Build vLLM from PR #38479 branch with gemma4_patched.py applied.
```bash
vllm serve ./Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --kv-cache-dtype turboquant_k8v4 \
  --kv-cache-dtype-skip-layers "sliding_window" \
  --moe-backend marlin \
  --trust-remote-code \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --dtype auto
```

---

## 4. VRAM Budget Analysis

### RTX 5090 Available Memory
- Total: 32 GB
- WSL baseline: ~945 MiB
- Available: ~31.2 GB

### Estimated Usage

| Component | NVFP4 + FP8 KV | NVFP4 + TQ k8v4 | NVFP4 + TQ t4nc |
|-----------|----------------|------------------|------------------|
| Model weights | 15.7 GB | 15.7 GB | 15.7 GB |
| vLLM overhead | ~1.0 GB | ~1.0 GB | ~1.0 GB |
| CUDA kernels/graphs | ~0.5 GB | ~0.5 GB | ~0.5 GB |
| **Available for KV cache** | **~14.0 GB** | **~14.0 GB** | **~14.0 GB** |

### KV Cache per Token (Gemma 4 26B-A4B)

The hybrid architecture means only 5 global layers scale with context length. The 25 sliding window layers are capped at 1024 tokens.

**Per-token KV cache breakdown:**

| Layer Type | Count | head_dim | KV heads | Per-layer bytes (BF16) | Per-layer bytes (FP8) | Per-layer bytes (TQ k8v4) |
|------------|-------|----------|----------|----------------------|---------------------|--------------------------|
| Global (full attention) | 5 | 512 | 4 | 2 * 512 * 4 * 2 = 8192 B | 4096 B | ~3154 B (2.6x) |
| Sliding window (1024 cap) | 25 | 256 | 4 | 2 * 256 * 4 * 2 = 4096 B | 2048 B | ~1577 B (2.6x) |

**Global layers per token (scales with context):**
- BF16: 5 * 8192 = 40,960 B/token = 40 KB/token
- FP8: 5 * 4096 = 20,480 B/token = 20 KB/token
- TQ k8v4: 5 * ~3154 = ~15,770 B/token = ~15.4 KB/token

**Sliding window total (fixed, 1024 tokens max):**
- BF16: 25 * 4096 * 1024 = 100 MB (fixed)
- FP8: 25 * 2048 * 1024 = 50 MB (fixed)
- TQ k8v4: 25 * ~1577 * 1024 = ~38.5 MB (fixed)

**IMPORTANT caveat on head_dim=512:** TurboQuant's behavior with head_dim=512 is untested. The pip plugin lists support for 64/96/128/256. The native PR validates up to head_dim=256. The global attention layers in Gemma 4 use head_dim=512. This is the single biggest risk for TurboQuant on Gemma 4.

### Context Length Estimates (14 GB for KV cache)

| KV Cache Type | Max Context (single request) |
|---------------|------------------------------|
| BF16 | ~350K tokens (14 GB / 40 KB) |
| FP8 | ~700K tokens (14 GB / 20 KB) |
| TQ k8v4 | ~933K tokens (14 GB / 15.4 KB) |

These are far beyond the model's 256K limit. Even at 256K context, FP8 KV uses only ~5.1 GB, leaving plenty of headroom.

**Conclusion:** KV cache is NOT the bottleneck on RTX 5090 for this model. The hybrid architecture with only 5 global attention layers means KV cache is extremely small. TurboQuant's value proposition here is primarily for batching multiple requests, not for extending context length.

---

## 5. Gemma 4 + Hybrid Attention Challenges

### The head_dim Problem

Gemma 4's two attention types have different head dimensions:
- Global layers: head_dim=512 (uncommon, only a few models use this)
- Sliding window layers: head_dim=256

This creates challenges:
1. **vLLM FlashAttention can't handle dual head_dim** -- falls back to slower Triton attention
2. **TurboQuant may not support head_dim=512** -- validated up to 256 only
3. **Non-uniform KV cache specs** within a single model

### Sliding Window + TurboQuant

PR #38479 handles this correctly:
- `--kv-cache-dtype-skip-layers "sliding_window"` skips TQ compression for all sliding window layers
- Those layers use standard FP16/FP8 KV cache
- Only global attention layers get TurboQuant compression

This is actually the optimal configuration for Gemma 4 because:
1. Sliding window layers are capped at 1024 tokens -- minimal KV cache regardless
2. Global layers are where context scales -- compression has highest impact here
3. Avoids the head_dim=256 vs 512 mixing issue (only compress 512-dim global layers)

**However**, this means TurboQuant's compression only applies to 5 out of 30 layers -- the memory savings are proportionally smaller.

### vLLM Version Requirements

| Feature | Minimum Version |
|---------|----------------|
| Gemma 4 support | vLLM 0.19.0 |
| transformers requirement | >= 5.5.0 |
| NVFP4/modelopt | vLLM 0.18+ (with patches) |
| TurboQuant (pip plugin) | Works with vLLM 0.18+ |
| TurboQuant (PR #38479) | Requires building from PR branch (based on ~0.19.x) |

---

## 6. Exact Setup Steps

### Prerequisites

```bash
# Verify GPU
nvidia-smi  # Should show RTX 5090, Driver 595.79, CUDA 13.2

# Verify VRAM
nvidia-smi --query-gpu=memory.total,memory.free --format=csv
```

### Option 1: Venv Install (Recommended for Testing)

```bash
# Create environment
python3 -m venv ~/gemma4-venv
source ~/gemma4-venv/bin/activate

# Install vLLM 0.19.0+ with CUDA 13.2
pip install vllm  # Should get 0.19.0+

# Verify transformers version
pip install 'transformers>=5.5.0'

# Download model
huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 \
  --local-dir ~/models/Gemma-4-26B-A4B-it-NVFP4

# Download and apply the gemma4 patch
# The patched file is in the model repo
VLLM_GEMMA4=$(python -c "import vllm; import os; print(os.path.join(os.path.dirname(vllm.__file__), 'model_executor/models/gemma4.py'))")
cp "$VLLM_GEMMA4" "${VLLM_GEMMA4}.bak"
cp ~/models/Gemma-4-26B-A4B-it-NVFP4/gemma4_patched.py "$VLLM_GEMMA4"
```

### Option 2: Docker

```bash
# Use the official vLLM Docker image (0.19.0+)
docker run -d \
  --name vllm-gemma4-test \
  --gpus all --ipc=host --network host \
  -e VLLM_NVFP4_GEMM_BACKEND=marlin \
  -v ~/models/Gemma-4-26B-A4B-it-NVFP4:/model \
  -v ~/models/Gemma-4-26B-A4B-it-NVFP4/gemma4_patched.py:/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py \
  vllm/vllm-openai:latest \
  vllm serve /model \
    --served-model-name gemma-4 \
    --host 0.0.0.0 --port 8888 \
    --quantization modelopt \
    --kv-cache-dtype fp8 \
    --moe-backend marlin \
    --gpu-memory-utilization 0.90 \
    --max-model-len 32768 \
    --trust-remote-code \
    --dtype auto
```

### Stage 1: Verify NVFP4 + FP8 KV (Baseline)

```bash
# Set environment
export VLLM_NVFP4_GEMM_BACKEND=marlin

# Launch server
vllm serve ~/models/Gemma-4-26B-A4B-it-NVFP4 \
  --served-model-name gemma-4 \
  --host 0.0.0.0 --port 8888 \
  --quantization modelopt \
  --kv-cache-dtype fp8 \
  --moe-backend marlin \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code \
  --dtype auto

# Test (in another terminal)
curl http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4",
    "messages": [{"role": "user", "content": "Explain quantum computing in 3 sentences."}],
    "max_tokens": 200
  }'

# Measure VRAM
nvidia-smi --query-gpu=memory.used --format=csv
```

### Stage 2: Add TurboQuant (Pip Plugin)

```bash
# Install the plugin
pip install turboquant-vllm[vllm]

# Launch with TurboQuant
export VLLM_NVFP4_GEMM_BACKEND=marlin
export TQ4_K_BITS=4
export TQ4_V_BITS=4

vllm serve ~/models/Gemma-4-26B-A4B-it-NVFP4 \
  --served-model-name gemma-4 \
  --host 0.0.0.0 --port 8888 \
  --quantization modelopt \
  --attention-backend CUSTOM \
  --moe-backend marlin \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code \
  --dtype auto

# Compare VRAM and quality with Stage 1
```

### Stage 3 (If Needed): Native PR Branch

```bash
# Only if pip plugin doesn't work
deactivate  # exit current venv
python3 -m venv ~/gemma4-venv-pr
source ~/gemma4-venv-pr/bin/activate

git clone https://github.com/vllm-project/vllm.git ~/vllm-turboquant
cd ~/vllm-turboquant
git fetch origin pull/38479/head:turboquant
git checkout turboquant
pip install -e .
pip install 'transformers>=5.5.0'

# Apply gemma4 patch
VLLM_GEMMA4=$(python -c "import vllm; import os; print(os.path.join(os.path.dirname(vllm.__file__), 'model_executor/models/gemma4.py'))")
cp ~/models/Gemma-4-26B-A4B-it-NVFP4/gemma4_patched.py "$VLLM_GEMMA4"

export VLLM_NVFP4_GEMM_BACKEND=marlin
vllm serve ~/models/Gemma-4-26B-A4B-it-NVFP4 \
  --served-model-name gemma-4 \
  --host 0.0.0.0 --port 8888 \
  --quantization modelopt \
  --kv-cache-dtype turboquant_k8v4 \
  --kv-cache-dtype-skip-layers "sliding_window" \
  --moe-backend marlin \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code \
  --dtype auto
```

---

## 7. Benchmarking Approach

### VRAM Measurement

```bash
# Before loading model
nvidia-smi --query-gpu=memory.used --format=csv,noheader

# After model loads (idle)
# Watch the vLLM startup logs for KV cache allocation info

# During inference at various context lengths
# Use vLLM's built-in metrics endpoint
curl http://localhost:8888/metrics | grep -E "vllm:gpu_cache|vllm:num_requests"
```

### Throughput Measurement

```bash
# Install benchmarking tool
pip install openai

# Single request throughput
python -c "
import openai, time
client = openai.OpenAI(base_url='http://localhost:8888/v1', api_key='none')
start = time.time()
response = client.chat.completions.create(
    model='gemma-4',
    messages=[{'role': 'user', 'content': 'Write a 500-word essay about AI.'}],
    max_tokens=500,
    stream=True
)
tokens = 0
first_token_time = None
for chunk in response:
    if chunk.choices[0].delta.content:
        tokens += 1
        if first_token_time is None:
            first_token_time = time.time()
elapsed = time.time() - start
ttft = first_token_time - start
print(f'TTFT: {ttft*1000:.0f}ms')
print(f'Total tokens: {tokens}')
print(f'Tokens/sec: {tokens/(elapsed-ttft):.1f}')
"
```

### Quality Comparison

Generate the same prompts with:
1. NVFP4 + FP8 KV (baseline)
2. NVFP4 + TurboQuant K4/V4
3. NVFP4 + TurboQuant K4/V3 (if supported)

Compare outputs manually for coherence and correctness.

---

## 8. Known Issues and Blockers

### Critical

| Issue | Severity | Mitigation |
|-------|----------|------------|
| head_dim=512 untested with TurboQuant | HIGH | Skip global layers with TQ, use FP8 for them instead. Or test and see. |
| gemma4_patched.py required | HIGH | Download from model repo, apply before launch |
| PR #38479 not merged | MEDIUM | Use pip plugin first, PR as fallback |
| NVFP4 + TurboQuant untested combination | MEDIUM | Stage 1 baseline first, then layer TurboQuant |
| vLLM 0.19.0 pins transformers < 5 in some configs | MEDIUM | Manual override: `pip install 'transformers>=5.5.0'` |

### Moderate

| Issue | Severity | Notes |
|-------|----------|-------|
| Hybrid attention falls back to Triton (slower) | MODERATE | Gemma 4's dual head_dim prevents FlashAttention |
| TQ pip plugin decode latency +201% | MODERATE | Only matters for single-request; batch throughput may differ |
| 3-bit TQ unpacking bug in PR #38479 | MODERATE | Use k8v4 preset (FP8 keys) to avoid |

### Minor

| Issue | Notes |
|-------|-------|
| `VLLM_NVFP4_GEMM_BACKEND=marlin` env var needed | Easy to forget |
| FP16 norms in TQ fail silently at long sequences | FP32 norms recommended (pip plugin may not have this fix) |
| Model is community quantization, not official NVIDIA | Quality slightly lower than official would be |

---

## 9. Performance Expectations on RTX 5090

### Throughput Estimate

The DGX Spark (GB10, 273 GB/s bandwidth) achieves 48.2 tok/s with NVFP4. The RTX 5090 has 1,792 GB/s bandwidth (6.6x more). MoE inference is memory-bandwidth-bound (only 3.8B active params per token).

**Rough estimate:** 48.2 * (1792/273) = ~316 tok/s theoretical maximum. Real-world will be lower due to:
- MoE routing overhead
- Kernel launch latency
- vLLM scheduling overhead
- Attention computation (not pure bandwidth)

**Realistic expectation:** 100-200 tok/s decode for single request. Community reports suggest ~51 tok/s single-request decode for the NVFP4-turbo 31B dense variant on RTX 5090 -- but the MoE 26B-A4B should be faster (3.8B vs 31B active params).

### With TurboQuant

TurboQuant k8v4 shows 79-100% of baseline throughput on RTX PRO 6000 Blackwell (same architecture). Expect:
- Short decode: ~80% of baseline
- Long prefill: ~95-100% of baseline
- The throughput cost is primarily in decode, not prefill

---

## 10. Fallback Plan

If TurboQuant doesn't work with NVFP4 on Gemma 4:

### Fallback 1: NVFP4 + FP8 KV Cache
```bash
--kv-cache-dtype fp8
```
This is already proven to work (it's in the model card). FP8 gives 2x KV compression vs BF16. For Gemma 4 with only 5 global attention layers, this is already quite efficient.

### Fallback 2: NVFP4 + No KV Compression
```bash
# Just omit --kv-cache-dtype (defaults to auto/bf16)
```
With 14 GB available for KV cache and only 5 global layers scaling with context, you can still fit ~350K tokens in BF16 KV. More than the model's 256K limit.

### Fallback 3: Different Weight Quantization
If NVFP4 itself causes issues, try:
- AWQ 4-bit (widely tested with TurboQuant)
- GGUF Q4_K_M via llama.cpp (with TurboQuant+ fork)
- BF16 weights (won't fit in 32 GB alone, but with tensor offloading...)

---

## 11. Open Questions (Need Empirical Testing)

1. **Does head_dim=512 work with TurboQuant?** No documentation confirms or denies this. The math should work (TurboQuant is dimension-agnostic in theory), but the Triton kernels may have hard-coded assumptions.

2. **Does `--attention-backend CUSTOM` conflict with `--moe-backend marlin`?** These control different things (attention vs MoE routing), but they both affect the execution graph.

3. **What's the actual VRAM usage?** The 15.7 GB estimate is from the model card on DGX Spark. RTX 5090 may differ slightly due to different memory alignment or CUDA runtime overhead.

4. **Is the Marlin backend needed on RTX 5090?** The model card says it's for SM 12.1 (DGX Spark). RTX 5090 is SM 12.0 (Blackwell consumer). The `VLLM_NVFP4_GEMM_BACKEND=marlin` env var may need adjustment.

5. **What's the actual decode throughput?** The 48.2 tok/s on DGX Spark is the only benchmark. RTX 5090 results haven't been published for this specific model.

---

## 12. Summary of Recommendations

1. **Download the model** -- no gating, Apache 2.0, straightforward HuggingFace download
2. **Start with NVFP4 + FP8 KV** -- proven configuration, measure baseline
3. **Try the pip plugin first** -- `pip install turboquant-vllm[vllm]` + `--attention-backend CUSTOM`
4. **If head_dim=512 fails**, try skipping global layers: only compress sliding window layers (less impact but safe)
5. **If pip plugin conflicts with modelopt**, build from PR #38479 branch which has better hybrid attention handling
6. **Measure everything**: VRAM after load, VRAM during inference at various context lengths, TTFT, decode tok/s, output quality
7. **KV cache is NOT the bottleneck for this model** -- the hybrid architecture with 5 global layers means FP8 KV is already very efficient. TurboQuant's value is for batch serving, not context extension.

---

## Sources

- [bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 (HuggingFace)](https://huggingface.co/bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4)
- [vLLM TurboQuant Issue #38171](https://github.com/vllm-project/vllm/issues/38171)
- [vLLM TurboQuant PR #38479](https://github.com/vllm-project/vllm/pull/38479)
- [turboquant-vllm pip package](https://github.com/Alberto-Codes/turboquant-vllm)
- [TurboQuant+ llama.cpp fork](https://github.com/TheTom/turboquant_plus)
- [TurboQuant paper (arXiv:2504.19874)](https://arxiv.org/abs/2504.19874)
- [vLLM Gemma 4 Recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
- [vLLM Hybrid KV Cache Manager](https://docs.vllm.ai/en/latest/design/hybrid_kv_cache_manager/)
- [vLLM Quantized KV Cache Docs](https://docs.vllm.ai/en/latest/features/quantization/quantized_kvcache/)
- [NVIDIA Gemma 4 Blog](https://developer.nvidia.com/blog/bringing-ai-closer-to-the-edge-and-on-device-with-gemma-4/)
- [vLLM 0.19.0 Release](https://github.com/vllm-project/vllm/releases)
- [DGX Spark TurboQuant Results (NVIDIA Forums)](https://forums.developer.nvidia.com/t/dgx-spark-gb10-vllm-0-19-1-turboquant-kv-cache-integration-results-on-qwen3-5-and-nemotron-including-gather-free-triton-decode-and-cuda-wph-decode/365627)
- [varjoranta/turboquant-vllm (TurboQuant+)](https://github.com/varjoranta/turboquant-vllm)
