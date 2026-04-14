# Research: llama.cpp for Gemma 4 26B-A4B on RTX 5090

**Researched:** 2026-04-14
**Verdict:** llama.cpp is a viable path but NOT recommended over vLLM for this specific setup.
**Confidence:** HIGH

---

## Executive Summary

llama.cpp has full Gemma 4 26B-A4B support (day-one, April 2, 2026), with multiple GGUF quant options including MXFP4-MOE. TurboQuant KV cache compression works on Gemma 4 via TheTom's fork with validated results. However, for a single-user RTX 5090 setup optimizing for lowest latency, **vLLM with NVFP4 + TurboQuant KV remains the better path** due to native Blackwell FP4 tensor core acceleration that llama.cpp cannot yet match.

The key blocker: llama.cpp's NVFP4 CUDA kernels are not yet functional for Gemma 4 (Issue #21777 -- tensor mapping broken). The MXFP4-MOE quant uses Blackwell FP4 tensor cores for expert layers only, achieving 197 tok/s tg on RTX 5090 vs Q4_K_M's 220 tok/s tg. vLLM's NVFP4 path uses FP4 tensor cores for ALL linear layers, which should yield higher throughput.

---

## 1. Gemma 4 MoE Support in llama.cpp

**Status: FULLY SUPPORTED** (HIGH confidence)

- Day-one support since April 2, 2026
- Works with `llama-cli`, `llama-server`, `llama-mtmd-cli`
- MoE architecture (128 experts, 8 active) fully implemented
- Hybrid attention (5 global + 25 sliding window) handled correctly
- Known fixes applied: PR #21326 (chat template), PR #21343 (tokenizer fix)
- Tool calling works in llama.cpp (broken in Ollama v0.20.0 but fine in llama.cpp from source)

**Command to run:**
```bash
./llama-server \
  -hf unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M \
  --port 8080 -ngl 99 -c 32768 --jinja
```

---

## 2. Available GGUF Quants

**Source:** [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF) (85 files, updated April 11, 2026)

| Quant | Size (approx) | Notes |
|-------|---------------|-------|
| BF16 | ~52 GB | Full precision, won't fit 32GB |
| UD-Q8_K_XL | ~27.9 GB | Near-lossless, tight fit on 32GB |
| Q8_0 | ~26.9 GB | Standard 8-bit |
| MXFP4-MOE | ~16.6 GB | Experts=MXFP4, dense=Q8_0, uses Blackwell FP4 cores |
| UD-Q6_K_XL | ~21 GB | Good quality/size balance |
| UD-Q5_K_S | ~19 GB | Confirmed working on all backends |
| UD-Q4_K_XL | ~17 GB | Dynamic 4-bit |
| UD-IQ4_XS | ~15 GB | "Surprisingly good" per community reports |
| UD-IQ4_NL | ~15 GB | Similar recipe to IQ4_XS |

**Recommendation for 32GB RTX 5090:** Q4_K_M or UD-Q4_K_XL for best quality/VRAM balance. MXFP4-MOE for maximum context length (smallest model footprint at 16.6 GB = 15.4 GB free for KV cache).

---

## 3. FP4/NVFP4 Support Status

**NVFP4 type merged but NOT usable for Gemma 4 on CUDA** (HIGH confidence)

- PR #19769 merged March 11, 2026 -- adds `GGML_TYPE_NVFP4` to ggml
- CPU reference implementation works (ARM NEON optimized)
- **CUDA backend kernels: NOT YET IMPLEMENTED** -- follow-up PRs pending
- **Gemma 4 tensor mapping: BROKEN** -- Issue #21777 open, loader fails with tensor count mismatch for NVFP4 GGUF files
- Community quote: "It will be really nice when GPU support comes for NVFP4 in llama.cpp. For now, it runs mostly on the CPU."

**MXFP4-MOE is different from NVFP4:**
- MXFP4-MOE = block-wise FP4 for MoE expert weights only, dense layers stay Q8_0
- Uses Blackwell FP4 tensor cores for expert layers via `mma.fp4` instruction
- This IS functional on CUDA/RTX 5090 today
- NOT the same as full NVFP4 (which quantizes ALL linear layers to FP4)

---

## 4. TurboQuant+ Fork & Gemma 4

**Status: WORKS on Gemma 4** (MEDIUM-HIGH confidence)

### TheTom's Fork
- Repo: [TheTom/llama-cpp-turboquant](https://github.com/TheTom/llama-cpp-turboquant)
- Research repo: [TheTom/turboquant_plus](https://github.com/TheTom/turboquant_plus) (6.1k stars)
- Supports turbo2 (2-bit, 6.4x), turbo3 (3-bit, 4.6-5.1x), turbo4 (4-bit, 3.8x)

### Gemma 4 Specific Results
- **TurboQuant+ validated on gemma-4-26b-a4b-it**: "99% answer agreement with baseline across all context lengths" (~1K to ~60K tokens), 50% cumulative KV memory savings
- Reddit u/Fearless-Wear8100 tested on M4 Pro 48GB: turbo3 scored 37/37 quality, 8/8 on needle-in-haystack
- RTX 4090 benchmark: Gemma 4 26B at full 262K context, 22.3 GB / 24 GB VRAM, 129 tok/s

### Backend Support
| Backend | turbo3 | turbo4 |
|---------|--------|--------|
| Metal | Full support | Full support |
| CUDA | Functional (tested on 5090) | **Functional** (tested on RTX 3090, +1.2% PPL) |
| HIP/ROCm | Validated (gfx1201) | Validated |

### Build Instructions
```bash
git clone https://github.com/TheTom/llama-cpp-turboquant.git
cd llama-cpp-turboquant
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

# Run with turbo4 KV cache:
./build/bin/llama-server \
  -m gemma-4-26B-A4B-it-Q4_K_M.gguf \
  --cache-type-k q8_0 --cache-type-v turbo4 \
  --port 8080 -ngl 99 -c 131072 --jinja
```

### Asymmetric Configuration (Recommended)
- `--cache-type-k q8_0 --cache-type-v turbo3` = +0.7% PPL only
- K stays high quality, V absorbs compression
- Or `--cache-type-k turbo4 --cache-type-v turbo3` for more savings

---

## 5. RTX 5090 Blackwell Performance

### Critical Build Note
**Use CUDA 12.8, NOT 13.x** for llama.cpp MMQ kernels:
- CUDA 12.8 + MMQ: pp=5611, tg=211 tok/s
- CUDA 13.x + cuBLAS fallback: pp=937, tg=156 tok/s
- **5x prompt processing difference** from wrong CUDA version

```bash
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=120 \
  -DGGML_CUDA_FORCE_CUBLAS=OFF \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.8
cmake --build build -j
```

**UPDATE:** The MXFP4-MOE benchmarks from tlskinner26 used CUDA 13.2 and still got good results (10,733 pp tok/s), suggesting the MXFP4 path uses its own FP4 MMA kernels that bypass the MMQ issue. For Q4_K_M, CUDA 12.8 is still preferred.

### Gemma 4 26B Benchmarks on RTX 5090

| Quant | Model Size | pp512 (tok/s) | tg128 (tok/s) | PPL |
|-------|-----------|---------------|---------------|-----|
| MXFP4-MOE | 13.70 GiB | 10,733 | 196.6 | 3,864 |
| Q4_K_M | 15.85 GiB | 8,744 | 219.9 | 3,615 |

Key observations:
- MXFP4-MOE is +22.7% faster on prompt processing (FP4 tensor cores for experts)
- Q4_K_M is +11.9% faster on token generation (more mature INT kernels)
- Q4_K_M has better perplexity (3,615 vs 3,864)
- Both fit comfortably in 32GB with room for KV cache

---

## 6. VRAM Budget & Context Length Estimates

### Gemma 4 26B KV Cache Architecture
- 5 global layers: full context, head_dim=512, 8 KV heads
- 25 sliding window layers: 1024-token window, head_dim=256, 8 KV heads
- Shared KV cache: last N layers reuse K/V from earlier layers

### KV Cache Size (FP16 baseline, per token)
- Global layers: 5 x 2 x 8 x 512 x 2 bytes = 81,920 bytes/token
- Sliding layers: fixed at 25 x 2 x 8 x 256 x 2 x 1024 = ~100 MB total (constant)
- At 128K context: ~10 GB KV cache (FP16) + ~100 MB sliding = ~10.1 GB

### VRAM Estimates: Q4_K_M + turbo4 KV on RTX 5090 (32 GB)

| Component | Size |
|-----------|------|
| Model weights (Q4_K_M) | 15.85 GiB |
| CUDA overhead / workspace | ~1.5 GiB |
| Sliding window KV (constant) | ~0.1 GiB |
| **Available for global KV** | **~14.5 GiB** |

With turbo4 (3.8x compression on KV):
- FP16 KV per token (global): ~80 KB
- turbo4 KV per token: ~21 KB
- 14.5 GiB / 21 KB per token = **~700K tokens** theoretical max
- **Safe operating context: ~200-300K tokens** (accounting for fragmentation, batch buffers)

With MXFP4-MOE (13.70 GiB) + turbo4 KV:
- Available for KV: ~16.8 GiB
- Theoretical max: ~800K+ tokens
- Safe operating context: ~250-400K tokens

**Either quant can hit 100K+ context easily with turbo4 KV.**

---

## 7. llama.cpp Server: OpenAI API Compatibility

**Fully compatible** (HIGH confidence)

- `llama-server` exposes `/v1/chat/completions` and `/v1/completions` endpoints
- Wire-compatible with OpenAI API -- drop-in replacement
- Supports streaming, tool calling (with template fixes), JSON mode
- `--jinja` flag required for proper Gemma 4 chat template

```bash
# Test with curl:
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4","messages":[{"role":"user","content":"Hello"}],"stream":true}'
```

This satisfies pipeline integration requirements -- same API as vLLM's OpenAI-compatible endpoint.

---

## 8. Head-to-Head: vLLM vs llama.cpp for This Use Case

### Comparison Table

| Dimension | vLLM + NVFP4 + TurboQuant KV | llama.cpp + Q4_K_M + turbo4 KV |
|-----------|-------------------------------|--------------------------------|
| **Token gen (tok/s)** | Est. 150-250 (NVFP4 tensor cores) | 197-220 (measured on 5090) |
| **Prompt processing** | Fast (FP4 all layers) | 8,744-10,733 tok/s (measured) |
| **Quality** | NVFP4: 80-92% on hard reasoning | Q4_K_M PPL 3,615 (better) |
| **VRAM (model)** | 15.7 GB (NVFP4) | 15.85 GB (Q4_K_M) or 13.7 GB (MXFP4) |
| **Max context** | 100K+ with TQ KV | 200K+ with turbo4 KV |
| **KV compression** | turboquant-vllm plugin | TheTom fork (turbo3/turbo4) |
| **Setup complexity** | HIGH (patched vLLM, modelopt, pip plugin) | MEDIUM (fork from source, one binary) |
| **API compatibility** | OpenAI `/v1/chat/completions` | OpenAI `/v1/chat/completions` |
| **Maturity** | vLLM 0.17+ native Blackwell | llama.cpp: battle-tested, huge community |
| **FP4 tensor cores** | YES (all linear layers) | Partial (expert layers only via MXFP4) |
| **Blackwell optimized** | YES (native sm_120) | YES but CUDA 12.8 recommended |
| **Single-user latency** | Slightly higher overhead | Slightly lower overhead |
| **Continuous batching** | YES (overkill for single user) | NO (fine for single user) |

### Quality Comparison
- **NVFP4 (vLLM):** Reports of 80-92% quality on hard non-English reasoning. FP4 across ALL layers is more aggressive.
- **Q4_K_M (llama.cpp):** Standard GGUF 4-bit with proven quality. PPL 3,615. Mixed-precision quantization preserves important layers.
- **Advantage: llama.cpp** -- Q4_K_M is a more mature quant format with better quality preservation than blanket FP4.

### Speed Comparison
- Single-user token generation is comparable (~200 tok/s either way)
- vLLM has overhead from its serving infrastructure even for single user
- llama.cpp is leaner for single-stream inference
- **Roughly even for single user, slight edge to llama.cpp**

### Context Length
- Both can exceed 100K with KV compression
- llama.cpp + turbo4 has more headroom (smaller fixed overhead)
- **Advantage: llama.cpp** -- more VRAM budget flexibility

---

## 9. Known Issues & Risks

### llama.cpp Path
1. **TurboQuant is a fork, not mainline** -- must build from TheTom's repo, not upstream llama.cpp
2. **CUDA 12.8 vs 13.x confusion** -- wrong CUDA version = 5x slower prompt processing
3. **turbo4 CUDA status unclear** -- some reports say "not ported to CUDA," others show it working on RTX 3090. Needs testing.
4. **Fork lag** -- TheTom's fork may fall behind upstream llama.cpp, requiring manual rebasing
5. **Windows MSVC build issues** -- not relevant for your Linux setup but worth noting

### vLLM Path
1. **Patched vLLM required** -- not stock vLLM
2. **NVFP4 quality concerns** -- hard reasoning degradation documented
3. **modelopt dependency** -- additional NVIDIA toolchain required
4. **Heavier runtime** -- more memory overhead from serving infrastructure

---

## 10. Recommendation

### For the Gemma 4 26B-A4B test on RTX 5090:

**Start with llama.cpp + Q4_K_M + turbo4 KV cache.** Here's why:

1. **Simpler setup** -- one binary, one GGUF file, one fork to build
2. **Better quality** -- Q4_K_M preserves quality better than NVFP4 blanket FP4
3. **Comparable speed** -- ~200 tok/s token generation, 8-10K tok/s prompt processing
4. **More context headroom** -- 200K+ tokens achievable vs ~100K for vLLM
5. **Same API** -- OpenAI-compatible `/v1/chat/completions` for pipeline integration
6. **Lower risk** -- battle-tested GGUF quants, huge community, well-understood behavior

**If llama.cpp tok/s proves insufficient**, then switch to vLLM + NVFP4. But for single-user inference with quality as a priority, llama.cpp is the pragmatic choice.

### Concrete Setup Steps

```bash
# 1. Clone TurboQuant fork
git clone https://github.com/TheTom/llama-cpp-turboquant.git
cd llama-cpp-turboquant

# 2. Build with CUDA 12.8 (critical for MMQ kernels)
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=120 \
  -DGGML_CUDA_FORCE_CUBLAS=OFF \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# 3. Download model
./build/bin/llama-server \
  -hf unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M \
  --port 8080 -ngl 99 \
  -c 131072 \
  --cache-type-k q8_0 --cache-type-v turbo4 \
  --jinja

# 4. Test
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4","messages":[{"role":"user","content":"Hello, tell me about yourself."}]}'
```

### Fallback Plan
If turbo4 CUDA doesn't work on the fork, fall back to:
- `--cache-type-k q8_0 --cache-type-v q4_0` (built-in llama.cpp, no fork needed)
- Less compression than turbo4 but still significant savings
- Then evaluate if TurboQuant vLLM plugin offers meaningful advantage

### Test Comparison Plan
Run both engines on the same prompt set and measure:
1. Time-to-first-token (TTFT)
2. Token generation speed (tok/s)
3. Prompt processing speed (tok/s)
4. VRAM usage at 8K, 32K, 64K context
5. Quality on your companion use case (subjective eval)

---

## Sources

- [llama.cpp main repo](https://github.com/ggml-org/llama.cpp)
- [Unsloth Gemma 4 GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF)
- [TurboQuant+ (TheTom)](https://github.com/TheTom/turboquant_plus)
- [TheTom llama.cpp fork](https://github.com/TheTom/llama-cpp-turboquant)
- [NVFP4 PR #19769](https://github.com/ggml-org/llama.cpp/pull/19769)
- [NVFP4 Gemma 4 tensor mapping issue #21777](https://github.com/ggml-org/llama.cpp/issues/21777)
- [Blackwell optimization benchmarks (tlskinner26)](https://github.com/tlskinner26/llama-cpp-blackwell-optimization)
- [TurboQuant upstream discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)
- [Gemma 4 262K context on RTX 4090](https://github.com/conorseabrook/gemma4-turboquant-bench)
- [CUDA Toolkit pitfall for Blackwell](https://zenn.dev/toki_mwc/articles/rtx5090-blackwell-cuda-toolkit-trap-llama-cpp?locale=en)
- [vLLM vs llama.cpp comparison (Red Hat)](https://developers.redhat.com/articles/2025/09/30/vllm-or-llamacpp-choosing-right-llm-inference-engine-your-use-case)
- [Inference engines on RTX 5090 (PatentLLM)](https://media.patentllm.org/blog/ai/vllm-vs-tensorrt-llm-vs-ollama-vs-llamacpp-choosing-the-right-inference-engine-on-rtx-5090)
- [Gemma 4 KV cache architecture (Kaitchup)](https://kaitchup.substack.com/p/gemma-4-31b-and-26b-a4b-architecture)
- [NVIDIA Gemma 4 blog](https://developer.nvidia.com/blog/bringing-ai-closer-to-the-edge-and-on-device-with-gemma-4/)
- [Unsloth Gemma 4 docs](https://unsloth.ai/docs/models/gemma-4)
- [Gemma 4 Hugging Face blog](https://huggingface.co/blog/gemma4)
- [r/LocalLLaMA TurboQuant Gemma 4 discussion](https://bskiller.com/story/8b9e70e4-d69a-46e8-94c4-938cd90ce6cd)
