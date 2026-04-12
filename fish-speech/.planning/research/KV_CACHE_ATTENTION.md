# KV Cache & Attention Optimization Research

**Target hardware**: RTX 5090 (SM120 Blackwell, 32GB GDDR7, ~2TB/s bandwidth, 209.5 TFLOPS BF16)
**Model**: DualAR transformer -- 36 layers, 2560 dim, 32 query heads, 8 KV heads (GQA 4:1), head_dim=128, max_seq_len=4096
**Current stack**: PyTorch 2.8.0+cu128, standard SDPA, full BF16 KV cache pre-allocated at 4096 tokens (~560MB)
**Date**: April 2026

---

## Critical SM120 Context

SM120 (consumer Blackwell / RTX 5090) is **architecturally different** from SM100 (datacenter Blackwell / B200). Key differences:

- SM120 uses HMMA (register-to-register MMA, same family since Volta/Ampere). No TMEM, no tcgen05 instructions.
- SM100 has dedicated Tensor Memory (TMEM) subsystem enabling warp-specialized kernel designs.
- FlashAttention-3 targets SM90 (Hopper), FlashAttention-4 targets SM100 only. **Neither will ever run on SM120.**
- SM120 effectively uses SM89 (Ada) class kernels for most attention workloads.
- Triton-generated kernels work on SM120 and are the primary compilation target.

---

## 1. FlashAttention-2 (Compiled for SM120)

**What**: FlashAttention-2 compiled with SM120 target. FA2 uses tiling and online softmax to avoid materializing the full attention matrix, achieving O(N) memory and fused I/O.

**Expected impact**: 2-4x speedup over naive SDPA for prefill; modest decode improvement. No VRAM savings for KV cache itself, but reduces peak attention scratch memory.

**Compatibility**: Works on SM120 with caveats.
- `flash-attn==2.8.0` reported working with CUDA 12.8 + torch 2.7.1. Earlier 2.7.x versions fail.
- Community-compiled wheels exist (`loscrossos/lib_flashattention` on GitHub, v2.7.4.post1).
- Compilation from source requires `TORCH_CUDA_ARCH_LIST="12.0"` and can take 6+ hours.
- Runtime arch check in flash-attn may reject SM120 -- requires patching the whitelist.

**Evidence**: 
- [flash-attn issue #1665](https://github.com/Dao-AILab/flash-attention/issues/1665) -- SM120 usage discussion
- [flash-attn issue #2016](https://github.com/Dao-AILab/flash-attention/issues/2016) -- working combination info
- [flash-attn issue #1683](https://github.com/Dao-AILab/flash-attention/issues/1683) -- community wheels

**Implementation complexity**: Medium (compilation pain, arch patching)

**Verdict**: **Investigate further** -- Test whether `flash-attn 2.8.0` works with our torch 2.8.0+cu128 build. If the arch check blocks us, PyTorch's built-in SDPA with `flex_attention` via Triton is the safer path. FA2 is a means to an end (faster attention), not a KV cache optimization per se.

---

## 2. PyTorch FlexAttention (Triton Backend)

**What**: PyTorch 2.5+ native API (`torch.nn.attention.flex_attention`) that compiles custom attention patterns into fused Triton kernels via `torch.compile`. Supports arbitrary `mask_mod` and `score_mod` functions -- including causal, sliding window, and paged patterns.

**Expected impact**: 
- Near-FA2 performance for forward pass via Triton compilation on SM120.
- Enables sliding window, paged attention, and custom masking without writing CUDA.
- FlexDecoding backend auto-activates for short-query / long-KV scenarios (decode phase).
- Native GQA support via `enable_gqa=True` parameter.

**Compatibility**: Excellent for SM120.
- Triton is the primary kernel backend for SM120 (no TMEM dependency).
- GQA broadcasting handled automatically: Q shape `(B, 32, L, 128)`, KV shape `(B, 8, S, 128)`.
- Works with `torch.compile`.
- Known bug: sliding window + FP16 can segfault on backward pass (not relevant for inference-only).

**Evidence**:
- [PyTorch FlexAttention docs](https://docs.pytorch.org/docs/stable/nn.attention.flex_attention.html)
- [FlexAttention blog post](https://pytorch.org/blog/flexattention/)
- [FlexAttention for Inference blog](https://pytorch.org/blog/flexattention-for-inference/)

**Implementation complexity**: Low-Medium (pure Python mask/score mods, torch.compile integration)

**Verdict**: **Try first** -- This is the recommended attention backend for SM120. Native GQA support, sliding window via mask_mod, PagedAttention via block tables, all compiled by Triton. Should be our primary attention path.

---

## 3. SageAttention 2 (INT8 Quantized Attention)

**What**: Quantized attention kernels from Tsinghua ML group. Q/K quantized to INT8, V to FP8 (E4M3) or FP16. Achieves 2-5x speedup over FlashAttention-2 by using INT8 tensor cores for QK matmul.

**Expected impact**: 
- RTX 5090 achieves 560 TOPS with SageAttention (2.7x vs FA2).
- ~35% faster diffusion sampling measured on RTX 5090.
- Does NOT reduce KV cache VRAM -- this is a compute optimization, not memory optimization.

**Compatibility**: SM120 supported.
- Prebuilt wheels available: SageAttention 2.2.0 for SM120 (PyTorch 2.11 nightly, CUDA 12.8).
- Uses SM89 kernels from `csrc/qattn/sm89/` on SM120 -- no SM120-specific kernel needed.
- Safe mode: `sageattn_qk_int8_pv_fp16_cuda` (INT8 Q/K, FP16 V) -- least risk of overflow.
- Requires PyTorch header patch for compilation on SM120.
- **Warning**: Some models produce black/noisy output due to INT8 overflow in certain attention patterns. Must validate with Fish Speech specifically.

**Evidence**:
- [SageAttention GitHub](https://github.com/thu-ml/SageAttention) (ICLR2025, ICML2025, NeurIPS2025)
- [Prebuilt SM120 wheels](https://github.com/mobcat40/sageattention-blackwell)
- [DeepWiki hardware results](https://deepwiki.com/thu-ml/SageAttention/6.3-hardware-specific-results)

**Implementation complexity**: Medium (integration into inference loop, validation for TTS quality)

**Verdict**: **Try** -- High potential speedup. Must validate that INT8 QK quantization doesn't degrade TTS audio quality. Start with the safe `qk_int8_pv_fp16` mode. If quality holds, this is free speed.

---

## 4. KV Cache Quantization (INT8/FP8)

**What**: Quantize cached K and V tensors from BF16 to INT8 or FP8, reducing KV cache memory by 2x.

**Expected impact**:
- Current KV cache: ~560MB at BF16 for 4096 seq len.
- INT8/FP8: ~280MB -- saving ~280MB VRAM.
- For our model (36 layers, 8 KV heads, head_dim=128): `36 * 2 * 8 * 4096 * 128 * 1 byte = ~302MB` at INT8 vs ~604MB at BF16.

**Compatibility**: Multiple paths available.
- **torchao**: Native PyTorch quantization. FP8 attention requires FA3 (SM90) or FA4 (SM100) -- **not available on SM120**.
- **Manual INT8**: Quantize K/V on write, dequantize on read. Simple per-tensor or per-channel quantization. Works with any attention backend.
- **HuggingFace QuantizedCache**: Built-in quantized cache class, but tied to HF model abstractions.

**Evidence**:
- [GPU-Accelerated INT8 KV Cache paper (Jan 2026)](https://arxiv.org/html/2601.04719v1) -- 4x memory reduction, reconstruction error <0.004
- [torchao quantized inference docs](https://docs.pytorch.org/ao/stable/workflows/inference.html)

**Implementation complexity**: Low (manual INT8) to Medium (torchao integration)

**Verdict**: **Try** -- Manual INT8 quantization of KV cache is straightforward and saves ~280MB. The key question is whether INT8 K/V precision is sufficient for TTS attention patterns. FP8 would be ideal but requires FA3/FA4 backends we can't use on SM120. Start with per-channel INT8 symmetric quantization.

---

## 5. TurboQuant / Sub-Byte KV Cache Compression

**What**: Google's ICLR 2026 algorithm for online vector quantization of KV cache. Achieves 3-4 bit compression via random orthogonal rotation (Walsh-Hadamard transform) followed by optimal scalar codebook quantization. No retraining needed.

**Expected impact**:
- 3.8x compression vs FP16 at 4-bit (~148MB KV cache, saving ~412MB).
- Up to 7.1x compression at 2-bit (~79MB).
- 1.9x compression vs FP8 at 4-bit.

**Compatibility**: Several implementations available.
- `pip install aither-kvcache` -- validated on RTX 5090 SM120, uses fused Triton kernels on GPU.
- `pip install turboquant` -- HuggingFace-compatible drop-in.
- `turboquant-pytorch` (tonbistudio) -- from-scratch PyTorch implementation.
- Set `AITHER_TQ_FORCE_TRITON=1` for SM120 (Blackwell) GPUs.
- Achieves 23.6 tok/s single-request on RTX 5090.

**Evidence**:
- [aither-kvcache on PyPI](https://pypi.org/project/aither-kvcache/2.0.0/)
- [TurboQuant paper (ICLR 2026)](https://turbo-quant.com/)
- [turboquant-pytorch GitHub](https://github.com/tonbistudio/turboquant-pytorch)
- Community finding: QJL (Algorithm 2 from paper) hurts quality in practice -- use MSE-optimal quantization only.

**Implementation complexity**: Medium (need to integrate compression/decompression into our KV cache read/write path)

**Verdict**: **Try** -- 3.8x compression at 4-bit is compelling. The aither-kvcache library with Triton kernels on SM120 is the easiest path. However, this is more impactful at longer sequences -- our typical 200-800 token generations make the absolute savings smaller (~37-148MB vs ~70-280MB at BF16). Worth trying if we also want to increase batch size or max sequence length.

---

## 6. Dynamic KV Cache Allocation

**What**: Instead of pre-allocating KV cache for max_seq_len=4096, grow the cache dynamically as tokens are generated.

**Expected impact**:
- Current: ~560MB pre-allocated for 4096 tokens regardless of actual generation length.
- Typical generation (200-800 tokens): only needs ~27-110MB.
- Saves 450-530MB VRAM for typical generations.
- No quality impact -- this is purely a memory management optimization.

**Compatibility**: Native PyTorch.
- HuggingFace `DynamicCache`: concatenates new KV tensors each step. Simple but creates fragmentation.
- Pre-allocate for expected max (e.g., 1024) and grow if needed.
- Best approach: allocate in chunks (e.g., 256-token blocks) to balance fragmentation vs waste.

**Evidence**:
- [HuggingFace KV Cache blog](https://huggingface.co/blog/not-lain/kv-caching)
- [HuggingFace Cache strategies](https://huggingface.co/docs/transformers/en/kv_cache)

**Implementation complexity**: Low

**Verdict**: **Try first** -- This is the lowest-hanging fruit. Our current pre-allocation wastes 80-95% of KV cache VRAM for typical generations. Switch to chunked allocation (e.g., 256-token blocks) or start with a reasonable initial size (512 tokens) and double when exceeded. No quality impact, pure VRAM savings.

---

## 7. Sliding Window Attention

**What**: Limit attention to the most recent W tokens instead of the full sequence. KV cache becomes fixed-size regardless of sequence length.

**Expected impact**:
- Fixed KV cache size = W * (per-token KV size).
- With W=1024: ~137MB fixed regardless of total generation length.
- Reduces attention compute from O(N^2) to O(N*W).
- **Risk**: TTS models may need global attention for prosody coherence across long utterances.

**Compatibility**: Easy with FlexAttention.
```python
def sliding_window_mask(b, h, q_idx, kv_idx):
    return (q_idx >= kv_idx) & ((q_idx - kv_idx) <= WINDOW)
```
- Combine with attention sinks (StreamingLLM): keep first 4 tokens + sliding window.
- No hardware dependency -- works with any attention backend.

**Evidence**:
- [StreamingLLM GitHub](https://github.com/mit-han-lab/streaming-llm) (ICLR 2024)
- [FlexAttention sliding window docs](https://pytorch.org/blog/flexattention/)

**Implementation complexity**: Low (FlexAttention mask_mod) to Medium (if adding attention sinks)

**Verdict**: **Investigate further** -- Sliding window is powerful for memory but risky for TTS. Fish Speech may need full context to maintain prosody/rhythm over long utterances. Need to test with varying window sizes (512, 1024, 2048) and measure audio quality. StreamingLLM's attention sink pattern (keep first few tokens + recent window) could help preserve global context cues.

---

## 8. PagedAttention (Without vLLM)

**What**: Virtual memory-style KV cache management. KV cache stored in non-contiguous fixed-size blocks (pages), mapped via a page table. Eliminates fragmentation and enables efficient memory sharing.

**Expected impact**:
- Near-zero internal fragmentation (waste limited to last page per sequence).
- Enables efficient batch serving with variable-length sequences.
- ~0% VRAM waste vs 50-90% waste with fixed pre-allocation.
- In vLLM benchmarks: 2-4x throughput improvement over naive approaches.

**Compatibility**: Multiple standalone paths.
- **FlexAttention + PagedAttention**: PyTorch-native via `mask_mod` with page table indirection. IBM FMS integration demonstrates this.
- **PyTorch RFC #121465**: Ongoing effort to bring native PagedAttention into PyTorch/TorchAO.
- **IBM FMS**: [foundation-model-stack](https://github.com/thomasjoshi/foundation-model-stack) -- open-source PagedAttention via FlexAttention, works on standard PyTorch.
- Block size typically 16 or 32 tokens.

**Evidence**:
- [PyTorch RFC #121465](https://github.com/pytorch/pytorch/issues/121465)
- [Paged Attention Meets FlexAttention paper](https://arxiv.org/html/2506.07311v1)
- [vLLM PagedAttention design](https://docs.vllm.ai/en/stable/design/paged_attention/)

**Implementation complexity**: High (page table management, block allocator, attention kernel integration)

**Verdict**: **Skip for now** -- PagedAttention shines in multi-request serving scenarios with batch processing. For single-stream TTS inference (our primary use case), dynamic allocation (technique #6) provides most of the benefit with far less complexity. Revisit if we need concurrent multi-user serving.

---

## 9. Token Eviction (H2O / ScissorHands)

**What**: Dynamically evict low-importance KV pairs based on attention score history, maintaining a fixed cache budget.

**Expected impact**:
- H2O/ScissorHands: Keep only top-K important tokens + recent window.
- SqueezeAttention: 30-70% memory savings with layer-wise budget allocation.
- KVzip (NeurIPS 2025 Oral): 3-4x cache reduction, query-agnostic (reusable across queries).

**Compatibility**: 
- H2O, ScissorHands: Pure Python/PyTorch, hardware-agnostic.
- KVzip: [snu-mllab/KVzip](https://github.com/snu-mllab/KVzip) -- supports LLaMA3, Qwen2.5, Gemma3.
- SqueezeAttention: Layer-wise optimal budget, combinable with any eviction method.

**Evidence**:
- [KVzip GitHub](https://github.com/snu-mllab/KVzip) (NeurIPS 2025 Oral)
- [SqueezeAttention paper](https://arxiv.org/html/2404.04793v2)
- [H2O/ScissorHands survey](https://medium.com/@plienhar/llm-inference-series-4-kv-caching-a-deeper-look-4ba9a77746c8)

**Implementation complexity**: Medium-High (need scoring heuristic, eviction logic, careful validation)

**Verdict**: **Skip for now** -- Token eviction methods are designed for long-context LLMs (32K-128K+ tokens). Our max is 4096 tokens with typical generations of 200-800. The complexity-to-benefit ratio is unfavorable at these sequence lengths. Revisit only if we need to support much longer sequences.

---

## 10. GQA-Specific Optimizations

**What**: The model already uses GQA (32 query heads, 8 KV heads). GQA inherently reduces KV cache by 4x vs MHA. Additional optimizations include GQA-aware kernel tuning.

**Expected impact**:
- Already benefiting: KV cache is 4x smaller than equivalent MHA model.
- FlexAttention with `enable_gqa=True` handles head broadcasting efficiently.
- NVIDIA AVO (AI-driven kernel optimization) showed GQA kernels can exceed hand-tuned cuDNN by 3.5%.

**Compatibility**: 
- FlexAttention: native GQA support, auto-broadcasts KV heads to Q heads.
- SDPA: PyTorch's `scaled_dot_product_attention` added GQA support.
- SageAttention: works with GQA.
- No SM120-specific GQA kernel issues beyond general SM120 attention concerns.

**Evidence**:
- [PyTorch SDPA GQA announcement](https://dev-discuss.pytorch.org/t/added-grouped-query-attention-to-scaled-dot-product-attention-api/2340)
- [TensorRT-LLM GQA docs](https://nvidia.github.io/TensorRT-LLM/advanced/gpt-attention.html)

**Implementation complexity**: Low (already using GQA, just ensure attention backend leverages it properly)

**Verdict**: **Verify** -- Ensure our SDPA call passes `enable_gqa=True` (FlexAttention) or correctly handles the head dimension mismatch. The 4:1 GQA ratio is already a strong optimization; further GQA-specific tuning has diminishing returns.

---

## 11. Custom CUDA Flash Attention for SM120

**What**: Hand-written CUDA C++ Flash Attention kernel specifically targeting SM120 hardware characteristics (HMMA instructions, no TMEM, ~2TB/s bandwidth).

**Expected impact**:
- gau-nernst's implementation beats official FA2 kernel on RTX 5090.
- CuDNN backend still faster, suggesting more headroom exists.
- RTX 5090 at 400W: achieves near speed-of-light BF16 attention with proper tiling.
- Key optimizations: shared memory swizzling, N-stage pipelining, double buffering.

**Compatibility**: SM120 native.
- Source: [gau-nernst/learn-cuda](https://github.com/gau-nernst/learn-cuda/tree/e83c256/07_attention)
- Compiled with CUDA 12.9. Uses only Ampere-class features (no TMA, no tcgen05).
- Benchmark: bs=1, num_heads=8, len_query=4096, len_kv=8192, head_dim=128.

**Evidence**:
- [Blog: Writing Speed-of-Light Flash Attention for 5090](https://gau-nernst.github.io/fa-5090/)
- [Hacker News discussion](https://news.ycombinator.com/item?id=44995508)

**Implementation complexity**: Very High (custom CUDA kernel, ongoing maintenance, GQA adaptation)

**Verdict**: **Skip** -- Great reference material but writing/maintaining a custom CUDA attention kernel is not justified for our use case. FlexAttention via Triton provides 90%+ of the performance with near-zero maintenance burden. Only revisit if attention becomes a proven bottleneck after other optimizations.

---

## Priority Order (Recommended Implementation Sequence)

### Phase 1: Quick wins (days)
1. **Dynamic KV Cache** (#6) -- Switch from 4096 pre-allocation to chunked growth. Saves 450-530MB for typical generations. Zero quality risk.
2. **FlexAttention + GQA** (#2, #10) -- Switch from raw SDPA to `flex_attention` with `enable_gqa=True` + `torch.compile`. Free performance from Triton compilation on SM120.

### Phase 2: Validation required (1-2 weeks)
3. **KV Cache INT8 Quantization** (#4) -- Manual per-channel INT8 quantization of K/V on write, dequantize on read. Saves ~280MB. Must validate TTS quality.
4. **SageAttention** (#3) -- INT8 Q/K attention kernels. 2.7x speedup potential. Must validate TTS quality with `sageattn_qk_int8_pv_fp16_cuda` mode.

### Phase 3: Advanced (if needed)
5. **TurboQuant/aither-kvcache** (#5) -- 3-4 bit KV compression. Worth it if pushing batch size or sequence length.
6. **Sliding Window** (#7) -- Test with TTS quality gating. May not be suitable for speech prosody.

### Phase 4: Skip unless circumstances change
7. **PagedAttention** (#8) -- Overkill for single-stream TTS.
8. **Token Eviction** (#9) -- Sequence lengths too short to benefit.
9. **Custom CUDA Kernel** (#11) -- Maintenance burden not justified.

---

## Key SM120 Pitfalls to Avoid

1. **Do not install xformers** -- It silently downgrades PyTorch from nightly to stable, breaking SM120 support.
2. **Do not attempt FA3 or FA4** -- Hardware impossible on SM120 (no TMEM/tcgen05).
3. **Do not use torchao FP8 attention** -- Requires FA3 (SM90) or FA4 (SM100) backends.
4. **Do not use FlashMLA** -- Hopper-only (SM90).
5. **Verify CUDA arch flags** -- Always compile with `TORCH_CUDA_ARCH_LIST="12.0"` for SM120.
6. **Prefer Triton kernels** -- Triton compiles correctly for SM120; custom CUDA kernels may need SM120-specific adaptation.
7. **Test FP32 accumulation** -- RTX 5090 runs FP16/FP8 matmuls at half speed when accumulating in FP32 (NVIDIA gaming card limitation). BF16 with BF16 accumulation is full speed.

---

## Sources

- [FlashAttention SM120 issues](https://github.com/Dao-AILab/flash-attention/issues/1853)
- [FlashAttention-4 SM120 investigation](https://gist.github.com/solatticus/aab6ec3a0436748b021cbbdd12e8c739)
- [FA4 Blackwell SGLang discussion](https://github.com/sgl-project/sglang/discussions/10564)
- [FlashInfer SM120 wiring issues](https://github.com/flashinfer-ai/flashinfer/issues/2555)
- [PyTorch FlexAttention docs](https://docs.pytorch.org/docs/stable/nn.attention.flex_attention.html)
- [FlexAttention for Inference blog](https://pytorch.org/blog/flexattention-for-inference/)
- [Paged Attention + FlexAttention paper](https://arxiv.org/html/2506.07311v1)
- [PyTorch PagedAttention RFC #121465](https://github.com/pytorch/pytorch/issues/121465)
- [SageAttention GitHub](https://github.com/thu-ml/SageAttention)
- [SageAttention SM120 prebuilt wheels](https://github.com/mobcat40/sageattention-blackwell)
- [KVzip (NeurIPS 2025 Oral)](https://github.com/snu-mllab/KVzip)
- [aither-kvcache on PyPI](https://pypi.org/project/aither-kvcache/2.0.0/)
- [TurboQuant (ICLR 2026)](https://turbo-quant.com/)
- [GPU-Accelerated INT8 KV Cache paper](https://arxiv.org/html/2601.04719v1)
- [torchao quantization docs](https://docs.pytorch.org/ao/stable/workflows/inference.html)
- [StreamingLLM (ICLR 2024)](https://github.com/mit-han-lab/streaming-llm)
- [Flash Attention for 5090 in CUDA C++](https://gau-nernst.github.io/fa-5090/)
- [TensorRT-LLM GQA docs](https://nvidia.github.io/TensorRT-LLM/advanced/gpt-attention.html)
- [NVIDIA NVFP4 KV Cache blog](https://developer.nvidia.com/blog/optimizing-inference-for-long-context-and-large-batch-sizes-with-nvfp4-kv-cache/)
- [HuggingFace KV Cache strategies](https://huggingface.co/docs/transformers/en/kv_cache)
- [IBM FMS PagedAttention](https://github.com/thomasjoshi/foundation-model-stack)
