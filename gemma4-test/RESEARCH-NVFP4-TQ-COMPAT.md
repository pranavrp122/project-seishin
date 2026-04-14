# NVFP4 Weight Quantization + TurboQuant KV Cache: Compatibility Research

**Date:** 2026-04-14
**Verdict:** (c) Simply untested — likely workable with the right approach, but page size is a real (fixable) constraint for hybrid models specifically.

---

## Executive Summary

The "page size conflict" from the previous research pass was **partially correct but misattributed**. The page size issue affects **hybrid architectures** (Mamba+attention models like Qwen3.5) — not the interaction between weight quantization and KV cache quantization. Weight quantization (NVFP4/modelopt) and KV cache quantization (TurboQuant) operate on genuinely independent code paths in vLLM. Nobody has tested the combination, but there is no architectural reason it cannot work for pure-attention models like Gemma 4.

---

## 1. Are They Independent Code Paths?

**Yes.** The two systems touch different parts of vLLM:

### Weight Quantization (NVFP4/modelopt)
- Lives in `vllm/model_executor/layers/quantization/modelopt.py`
- `ModelOptNvFp4Config` handles weight loading and GEMM dispatch
- Uses `nvfp4_utils.py` with CUTLASS/FlashInfer FP4 backends for linear layers
- The `KVCacheMethodCls` on `ModelOptNvFp4Config` is set to `ModelOptFp8KVCacheMethod` — meaning it defaults to FP8 KV cache, but this is a default, not a hard constraint

### KV Cache Quantization (TurboQuant)
- Lives in the attention backend layer
- PR #38479: registers as a CUSTOM attention backend with new kv-cache-dtype values (`turboquant_k8v4`, `turboquant_4bit_nc`, `turboquant_3bit_nc`)
- PR #38280: alternative approach registering as a new `--kv-cache-dtype` option
- Quantization happens at KV store time via fused Triton kernels — no weight modifications needed
- The `kv_cache_dtype` parameter drives attention backend selection independently of `--quantization`

### How They Interact
- `--quantization modelopt` controls how **weight tensors** are loaded and how **linear layer GEMMs** execute
- `--kv-cache-dtype` controls how **KV tensors** are stored/retrieved in the paged attention cache
- The dispatch macro `DISPATCH_BY_KV_CACHE_DTYPE` in `cache_kernel.cu` and `attention_kernel.cu` routes based on `kv_cache_dtype` string — completely independent of weight quantization method
- The `CacheDType` validation in `vllm/config/cache.py` has **no conditional checks** that block specific weight quantization + KV cache dtype combinations

## 2. The Page Size Issue — What It Actually Is

The page size conflict is **real but specific to hybrid architectures**, not weight quantization:

- vLLM's `unify_kv_cache_spec_page_size()` in `kv_cache_utils.py` requires all KV cache specs in a cache group to have compatible page sizes
- TurboQuant uses uint8 nibble-packed slots (~95 bytes per slot vs ~256 bytes for bf16)
- This clashes with **Mamba state cache pages** in hybrid models (Qwen3.5, Jamba, etc.)
- Error: `NotImplementedError: The page size of the layer is not divisible by the maximum page size`
- **This has nothing to do with weight quantization** — it's about mixing attention-type layers with non-attention state layers

For **Gemma 4 26B-A4B** (pure MoE with standard attention + no Mamba layers), the page size issue should not apply.

There is an RFC for nonuniform page sizes (Issue #25314) proposing `_get_kv_cache_groups_uniform_type_nonuniform_page_size()` to fix this for hybrid models.

## 3. PR #38479 (TurboQuant Native Backend) — ModelOpt Mentions

**None.** The PR:
- Contains zero mentions of modelopt, NVFP4, or weight quantization compatibility
- Was tested only with unquantized base models (Qwen3-4B, Nemotron)
- Explicitly scopes out hybrid architectures for a follow-up PR
- Weight quantization composition appears to be implicitly deferred/untested

## 4. Attention Backend Selection with modelopt + Custom KV Cache

Current behavior:
- `ModelOptNvFp4Config` sets `KVCacheMethodCls = ModelOptFp8KVCacheMethod` — this is the **default** KV cache method when using NVFP4 weights
- The `--kv-cache-dtype` CLI argument can override this default
- vLLM's attention backend selector (`selector.py`) picks backends based on `kv_cache_dtype`, not `--quantization`
- FlashAttention-2 is rejected for FP8 KV cache (falls back to FlashInfer/XFormers)
- TurboQuant would use its own CUSTOM attention backend, which is selected based on `kv_cache_dtype` containing "turboquant"

**Key question:** Does `ModelOptNvFp4Config.KVCacheMethodCls = ModelOptFp8KVCacheMethod` hard-override the `--kv-cache-dtype` CLI arg? Or does the CLI arg take precedence? This needs testing. The code suggests CLI should win since `kv_cache_dtype` flows through `CacheConfig` before hitting the quantization layer.

## 5. Known Working Combinations (Weight Quant + KV Cache Quant)

GPTQ/AWQ + FP8 KV cache is a **proven working combination** in vLLM:

```bash
# Working example: GPTQ weights + FP8 KV cache
VLLM_ATTENTION_BACKEND=FLASHINFER vllm serve \
  /path/to/GPTQ-model/ \
  --kv-cache-dtype fp8 \
  --dtype float16
```

This confirms that weight quantization and KV cache quantization are architecturally independent in vLLM. The same principle should extend to NVFP4 + TurboQuant.

## 6. TurboQuant Plugin Repos

### varjoranta/turboquant-vllm
- Offers AWQ export capability for TQ-compressed weights
- Supports asymmetric K/V bit widths (noted as "required for quantized weight models")
- **No mention of modelopt or NVFP4**
- The "required for quantized weight models" note suggests awareness that quantized-weight models need asymmetric KV compression, but no testing documented

### Alberto-Codes/turboquant-vllm
- Registers via `--attention-backend CUSTOM` plugin system
- KV cache compressed to 68 bytes/token/head vs 256 bytes FP16
- **No mention of modelopt or NVFP4**

## 7. What Would Need to Happen for NVFP4 + TurboQuant

For Gemma 4 26B-A4B specifically:

1. **TurboQuant must be merged or installed as plugin** — PR #38479 or one of the community forks
2. **CLI override must work:** `--quantization modelopt --kv-cache-dtype turboquant_k8v4` — the `kv_cache_dtype` must override the default `ModelOptFp8KVCacheMethod`
3. **No hybrid model page size issue** — Gemma 4 is pure attention, so this shouldn't trigger
4. **Attention backend routing must not conflict** — TurboQuant's CUSTOM backend handles attention; modelopt's NVFP4 handles linear layers. These are separate kernel dispatch paths.

### Potential Blockers
- If `ModelOptNvFp4Config` hard-codes FP8 KV cache and ignores CLI `--kv-cache-dtype`, you'd need to patch the config class
- If TurboQuant's attention backend assumes bf16 input projections (Q/K/V before caching), NVFP4's different activation format could cause issues — but NVFP4 W4A16 would output FP16 activations, so this should be fine. W4A4 would need checking.
- The `CacheDType` enum in `cache.py` currently does NOT include turboquant dtypes — TurboQuant PRs add them, but they're not merged yet

## 8. Recommended Test Plan

```bash
# Step 1: Verify NVFP4 alone works
vllm serve nvidia/gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --dtype auto

# Step 2: Verify TurboQuant alone works (after PR merge or plugin install)
vllm serve google/gemma-4-26B-A4B-it \
  --kv-cache-dtype turboquant_k8v4

# Step 3: Combine them
vllm serve nvidia/gemma-4-26B-A4B-it-NVFP4 \
  --quantization modelopt \
  --kv-cache-dtype turboquant_k8v4

# If step 3 fails with KVCacheMethod conflict, try:
# - Patching ModelOptNvFp4Config.KVCacheMethodCls to None
# - Using --attention-backend CUSTOM explicitly
# - Using the varjoranta fork which has asymmetric K/V for quantized models
```

## 9. Conclusion

| Aspect | Status |
|--------|--------|
| Fundamental architectural constraint? | **No.** Weight quant and KV cache quant are independent code paths. |
| Page size conflict? | **Real but irrelevant for Gemma 4.** Only affects hybrid Mamba+attention models. |
| Bug/oversight blocking it? | **Possibly.** `ModelOptNvFp4Config.KVCacheMethodCls` defaults to FP8 KV — may need CLI override or patch. |
| Simply untested? | **Yes.** No one has documented testing NVFP4 + TurboQuant together. |
| Known workaround? | **GPTQ/AWQ + FP8 KV cache works today**, suggesting the pattern is sound. TurboQuant just needs the same treatment. |
| Recommended path? | Test it. High probability of working for Gemma 4 with minor config adjustments. |

---

## Sources

- [PR #38479 — TurboQuant attention backend](https://github.com/vllm-project/vllm/pull/38479)
- [PR #38280 — TurboQuant kv-cache-dtype](https://github.com/vllm-project/vllm/pull/38280)
- [Issue #38171 — TurboQuant feature request](https://github.com/vllm-project/vllm/issues/38171)
- [Issue #25314 — Nonuniform page size RFC](https://github.com/vllm-project/vllm/issues/25314)
- [Issue #37121 — KV cache overestimation for hybrid models](https://github.com/vllm-project/vllm/issues/37121)
- [Issue #32220 — NVFP4 KV cache support](https://github.com/vllm-project/vllm/issues/32220)
- [Issue #37854 — ModelOpt MIXED_PRECISION whitelist bug](https://github.com/vllm-project/vllm/issues/37854)
- [Issue #38980 — ModelOpt NVFP4 Qwen3 loading bug](https://github.com/vllm-project/vllm/issues/38980)
- [varjoranta/turboquant-vllm](https://github.com/varjoranta/turboquant-vllm)
- [Alberto-Codes/turboquant-vllm](https://github.com/Alberto-Codes/turboquant-vllm)
- [vLLM quantization docs](https://docs.vllm.ai/en/stable/features/quantization/modelopt/)
- [NVIDIA Model-Optimizer](https://github.com/NVIDIA/Model-Optimizer)
- [vLLM Q1 2026 Roadmap](https://github.com/vllm-project/vllm/issues/32455)
