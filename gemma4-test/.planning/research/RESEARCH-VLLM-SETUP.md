# vLLM Setup Guide: Gemma 4 26B-A4B NVFP4 on RTX 5090

**Researched:** 2026-04-14
**Overall Confidence:** MEDIUM (community model + evolving SM120 support)

---

## Executive Summary

Running Gemma 4 26B-A4B NVFP4 on an RTX 5090 via vLLM is feasible but requires careful setup. The model weights are ~16.5 GB, leaving ~12-14 GB for KV cache on 32GB VRAM -- enough for 32K-64K tokens of context with FP8 KV cache. The main complications are: (1) vLLM needs a patched `gemma4.py` because upstream doesn't correctly map NVFP4 scale keys for MoE experts, (2) you must use `--moe-backend marlin` or get garbage output, and (3) the RTX 5090 (SM120) needs a CUDA 13.0 Docker image. The `vllm/vllm-openai:gemma4-cu130` image should work, but SM120 support in vLLM is still maturing with edge cases.

---

## Step-by-Step Setup

### Step 1: Download the Model

The model is Apache 2.0 licensed. No gating or special access needed.

```bash
# ~16.5 GB download
huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 \
  --local-dir ~/models/gemma4-26b-a4b-nvfp4
```

This downloads both the model weights AND the `gemma4_patched.py` file.

**Verify the patch file exists after download:**
```bash
ls ~/models/gemma4-26b-a4b-nvfp4/gemma4_patched.py
```

### Step 2: Choose Docker Image

**Recommended:** `vllm/vllm-openai:gemma4-cu130`

This is the v0.19.0 release with:
- CUDA 13.0 (required for SM120 / RTX 5090)
- transformers >= 5.5.0 (required for Gemma 4 architecture)
- Gemma 4 MoE + multimodal support
- SM120 CUTLASS blockwise FP8 GEMM fix
- NVFP4 NaN fix for desktop Blackwell

**Alternative images (in order of preference):**

| Image | Notes |
|-------|-------|
| `vllm/vllm-openai:gemma4-cu130` | Best bet -- Gemma 4 specific, CUDA 13.0 |
| `vllm/vllm-openai:v0.19.0-x86_64-cu130-ubuntu2404` | Generic v0.19.0 with CUDA 13.0, confirmed working on Blackwell |
| `vllm/vllm-openai:gemma4` | CUDA 12.9 -- may lack SM120 kernels |

```bash
docker pull vllm/vllm-openai:gemma4-cu130
```

**If the `gemma4-cu130` tag doesn't exist** (it may not -- verify on Docker Hub), fall back to:
```bash
docker pull vllm/vllm-openai:v0.19.0-x86_64-cu130-ubuntu2404
```

### Step 3: Run vLLM

```bash
docker run -d \
  --name vllm-gemma4-test \
  --gpus all \
  --ipc=host \
  --network host \
  --shm-size=8gb \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e VLLM_NVFP4_GEMM_BACKEND=marlin \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  -v ~/models/gemma4-26b-a4b-nvfp4:/model \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/models/gemma4-26b-a4b-nvfp4/gemma4_patched.py:/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py \
  vllm/vllm-openai:gemma4-cu130 \
  vllm serve /model \
    --served-model-name gemma-4 \
    --host 0.0.0.0 \
    --port 8000 \
    --quantization modelopt \
    --dtype auto \
    --kv-cache-dtype fp8 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 32768 \
    --max-num-seqs 1 \
    --moe-backend marlin \
    --trust-remote-code \
    --limit-mm-per-prompt image=0,audio=0
```

### Step 4: Verify Startup

```bash
# Watch logs for successful model loading
docker logs -f vllm-gemma4-test

# Wait for "Uvicorn running on http://0.0.0.0:8000"
# Model loading typically takes 1-3 minutes
```

### Step 5: Test Inference

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4",
    "messages": [{"role": "user", "content": "Hello! Tell me a short joke."}],
    "max_tokens": 200,
    "temperature": 0.7
  }'
```

---

## Flag-by-Flag Explanation

| Flag | Value | Why |
|------|-------|-----|
| `--quantization modelopt` | Required | Tells vLLM this is an NVIDIA ModelOpt NVFP4 checkpoint |
| `--moe-backend marlin` | **Critical** | Without this, CUTLASS MoE runs and produces NaN/garbage. Marlin decompresses FP4 to BF16 at runtime -- slower than native W4A4 but correct |
| `--kv-cache-dtype fp8` | Recommended | Halves KV cache memory, critical on 32GB to maximize context length |
| `--gpu-memory-utilization 0.92` | Tunable | Higher = more KV cache room. Start at 0.92, back off to 0.85 if OOM |
| `--max-model-len 32768` | Conservative start | Model supports up to 262144 (256K) but on 32GB VRAM you have ~12-14GB for KV cache. Start at 32K, try 65536 if it fits |
| `--max-num-seqs 1` | For testing | Single request at a time. Increase later if VRAM allows |
| `--dtype auto` | Required | Auto-detects model precision |
| `--trust-remote-code` | Required | Needed for Gemma 4 architecture |
| `--limit-mm-per-prompt image=0,audio=0` | Optional | Skips multimodal profiling, saves memory. Remove if you need vision |
| `-e VLLM_NVFP4_GEMM_BACKEND=marlin` | **Critical on SM120** | Forces Marlin for non-MoE NVFP4 GEMM layers too |
| `-e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` | Recommended | Better CUDA memory allocation on Blackwell |
| `-e VLLM_WORKER_MULTIPROC_METHOD=spawn` | WSL2 only | Needed for WSL2 stability |

---

## Memory Budget on RTX 5090 (32GB)

| Component | Estimate |
|-----------|----------|
| Model weights (NVFP4) | ~16.5 GB |
| CUDA/framework overhead | ~1-2 GB |
| KV cache (fp8, at 0.92 util) | ~11-12 GB |
| **Total** | ~29-30 GB |

**Context length estimate:** With ~12 GB of FP8 KV cache and `--max-num-seqs 1`, you should get 32K-64K tokens. The exact number depends on overhead; start at 32768 and increase.

**To find your max context:** Remove `--max-model-len` entirely and let vLLM auto-detect, or try progressively larger values (32768 -> 49152 -> 65536) until OOM.

---

## The gemma4_patched.py Explained

**What it fixes:** vLLM's `expert_params_mapping` in `gemma4.py` maps base weight keys correctly but fails on NVFP4 scale keys. Specifically:
- `experts.0.down_proj.weight_scale` gets incorrectly mapped to `experts.w2_weight.weight_scale` (with a dot)
- Should map to `experts.w2_weight_scale` (with underscore, as part of the FusedMoE parameter name)

**Bug tracking:** vLLM issue [#38912](https://github.com/vllm-project/vllm/issues/38912), PR [#39084](https://github.com/vllm-project/vllm/pulls) (open as of 2026-04-14).

**How applied:** Docker volume mount replaces the built-in file:
```
-v /path/to/gemma4_patched.py:/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py
```

**When it becomes unnecessary:** Once PR #39084 merges into vLLM and a new release includes it. Check before running -- if you're on a version newer than v0.19.0, the fix may already be included.

---

## Known Issues and Gotchas

### Critical

1. **Without `--moe-backend marlin` you get garbage output.** CUTLASS MoE produces NaN scale factors on NVFP4 MoE weights. There is no warning -- it just silently outputs nonsense.

2. **Without the patched gemma4.py, weight loading fails with a TypeError.** The scale key mapping is broken in all vLLM versions up to and including v0.19.0.

3. **SM120 Docker image mismatch.** The `vllm/vllm-openai:gemma4` (no cu130 suffix) ships with CUDA 12.9 and may not have SM120 kernel images. You'll get `RuntimeError: CUDA error: no kernel image is available for execution on the device`. Use the cu130 variant.

### Moderate

4. **FlashMLA kernels are Hopper-only.** They should auto-disable on SM120, but if you see FlashMLA errors, the workaround is to force a different attention backend: `--attention-backend flashinfer`.

5. **FP8 is slow on RTX 5090 under WSL2.** WSL2's dxgkrnl doesn't expose Blackwell FP8 cores properly. AWQ Marlin actually beats FP8 on WSL2. This affects `--kv-cache-dtype fp8` performance but not correctness.

6. **bitsandbytes is incompatible with SM120.** Don't try to use `--quantization bitsandbytes` on RTX 5090.

### Minor

7. **First request is slow.** CUDA graph compilation/warmup happens on first inference. Expect 10-30 seconds for the first response, then normal speed after.

8. **Marlin decompresses to BF16 at runtime.** This means you're not getting native W4A4 speed -- more like FP4-weight-only with BF16 compute. Still significantly faster than running the full BF16 model.

9. **This is a community quantization, not official NVIDIA/Google.** Quality is good (97.6% average retention) but it's not the same as an official release.

---

## RTX 5090 Blackwell (SM120) Specific Notes

### What works as of vLLM v0.19.0

- CUDA graphs (no longer need `--enforce-eager`)
- AWQ Marlin quantization
- FlashInfer attention backend
- NVFP4 with Marlin MoE backend (after the NaN fix in v0.19.0)

### Environment for WSL2

```bash
# Required for WSL2 stability
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export VLLM_WORKER_MULTIPROC_METHOD=spawn

# If you see Tailscale-related GPU hangs:
# sudo apt remove tailscale
```

### Your system

- CUDA 13.2, Driver 595.79 -- this is fine. The cu130 Docker image bundles its own CUDA runtime internally; the host driver just needs to be >= the container's CUDA version.

---

## Performance Expectations on RTX 5090

No direct benchmarks exist for this exact combo (NVFP4 MoE on RTX 5090 32GB). Extrapolating from available data:

| Metric | DGX Spark (128GB, GB10) | RTX 5090 Estimate (32GB) |
|--------|------------------------|--------------------------|
| Model load | ~16.5 GB | ~16.5 GB |
| Single-user tok/s | ~48-52 | ~30-50 (memory bandwidth limited) |
| TTFT | ~53ms | ~50-100ms |
| Max context (fp8 KV) | 256K tokens | 32K-64K tokens |

The RTX 5090 has higher memory bandwidth (1792 GB/s) than DGX Spark GB10 (~273 GB/s), so per-token generation speed could actually be faster. But VRAM is the constraint for context length.

---

## Alternative: If This Doesn't Work

If NVFP4 proves too buggy on SM120, fallback options in order of preference:

1. **AWQ INT4 quantization** of Gemma 4 26B-A4B -- ~15GB weights, proven stable on RTX 5090, no patch needed. Look for `gemma-4-26B-A4B-it-AWQ` on HuggingFace.

2. **GGUF via llama.cpp** -- Unsloth provides `unsloth/gemma-4-26B-A4B-it-GGUF` in various quantizations. No Docker needed, but different serving stack.

3. **FP8 quantization** of Gemma 4 26B-A4B -- ~25-30GB, tight fit on 32GB but no patches needed. Use `--quantization fp8`.

---

## Quick Reference Commands

```bash
# Download model
huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 \
  --local-dir ~/models/gemma4-26b-a4b-nvfp4

# Pull Docker image
docker pull vllm/vllm-openai:gemma4-cu130

# Start server
docker run -d \
  --name vllm-gemma4-test \
  --gpus all --ipc=host --network host --shm-size=8gb \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -e VLLM_NVFP4_GEMM_BACKEND=marlin \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v ~/models/gemma4-26b-a4b-nvfp4:/model \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/models/gemma4-26b-a4b-nvfp4/gemma4_patched.py:/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/gemma4.py \
  vllm/vllm-openai:gemma4-cu130 \
  vllm serve /model \
    --served-model-name gemma-4 \
    --host 0.0.0.0 --port 8000 \
    --quantization modelopt \
    --dtype auto \
    --kv-cache-dtype fp8 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 32768 \
    --max-num-seqs 1 \
    --moe-backend marlin \
    --trust-remote-code \
    --limit-mm-per-prompt image=0,audio=0

# Check logs
docker logs -f vllm-gemma4-test

# Test inference
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4","messages":[{"role":"user","content":"Hello!"}],"max_tokens":100}'

# Stop
docker stop vllm-gemma4-test && docker rm vllm-gemma4-test
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `no kernel image is available` | Docker image lacks SM120 | Use `gemma4-cu130` or `v0.19.0-x86_64-cu130-ubuntu2404` |
| `TypeError` during weight loading | Missing gemma4 patch | Mount `gemma4_patched.py` over the vLLM file |
| Garbage/nonsense output | Missing `--moe-backend marlin` | Add the flag |
| NaN in output | Missing `VLLM_NVFP4_GEMM_BACKEND=marlin` env var | Add the env var |
| OOM on startup | `--max-model-len` too high | Reduce to 32768 or lower, reduce `--gpu-memory-utilization` |
| FlashMLA error | Hopper-only kernel on SM120 | Add `--attention-backend flashinfer` |
| Slow first request | CUDA graph warmup | Normal -- wait 10-30s for first request |
| `sm_120 is not compatible` | PyTorch not compiled for Blackwell | Use cu130 Docker image |

---

## Sources

- [bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4 (HuggingFace)](https://huggingface.co/bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4) -- model card with Docker command and patch
- [Gemma 4 26B NVFP4 Benchmark on DGX Spark](https://ai-muninn.com/en/blog/dgx-spark-gemma4-26b-nvfp4-52-toks) -- performance numbers
- [vLLM v0.19.0 Release](https://github.com/vllm-project/vllm/releases/tag/v0.19.0) -- Blackwell fixes, Gemma 4 support
- [vLLM Gemma 4 Blog Post](https://vllm-project.github.io/2026/04/02/gemma4.html) -- official announcement
- [vLLM Gemma 4 Recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html) -- official usage guide
- [Issue #38912: expert_params_mapping bug](https://github.com/vllm-project/vllm/issues/38912) -- the patch rationale
- [Issue #35065: NVFP4 MoE on RTX 5090](https://github.com/vllm-project/vllm/issues/35065) -- SM120 MoE backend failure
- [Issue #37242: RTX 5090 WSL2 working config](https://github.com/vllm-project/vllm/issues/37242) -- CUDA graphs on SM120
- [Issue #36865: SM120 Marlin defaults bug](https://github.com/vllm-project/vllm/issues/36865) -- FlashMLA/Marlin SM120 issues
- [Issue #35432: Prebuilt wheels fail on RTX 50-series](https://github.com/vllm-project/vllm/issues/35432) -- why cu130 is needed
- [BoltzmannEntropy/vLLM-5090](https://github.com/BoltzmannEntropy/vLLM-5090) -- community RTX 5090 Docker
- [jvadura/vLLM-Blackwell](https://github.com/jvadura/vLLM-Blackwell) -- community Blackwell Docker
- [NVIDIA Developer Forums: Gemma 4 NVFP4 in vLLM Docker](https://forums.developer.nvidia.com/t/how-to-run-gemma-4-nvfp4-in-vllm-docker/365513)

---

## Confidence Assessment

| Area | Level | Notes |
|------|-------|-------|
| Model download/size | HIGH | Confirmed from HF model card |
| Docker image tag | MEDIUM | `gemma4-cu130` tag mentioned in search results but not directly verified on Docker Hub |
| gemma4_patched.py | HIGH | Well-documented bug, patch ships with model, tracked in vLLM #38912 |
| `--moe-backend marlin` requirement | HIGH | Multiple sources confirm garbage without it |
| SM120 compatibility | MEDIUM | v0.19.0 has fixes but edge cases remain; community still reporting issues |
| Memory/context estimates | MEDIUM | Extrapolated from DGX Spark numbers, not directly measured on RTX 5090 |
| Performance estimates | LOW | No direct RTX 5090 + NVFP4 benchmarks found |
| WSL2 environment vars | MEDIUM | Confirmed working for other models on RTX 5090, not specifically for this model |

## Open Questions

1. **Does `vllm/vllm-openai:gemma4-cu130` actually exist?** Verify on Docker Hub. If not, use `v0.19.0-x86_64-cu130-ubuntu2404`.
2. **Exact max-model-len on 32GB?** Need to test empirically. Start at 32768.
3. **Is `--attention-backend flashinfer` needed on SM120?** May auto-select correctly in v0.19.0.
4. **Has PR #39084 merged yet?** If so, the patch file may no longer be needed in newer vLLM versions.
5. **Performance on RTX 5090 vs DGX Spark?** RTX 5090 has 6.5x more memory bandwidth but 4x less VRAM. Token generation could be faster, context is shorter.
