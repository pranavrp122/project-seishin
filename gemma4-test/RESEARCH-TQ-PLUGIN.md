# TurboQuant-vLLM Plugin: Compatibility with NVFP4 MoE (Gemma 4 26B-A4B)

**Researched:** 2026-04-14
**Verdict:** NOT COMPATIBLE as a direct combo. Use varjoranta fork with its own weight compression OR use NVFP4 + FP8 KV cache instead.

---

## Executive Summary

Combining the turboquant-vllm KV cache plugin with NVFP4 weight quantization on Gemma 4 26B-A4B faces three independent blockers:

1. **Page size conflict** -- TurboQuant CUSTOM attention backend uses uint8 nibble-packed KV slots (95 bytes) vs vLLM's standard page layout (256 bytes for bf16). The `--quantization modelopt` path expects standard attention backend page sizes. These cannot be reconciled without framework-level changes.

2. **head_dim=512 unsupported** -- Gemma 4's 10 global attention layers use head_dim=512. The Alberto-Codes plugin only validates up to head_dim=256. FlashAttention and FlashInfer don't support 512 either -- vLLM forces TRITON_ATTN for these layers. The CUSTOM backend has no Triton fallback for 512-dim heads.

3. **MoE not tested on Alberto-Codes** -- The original plugin's validated model list stops at dense models. MoE routing adds no KV cache complications (KV is per-layer, not per-expert), but the hybrid attention architecture is the real blocker.

**The varjoranta fork solves problems 1 and 3** (MoE validated on Qwen3-30B-A3B, GLM-4.7-Flash), and claims Gemma 4 quality at 4.79/5. But it uses its own TQ3 weight compression (not NVFP4) and does not document NVFP4 coexistence.

---

## Detailed Analysis

### Q1: MoE Compatibility

**Answer: MoE architecture itself is not a KV cache problem.**

KV cache is generated per attention layer, not per expert. The MoE routing only affects the FFN layers. So TurboQuant's KV compression has no architectural conflict with MoE routing.

The varjoranta fork validates this:
- Qwen3-30B-A3B (MoE): full CUDA graph capture, no `--enforce-eager` needed
- GLM-4.7-Flash 355B (MoE): compressed from 62.4 GB to 14.7 GB
- Gemma 4 26B-A4B (MoE): 4.79/5 quality score

**Confidence: HIGH** (varjoranta fork demonstrates it working)

### Q2: NVFP4 + CUSTOM Attention Backend Coexistence

**Answer: They conflict. Cannot use both simultaneously.**

The conflict chain:
1. NVFP4 requires `--quantization modelopt` and `--moe-backend marlin`
2. TurboQuant plugin requires `--attention-backend CUSTOM`
3. The CUSTOM backend changes KV cache page layout (uint8 nibble-packed, 95 bytes/slot)
4. ModelOpt's weight dequantization path expects standard KV cache memory layout
5. vLLM requires all KV cache specs in a cache group to have compatible page sizes

This is a framework-level architectural constraint, not a simple flag conflict. The page size mismatch means vLLM cannot allocate a unified paged KV cache that satisfies both the TurboQuant compression format and the standard decode path.

**Confidence: HIGH** (multiple sources confirm page size incompatibility)

### Q3: head_dim=512 Support

**Answer: Neither plugin version handles head_dim=512 correctly.**

Gemma 4 architecture:
- 25 sliding window layers: head_dim=256
- 5 global attention layers: head_dim=512

Backend support for head_dim=512:
| Backend | head_dim=512 | Notes |
|---------|-------------|-------|
| FlashAttention | NO | Max 256 |
| FlashInfer | NO | Supports [64, 128, 256] only |
| TRITON_ATTN | YES | vLLM auto-selects this for Gemma 4 |
| TQ CUSTOM (Alberto) | NO | Only validated up to 256 |
| TQ CUSTOM (varjoranta) | UNCLEAR | Claims Gemma 4 works, but no explicit 512 docs |

The varjoranta fork scores 4.79/5 on Gemma 4, which implies it handles both head dimensions. The llama.cpp TurboQuant fork explicitly mentions "D=256/512 heads" support. But the vLLM plugin documentation doesn't confirm the mechanism.

Likely approach: the varjoranta fork either (a) uses TRITON_ATTN as the underlying kernel and wraps it with TQ compression, or (b) has custom Triton kernels for 512-dim heads. The 128-element block size for norms (documented in the README) would need 4 blocks per 512-dim head vector.

**Confidence: MEDIUM** (working quality scores exist, but implementation details undocumented)

### Q4: Sliding Window + Global Hybrid Handling

**Answer: The varjoranta fork handles this. Alberto-Codes fork does not.**

Alberto-Codes lists "sliding window attention bypass (Gemma 2/3)" on the roadmap, meaning it skips compression on sliding window layers. This is insufficient for Gemma 4 which has BOTH sliding window AND global layers with different head dimensions.

The varjoranta fork validates Gemma 4 end-to-end, so it must handle the hybrid architecture. The original llama.cpp TurboQuant fork explicitly handles "D=256/512 heads" with separate kernel paths.

**Confidence: MEDIUM** (inferred from working results, not from code inspection)

### Q5: Which Version to Use

**Answer: varjoranta/turboquant-vllm (turboquant-plus-vllm on pip)**

| Feature | Alberto-Codes (original) | varjoranta (fork) |
|---------|-------------------------|-------------------|
| Package | `turboquant-vllm` | `turboquant-plus-vllm` |
| Version | v1.5.0 (2026-04-08) | Unknown |
| MoE support | Not tested | Validated (Qwen3-30B, GLM-4.7) |
| Gemma 4 | Not supported | Validated (4.79/5 quality) |
| head_dim=512 | Not supported | Likely supported (via results) |
| CUDA kernels | PyTorch + Triton | Fused CUDA (A100/H100) |
| Asymmetric K/V | Via env vars | Built-in, recommended |
| MLA support | No | Yes (GLM-4.7, DeepSeek-V3) |
| Weight compression | No (KV only) | Yes (TQ3 weights) |
| NVFP4 coexistence | No | No (uses own weight compression) |

**Use the varjoranta fork. It's the only option that works with Gemma 4.**

### Q6: Optimal TQ4_K_BITS / TQ4_V_BITS for Gemma 4

**Answer: K4/V3 (asymmetric)**

From the varjoranta README: "K precision dominates quality (controls softmax routing). V can be compressed more aggressively. K4/V3 gives better compression AND better quality than symmetric turbo3."

For Gemma 4 specifically:
- K4/V3: Recommended default. 3.8x KV cache reduction.
- K4/V4: If quality is paramount. 3.0x reduction.
- K3/V3: Maximum compression. Not recommended for Gemma 4 (global layers with 512-dim heads need higher K precision).

Environment variables (if using env-var activation):
```bash
export TQ_KV_K_BITS=4
export TQ_KV_V_BITS=3
export TQ_KV_ROTATION=wht  # Walsh-Hadamard, faster than Givens
```

**Confidence: MEDIUM** (general recommendation, not Gemma-4-specific tuning data)

### Q7: Fallback Plan

If TurboQuant doesn't work with NVFP4 MoE, the options in order of preference:

#### Option A: NVFP4 weights + FP8 KV cache (RECOMMENDED FALLBACK)
```bash
vllm serve /path/to/Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --kv-cache-dtype fp8 \
  --moe-backend marlin \
  --gpu-memory-utilization 0.90 \
  --trust-remote-code
```
- 2x KV compression (vs 3.8x from TQ)
- Proven working on DGX Spark: 16.5 GB model + 82 GB for KV
- Community-validated by bg-digitalservices
- Requires gemma4_patched.py for correct NVFP4 scale key mapping

#### Option B: varjoranta TQ3 weights + TQ K4/V3 KV cache (ALL-TQ approach)
```bash
pip install turboquant-plus-vllm
# Uses TQ3 weight compression instead of NVFP4
vllm serve google/gemma-4-26B-A4B-it \
  --attention-backend CUSTOM
```
- 52 GB BF16 -> 12 GB model (TQ3 weights) + 3.8x KV compression
- Quality: 4.79/5
- Throughput: reportedly 7-17% of BF16 (significant penalty)
- No NVFP4, no modelopt, no patching needed

#### Option C: FP8 weights + FP8 KV cache
```bash
vllm serve google/gemma-4-26B-A4B-it \
  --quantization fp8 \
  --kv-cache-dtype fp8
```
- 2x weight compression + 2x KV compression
- Works out of the box (issue #39000 confirms fp8 works)
- Less memory savings than NVFP4 (2x vs ~3x)

#### Option D: No KV compression
```bash
vllm serve /path/to/Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --moe-backend marlin \
  --trust-remote-code
```
- NVFP4 weights only, BF16 KV cache
- Maximum quality, minimum context window
- Only viable if context requirements are modest (<16K on 24GB)

### Q8: Native PR #38479 Status

**Answer: Open, not close to merging. Don't wait for it.**

Status as of 2026-04-14:
- Submitted 2026-03-29, extensive review ongoing
- **Does NOT support hybrid models** -- code explicitly bypasses TurboQuant with `if not model_config.is_hybrid`
- Multiple blocking issues: quality regression (0% GSM8K on Qwen3-4B with defaults), Ampere FP8 crash, performance bugs (.item() GPU sync), missing tests
- Only validates head_dim=128
- Reviewers requested explicit user warnings when TurboQuant is requested but auto-disabled for hybrid architectures

Even if merged, it won't help Gemma 4 (hybrid model) without follow-up PRs.

**Confidence: HIGH** (directly from PR review comments)

### Q9: Performance Overhead

**Answer: Expect significant throughput penalty.**

| Source | Model | Hardware | Throughput Impact |
|--------|-------|----------|------------------|
| Alberto-Codes | Llama-3.1-8B | RTX 4090 | -7.3% at high concurrency |
| PR #38479 | Qwen3-4B | 4x RTX PRO 6000 | -21% to -35% (short decode) |
| varjoranta | Gemma 4 26B | A100 80GB | 816 tok/s output (no baseline given) |
| varjoranta | General | - | "7-17% of BF16 throughput" (Triton kernel overhead) |

The 7-17% throughput figure is alarming. This appears to be a worst-case for the TQ3 weight compression path (which touches both weights AND KV). For KV-only compression (the plugin approach), expect:
- **Prefill**: Minimal impact (compute-bound, not memory-bound)
- **Decode (short context)**: -7% to -20% (overhead of quantize/dequantize)
- **Decode (long context)**: FASTER (memory bandwidth savings outweigh compute)

On RTX 5090 vs 4090: SM 12.1 (Blackwell) has higher memory bandwidth (1792 GB/s vs 1008 GB/s) but also higher compute throughput. The TQ overhead ratio should be similar or slightly better due to Blackwell's improved Triton kernel support.

**Confidence: LOW** (no RTX 5090 benchmarks exist for TQ)

### Q10: Testing / Verification Approach

To verify TurboQuant is working correctly:

#### 1. VRAM Measurement (primary signal)
```bash
# Without TQ
nvidia-smi --query-gpu=memory.used --format=csv -l 1

# Expected: KV cache should be ~3.8x smaller with K4/V3
# For 8K context on Gemma 4: ~200MB BF16 -> ~53MB TQ K4/V3
```

#### 2. Cosine Similarity Check
The Alberto-Codes plugin includes per-layer cosine similarity reporting:
```python
from turboquant_vllm import CompressedDynamicCache
# Compare compressed vs uncompressed outputs
# Minimum acceptable: >0.97 per layer
```

#### 3. Quality Benchmarks
```bash
# Quick sanity check with lm-eval
lm_eval --model vllm \
  --model_args pretrained=google/gemma-4-26B-A4B-it \
  --tasks gsm8k \
  --batch_size auto \
  --num_fewshot 5
```

#### 4. Log Verification
```bash
# vLLM should log which attention backend is active
# Look for: "Using attention backend: CUSTOM" or "TurboQuant"
# If you see "Using attention backend: TRITON_ATTN" -- TQ plugin didn't activate
```

#### 5. Silent Fallback Detection
vLLM's plugin discovery is silent. If the entry point isn't registered, vLLM falls back to default without error. Always verify via logs that CUSTOM backend is active.

---

## Recommendation for RTX 5090 (32GB VRAM)

### Primary Path: NVFP4 + FP8 KV Cache

This is the battle-tested approach. No experimental plugins.

```bash
# 1. Get the community NVFP4 checkpoint
huggingface-cli download bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4

# 2. Apply the vLLM patch for NVFP4 MoE scale keys
# Download gemma4_patched.py from the model repo
# Mount it over vllm/model_executor/models/gemma4.py

# 3. Serve
vllm serve /path/to/Gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --kv-cache-dtype fp8 \
  --moe-backend marlin \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --max-num-seqs 1 \
  --trust-remote-code \
  --dtype auto
```

**Expected memory budget on 32GB:**
- Model weights (NVFP4): ~16.5 GB
- KV cache (FP8, 32K context): ~4-6 GB
- Activations + overhead: ~3-4 GB
- Total: ~24-27 GB -- fits in 32GB with margin

### Experimental Path: varjoranta TQ3 (test later)

If FP8 KV cache proves insufficient for context length needs:

```bash
pip install turboquant-plus-vllm
pip install 'transformers>=5.5'

vllm serve google/gemma-4-26B-A4B-it \
  --attention-backend CUSTOM
```

This uses TQ3 for BOTH weights and KV, avoiding the NVFP4 conflict entirely. But:
- Throughput penalty is severe (7-17% of BF16)
- Less battle-tested than NVFP4 path
- 12 GB model + aggressive KV compression = more context headroom

### What NOT to Do

1. **Do NOT combine** `--attention-backend CUSTOM` with `--quantization modelopt` -- page size conflict will cause crashes or silent corruption
2. **Do NOT use** Alberto-Codes original plugin with Gemma 4 -- no head_dim=512, no MoE validation
3. **Do NOT wait** for native PR #38479 -- it explicitly skips hybrid models like Gemma 4
4. **Do NOT use** `--quantization mxfp4` for runtime FP4 -- crashes on Gemma 4 MoE (issue #39000, 2D vs 3D tensor shape mismatch)

---

## Sources

### Primary (HIGH confidence)
- [Alberto-Codes/turboquant-vllm GitHub](https://github.com/Alberto-Codes/turboquant-vllm) -- original plugin, v1.5.0
- [varjoranta/turboquant-vllm GitHub](https://github.com/varjoranta/turboquant-vllm) -- fork with MoE + Gemma 4 support
- [vLLM PR #38479](https://github.com/vllm-project/vllm/pull/38479) -- native TurboQuant backend (open, hybrid models excluded)
- [bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4](https://huggingface.co/bg-digitalservices/Gemma-4-26B-A4B-it-NVFP4) -- community NVFP4 checkpoint with vLLM patch
- [vLLM Issue #39000](https://github.com/vllm-project/vllm/issues/39000) -- MXFP4 runtime crash on Gemma 4 MoE
- [vLLM Issue #38918](https://github.com/vllm-project/vllm/issues/38918) -- Gemma 4 head_dim=512 shared memory limits

### Secondary (MEDIUM confidence)
- [vLLM Issue #38171](https://github.com/vllm-project/vllm/issues/38171) -- TurboQuant feature request
- [NVIDIA Gemma 4 blog](https://developer.nvidia.com/blog/bringing-ai-closer-to-the-edge-and-on-device-with-gemma-4/) -- official NVFP4 for 31B dense only
- [DGX Spark Gemma 4 benchmarks](https://ai-muninn.com/en/blog/dgx-spark-gemma4-26b-nvfp4-52-toks) -- 52 tok/s with NVFP4
- [vLLM Gemma 4 recipes](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html) -- official deployment guide

### Low confidence (WebSearch only, needs validation)
- TurboQuant 7-17% throughput figure -- from varjoranta README, not independently benchmarked
- head_dim=512 handling in varjoranta fork -- inferred from quality scores, not from code
- RTX 5090 performance expectations -- no benchmarks exist
