# Fish Speech S2-Pro Inference Optimization: Research Summary

**Project:** Fish Speech S2-Pro Inference Optimization on RTX 5090
**Domain:** TTS Inference Performance Engineering (PyTorch, CUDA, SM120 Blackwell)
**Researched:** 2026-04-12
**Confidence:** MEDIUM-HIGH

---

## Executive Summary

Fish Speech S2-Pro inference on RTX 5090 (SM120) currently runs at 0.263x RTF with 9.2GB VRAM using INT8 W8A16 quantization and torch.compile reduce-overhead mode. Research across PyTorch advances, KV cache/attention mechanisms, community findings, and SM120 hardware reveals a layered optimization landscape: several quick wins (config flags, compiler tuning) are available immediately, a substantial middle tier (attention backend migration, quantization exploration, DAC decoder compilation) requires validation work, and a high-ceiling long-term path (SGLang serving, speculative decoding, TensorRT export) could deliver transformative 2-5x improvements at significant engineering cost.

The most critical finding is that SM120 (consumer Blackwell) is **not** SM100 (datacenter Blackwell). SM120 lacks TMEM and tcgen05 instructions, which means FlashAttention-3, FlashAttention-4, FlashMLA, and torchao's FP8 attention are all hardware-impossible. Triton treats SM120 as SM80, so compiled kernels miss Blackwell-specific optimizations. This eliminates many "Blackwell optimization" techniques from consideration and makes Triton-compiled FlexAttention or community FA2 wheels the best available attention path. Furthermore, community reports reveal that torch.compile on SM120 may be silently degraded or hitting recompilation loops -- verifying compile health is the single most important first step.

The recommended strategy is: (1) verify and fix the torch.compile pipeline on SM120 first, (2) apply zero-risk config flags (weight freezing, coordinate descent tuning, cuBLAS autotune, env vars), (3) migrate attention to FlexAttention with GQA and validate SageAttention for INT8 speedups, (4) explore FP8 W8A8 quantization and DAC decoder optimization, (5) evaluate SGLang as a serving framework for production deployment. The PyTorch 2.8.0 version lock (2.10+ has 40-55% regression) constrains our optimization surface but does not block any Tier 1 or Tier 2 optimizations.

---

## Key Findings

### From PYTORCH_ADVANCES.md -- Compiler and Quantization

**Core recommendations:**
- **Weight freezing** (`TORCHINDUCTOR_FREEZING=1`): ~15% speedup, 1 line, zero risk for inference-only deployment. `freezing_discard_parameters=True` also frees VRAM.
- **Coordinate descent tuning**: 3-10% additional speedup from better Triton kernel configs. Increases first-compile time but cached afterward.
- **Int8DynamicActivationInt8WeightConfig**: 7-15% speedup over current W8A16 by enabling true INT8 GEMM compute. Drop-in replacement.
- **Float8DynamicActivationFloat8WeightConfig**: 10-20% speedup potential. SM120 has FP8 tensor cores but uses HMMA path (not TMEM). Quality validation needed.
- **CUDA graph bucketing**: Pre-capture graphs at discrete sequence lengths (128, 256, 512, 1024). Reduces padding waste 50-75%. Standard production practice.
- **PyTorch 2.10+ is off-limits**: Confirmed 40-55% throughput regression in `reduce-overhead` mode. GitHub issue #174575 open. Stay on 2.8.0.

**Deferred/rejected:**
- MXFP8: Requires torchao nightly (0.14+), SM120 kernel support unconfirmed. Prototype API.
- NVFP4: SM120 kernel bugs, quality risk for speech, prototype API.
- 2:4 structured sparsity: Requires retraining, SM120 kernel support unconfirmed.
- Multi-token prediction: 2-5x potential but requires training new prediction heads. Separate project.

### From KV_CACHE_ATTENTION.md -- Attention and Cache

**Core recommendations:**
- **FlexAttention (Triton backend)**: The recommended attention path for SM120. Native GQA support (`enable_gqa=True`), sliding window via `mask_mod`, compiled by Triton. Near-FA2 performance without external dependencies.
- **Dynamic KV cache allocation**: Current pre-allocation wastes 80-95% of KV cache VRAM for typical 200-800 token generations. Chunked allocation saves 450-530MB. Zero quality risk.
- **SageAttention 2**: INT8 Q/K quantized attention, 2.7x speedup over FA2 on RTX 5090. SM89 kernels work on SM120. Must validate TTS quality -- some models produce noisy output from INT8 overflow.
- **Manual INT8 KV cache quantization**: Per-channel INT8 on write, dequantize on read. Saves ~280MB. Simple implementation.

**Deferred/rejected:**
- FA3/FA4: Hardware impossible on SM120.
- FP8 KV cache with `apply_low_precision_attention`: Requires FA3 (SM90) or FA4 (SM100).
- PagedAttention: Overkill for single-stream TTS.
- Token eviction (H2O/ScissorHands): Sequence lengths too short to benefit.
- Custom CUDA flash attention: Maintenance burden not justified.

### From COMMUNITY_TRICKS.md -- Practical Findings

**Critical discoveries:**
- **torch.compile may be broken on SM120**: Fish Speech issues #966, #971 report compile making inference 15x slower (29s vs 2s). Triton `sm_120` arch errors. This must be verified immediately -- our 0.263x RTF may be degraded.
- **SGLang is Fish Audio's production stack**: RTF 0.195 on H200, 3000+ tok/s, 86.4% prefix-cache hit rate. The official recommended path, not torch.compile.
- **DAC decoder is separately optimizable**: Static shapes make it an ideal torch.compile or TensorRT target. May not be compiled currently. Profile to determine its fraction of total inference time.
- **W8A16 is correct for batch=1**: At batch=1, decode is memory-bandwidth bound. W8A16 halves weight traffic without activation quantization overhead. W8A8 only helps at batch >= 4-8.
- **Prefix caching (RadixAttention)**: Eliminates redundant reference-audio prefill. Huge win for voice reuse scenarios. Comes free with SGLang.
- **Streaming chunked audio emission**: 42ms first-token latency possible. Reduces perceived latency for interactive use.

**Confirmed not applicable:**
- fish-speech.rs: Only supports Fish Speech 1.5, not S2-Pro.
- Attention-free architectures: Can't change model architecture without retraining.

### From HARDWARE_SM120.md -- Hardware-Specific

**Core recommendations:**
- **cuBLAS GEMM autotune**: CUDA 13.0 `CUBLAS_GEMM_AUTOTUNE` benchmarks algorithms per-handle. 5-15% GEMM speedup. Easy to enable.
- **cuDNN 9 SDPA optimizations**: cuDNN 9.13+ has Blackwell attention improvements. Verify our SDPA routes through cuDNN backend.
- **Environment variables**: `CUDA_MODULE_LOADING=LAZY`, `CUBLAS_WORKSPACE_CONFIG`, `CUDA_FORCE_PTX_JIT=1` -- low-risk tuning knobs.
- **GDDR7 bandwidth profiling**: 1.79 TB/s theoretical. Profile with Nsight Compute to find if we're saturating bandwidth or leaving performance on the table.
- **compute_120f not compute_120a**: When building CUDA extensions for SM120, the `f` suffix is critical. `a` suffix causes GEMM crashes.

**Key constraint:**
- Triton on SM120 compiles as SM80 (Ampere), disabling all Blackwell-specific optimizations. We cannot fix this without upgrading PyTorch (blocked by 2.10+ regression). TensorRT-RTX is the escape hatch that bypasses this limitation entirely.

---

## Prioritized Technique List

### Tier 1: Quick Wins (< 1 hour, low risk)

| # | Technique | Source | Expected Impact | Notes |
|---|-----------|--------|----------------|-------|
| 1 | Verify torch.compile health on SM120 | COMMUNITY | **Diagnostic (potentially huge)** | Check for recompilation loops, Triton sm_120 errors. Our RTF may be degraded. |
| 2 | `TORCHINDUCTOR_FREEZING=1` + `freezing_discard_parameters=True` | PYTORCH | ~15% speedup + VRAM savings | One env var + one config line. Inference-only, no downside. |
| 3 | Coordinate descent tuning | PYTORCH | 3-10% speedup | 2 config lines. Longer first compile, cached after. |
| 4 | `cudagraph_support_input_mutation=True` | PYTORCH | Stability improvement | Prevents bad graph captures from in-place ops. |
| 5 | `torch.inference_mode()` instead of `torch.no_grad()` | COMMUNITY | Minor VRAM savings | More aggressive than no_grad. 1-line change. |
| 6 | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` | COMMUNITY | Reduced fragmentation | Env var. Prevents OOM on long-running server. |
| 7 | `CUDA_MODULE_LOADING=LAZY` | HARDWARE | Faster startup | Env var. |
| 8 | cuBLAS GEMM autotune | HARDWARE | 5-15% GEMM speedup | CUDA 13.0 feature. Easy to enable. |
| 9 | Verify cuDNN version and SDPA backend routing | HARDWARE | 5-15% attention speedup | Check `torch.backends.cudnn.version()`. |

### Tier 2: Medium Effort, High Potential (1-4 hours)

| # | Technique | Source | Expected Impact | Notes |
|---|-----------|--------|----------------|-------|
| 10 | Migrate attention to FlexAttention with GQA | KV_CACHE | Near-FA2 performance | Native SM120 path. `enable_gqa=True`. Compiled by Triton. |
| 11 | Dynamic KV cache allocation (chunked) | KV_CACHE | **Save 450-530MB VRAM** | Replace 4096 pre-alloc with chunked growth. Zero quality risk. |
| 12 | Compile DAC decoder separately with max-autotune | COMMUNITY | Unknown until profiled | Static shapes = ideal compile target. Profile DAC % of total time first. |
| 13 | `Int8DynamicActivationInt8WeightConfig` | PYTORCH | 7-15% speedup | Drop-in replacement for current W8A16. Needs quality validation. |
| 14 | CUDA graph sequence length bucketing | PYTORCH | 20-40% less padding waste | Pre-capture at 4-6 discrete lengths. Standard practice. |
| 15 | Bandwidth profiling with Nsight Compute | HARDWARE | Diagnostic | Measure achieved vs theoretical 1.79 TB/s. Find bottlenecks. |

### Tier 3: Significant Effort, Transformative Potential (4+ hours)

| # | Technique | Source | Expected Impact | Notes |
|---|-----------|--------|----------------|-------|
| 16 | SGLang integration | COMMUNITY | **RTF ~0.195 (25% improvement)** | Fish Audio's production stack. Continuous batching, prefix caching, CUDA graph replay. |
| 17 | SageAttention 2 (INT8 Q/K attention) | KV_CACHE | **2.7x attention speedup** | SM89 kernels on SM120. Must validate TTS quality. Overflow risk. |
| 18 | `Float8DynamicActivationFloat8WeightConfig` | PYTORCH | 10-20% speedup | FP8 tensor cores on SM120. Quality validation required. |
| 19 | Manual INT8 KV cache quantization | KV_CACHE | Save ~280MB VRAM | Per-channel INT8. Quality validation needed for TTS attention. |
| 20 | Streaming chunked audio emission | COMMUNITY | **42ms first-token latency** | Overlap token generation with DAC decoding. Perceived latency improvement. |
| 21 | TensorRT-RTX export (POC) | HARDWARE | **30-60% speedup** | Bypasses Triton SM120 limitations. High engineering effort. Start with transformer backbone only. |
| 22 | Multi-token prediction / speculative decoding | PYTORCH, COMMUNITY | **2-5x Slow AR speedup** | Requires training additional prediction heads. Separate project phase. |

### Skip: Confirmed Incompatible or Already Rejected

| Technique | Source | Reason |
|-----------|--------|--------|
| FlashAttention-3 | KV_CACHE, HARDWARE | SM90 (Hopper) only. Hardware impossible. |
| FlashAttention-4 | PYTORCH, KV_CACHE, HARDWARE | SM100 only. No TMEM on SM120. Hardware impossible. |
| FlashMLA | KV_CACHE | Hopper-only. |
| torchao FP8 attention (`apply_low_precision_attention`) | PYTORCH | Requires FA3 (SM90) or FA4 (SM100). |
| NVFP4 quantization | PYTORCH, HARDWARE | SM120 kernel bugs, quality risk for speech, prototype API. |
| MXFP8 microscaling | PYTORCH | Requires torchao nightly (0.14+), SM120 kernel support unconfirmed. |
| 2:4 structured sparsity | PYTORCH | Requires retraining, SM120 kernel support unconfirmed. |
| PyTorch 2.10+ upgrade | PYTORCH | 40-55% reduce-overhead regression. Blocked. |
| PagedAttention | KV_CACHE | Overkill for single-stream TTS. |
| Token eviction (H2O/KVzip) | KV_CACHE | Sequence lengths too short to benefit. |
| Custom CUDA flash attention | KV_CACHE | Maintenance burden not justified. |
| fish-speech.rs | COMMUNITY | Only supports Fish Speech 1.5, not S2-Pro. |
| cuTile / CUDA 13.1 tile programming | HARDWARE | Too new, no ecosystem. |
| Attention-free architectures | COMMUNITY | Can't change model without retraining. |

---

## Critical Risks and Blockers

### 1. torch.compile May Be Silently Degraded (CRITICAL)

**Sources:** COMMUNITY_TRICKS.md #9/#16, HARDWARE_SM120.md #7

Fish Speech issues #966 and #971 document torch.compile making inference **15x slower** on Blackwell GPUs due to Triton `sm_120` arch errors and recompilation loops. Our 0.263x RTF may already be running in a degraded state. Triton compiles SM120 kernels as SM80, missing Blackwell optimizations. This must be verified before any other optimization work -- if compile is broken, fixing it alone could be the largest win.

**Mitigation:** Check compile logs for graph breaks, recompilation warnings, and Triton errors. Run with `TORCH_LOGS="dynamo,inductor"` to diagnose.

### 2. PyTorch 2.8.0 Version Lock

**Sources:** PYTORCH_ADVANCES.md #8, HARDWARE_SM120.md #7

PyTorch 2.10+ has a confirmed 40-55% regression in `reduce-overhead` mode (GitHub #174575). This locks us out of better Triton SM120 support, native FP8 torch ops, MXFP8, NVFP4, and newer torchao features. The version lock is the correct decision but constrains our optimization surface.

**Mitigation:** Monitor GitHub #174575 for a fix. TensorRT-RTX bypasses this limitation entirely for production deployment.

### 3. SM120 Kernel Ecosystem Immaturity

**Sources:** All four research files

FlashAttention, FlashInfer, CUTLASS grouped GEMM, and Triton all have incomplete SM120 support. Many kernels either don't compile, produce wrong results, or fall back to SM80 codegen. This is an ecosystem-wide problem that will improve over time but currently limits what's achievable.

**Mitigation:** Prefer PyTorch-native APIs (FlexAttention, SDPA, torchao) over external kernel libraries. These have the best SM120 support path.

### 4. TTS Quality Sensitivity

**Sources:** PYTORCH_ADVANCES.md (quantization sections), KV_CACHE_ATTENTION.md #3/#4

Speech synthesis is more quality-sensitive than text LLMs. INT8 Q/K attention (SageAttention) can produce noisy output in some models. FP8 weight quantization has less dynamic range than INT8. Every quantization change needs perceptual quality validation (UTMOS, WER, MOS listening test).

**Mitigation:** Always benchmark quality before committing to a quantization change. Maintain A/B comparison infrastructure.

### 5. W8A16 is Correct for Batch=1 (Validates Current Approach)

**Sources:** COMMUNITY_TRICKS.md #12, PYTORCH_ADVANCES.md #1a

At batch=1, autoregressive decode is memory-bandwidth bound. W8A16 already halves weight bandwidth. W8A8 adds activation quantization overhead with no compute benefit at batch=1. The crossover to compute-bound is batch >= 4-8. Our current INT8 W8A16 is the right choice for single-user inference.

---

## Recommended Execution Order

### Phase 1: Diagnostics and Zero-Risk Config (Day 1)

**Rationale:** Must verify baseline is healthy before optimizing. Config flags are free performance.

**Actions:**
1. Verify torch.compile is working correctly on SM120 (check for recompilation, Triton errors)
2. Profile DAC decoder vs transformer time split
3. Profile memory bandwidth utilization with Nsight Compute
4. Set `TORCHINDUCTOR_FREEZING=1` + `freezing_discard_parameters=True`
5. Enable `coordinate_descent_tuning` + `coordinate_descent_check_all_directions`
6. Set `cudagraph_support_input_mutation=True`
7. Test env vars: `CUDA_MODULE_LOADING=LAZY`, `expandable_segments:True`
8. Enable cuBLAS GEMM autotune
9. Verify cuDNN version and SDPA backend routing
10. Switch to `torch.inference_mode()` if not already using it

**Expected outcome:** 15-30% speedup from config flags alone, plus diagnostic data to guide Phase 2.

**Pitfalls to avoid:** Do not upgrade PyTorch. Do not install xformers (silently downgrades PyTorch).

### Phase 2: Attention and Memory (Days 2-4)

**Rationale:** Attention backend and KV cache are the two areas where SM120-compatible improvements exist with well-understood tradeoffs.

**Actions:**
1. Migrate attention to FlexAttention with `enable_gqa=True` + `torch.compile`
2. Implement dynamic KV cache allocation (chunked, start at 512, grow in 256-token blocks)
3. Compile DAC decoder separately with `max-autotune` mode
4. Benchmark `Int8DynamicActivationInt8WeightConfig` vs current W8A16 (with quality eval)
5. Implement CUDA graph sequence length bucketing (4-6 buckets based on actual distribution)

**Expected outcome:** Additional 10-30% speedup, 450-530MB VRAM savings from dynamic KV cache.

**Pitfalls to avoid:** Do not attempt FA3/FA4. Do not use torchao FP8 attention. Validate quality for any quantization change.

### Phase 3: Advanced Quantization and Attention (Week 2)

**Rationale:** These techniques have higher ceilings but require quality validation and more engineering.

**Actions:**
1. Validate SageAttention 2 (`sageattn_qk_int8_pv_fp16_cuda` mode) on Fish Speech
2. Benchmark `Float8DynamicActivationFloat8WeightConfig` on SM120
3. Implement manual INT8 KV cache quantization if VRAM savings matter
4. Test mixed-precision per-module quantization (FP8 for FFN, INT8 for attention)
5. Profile individual layer shapes to identify best quantization per layer

**Expected outcome:** Best quantization config identified. SageAttention validated or rejected. Potential 10-25% additional speedup.

**Research flags:** SageAttention quality on TTS is unknown. FP8 on SM120 uses HMMA path, performance may differ from benchmarks.

### Phase 4: Serving Infrastructure (Weeks 2-4)

**Rationale:** SGLang is Fish Audio's own production stack. This is the highest-impact single change but requires significant integration work.

**Actions:**
1. Set up SGLang serving for Fish Speech S2-Pro
2. Enable RadixAttention prefix caching for voice reuse
3. Implement streaming chunked audio emission for low first-audio latency
4. Benchmark SGLang vs optimized torch.compile path from Phases 1-3

**Expected outcome:** Production-grade serving with RTF approaching 0.195x. Prefix caching eliminates redundant computation for reused voices.

**Research flags:** SGLang integration with DualAR architecture needs investigation. Single-user latency improvement may be smaller than throughput improvement.

### Phase 5: Long-Term Explorations (Month+)

**Rationale:** These have the highest ceilings (2-5x) but require training investment or major engineering.

**Actions:**
1. POC TensorRT-RTX export of transformer backbone (bypasses Triton SM120 limitations)
2. Prototype 2-head multi-token prediction for Slow AR (requires training)
3. Benchmark s2.cpp Q8 on RTX 5090 as alternative inference stack
4. Monitor PyTorch 2.10+ regression fix for potential upgrade path
5. Revisit NVFP4 when SM120 kernel support stabilizes

**Expected outcome:** Determine if TensorRT or speculative decoding justify full investment.

---

## Cross-References and Conflicts

### Agreements Across Research

1. **SM120 is not SM100**: All four documents emphasize this. PYTORCH, KV_CACHE, and HARDWARE all independently confirm FA3/FA4/FlashMLA are impossible.
2. **FlexAttention is the best attention path**: PYTORCH (6c) and KV_CACHE (2) both recommend FlexAttention over external FA2 or custom kernels for SM120.
3. **Weight freezing is the easiest win**: PYTORCH (2b) rates it #1 priority. No other document contradicts.
4. **W8A16 is correct for batch=1**: COMMUNITY (12) and PYTORCH (1a) agree. Only switch to W8A8/FP8 if batching.
5. **Dynamic KV cache is pure upside**: KV_CACHE (6) and COMMUNITY (2) both identify the pre-allocation waste. COMMUNITY's StaticCache recommendation seems to conflict but actually addresses a different concern (CUDA graph compatibility, not VRAM waste).

### Conflicts and Tensions

1. **Static vs Dynamic KV cache**: COMMUNITY (2) recommends StaticCache for CUDA graph compatibility. KV_CACHE (6) recommends dynamic allocation for VRAM savings. **Resolution:** Use a "static-but-right-sized" cache -- pre-allocate at a reasonable expected max (e.g., 1024) rather than the full 4096, with fallback growth. This gets CUDA graph benefits AND reduces waste.

2. **max-autotune vs reduce-overhead**: COMMUNITY (3) suggests trying max-autotune. PYTORCH (2c) says investigate carefully. HARDWARE notes that with Triton treating SM120 as SM80, the autotuning search space may be limited. **Resolution:** Quick A/B test. If < 5% difference, stick with reduce-overhead for its automatic CUDA graph management.

3. **FP8 W8A8 vs INT8 W8A16**: HARDWARE (1) suggests FP8 could give 10-25% speedup. COMMUNITY (12) says W8A16 is correct for batch=1. **Resolution:** Profile whether decode is truly memory-bound or partially compute-bound on the 5090's 1.79 TB/s bandwidth. The high bandwidth may shift the crossover point, making FP8 W8A8 beneficial even at batch=1.

4. **SGLang vs torch.compile optimization**: COMMUNITY strongly recommends SGLang migration. PYTORCH optimizations target the torch.compile path. **Resolution:** Not mutually exclusive. Optimize the torch.compile path first (Phases 1-3) since those learnings transfer. SGLang evaluation (Phase 4) may supersede the torch.compile path for production, but the torch.compile path remains valuable for development/testing.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| PyTorch Compiler/Quantization | **HIGH** | Official PyTorch docs, torchao source code, confirmed APIs in our version |
| KV Cache & Attention | **HIGH** | Well-documented patterns, multiple independent sources, clear SM120 constraints |
| Community Tricks | **MEDIUM-HIGH** | Fish Speech GitHub issues are primary sources; SGLang recommendation from official technical report |
| SM120 Hardware | **MEDIUM** | Hardware specs confirmed, but kernel ecosystem maturity is a moving target. cuBLAS/cuDNN findings based on release notes, not our-model benchmarks |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

1. **torch.compile health on SM120**: Unknown whether our current setup is hitting recompilation or Triton errors. Must verify before trusting baseline numbers.
2. **DAC decoder time fraction**: Unknown what percentage of total inference time is DAC vs transformer. This determines whether DAC optimization matters.
3. **SageAttention quality on TTS**: No existing data on INT8 Q/K attention for speech codec token prediction. Must validate empirically.
4. **FP8 quality on Fish Speech**: No published FP8 benchmarks for this model. Need calibration and quality testing.
5. **SM120 FP8 GEMM throughput**: Benchmarked on SM100 (B200) and SM90 (H100), not SM120. Real throughput on our hardware is unknown.
6. **SGLang + DualAR integration path**: Unclear how much adaptation is needed to serve Fish Speech S2-Pro through SGLang.
7. **Effective bandwidth utilization**: Don't know what fraction of the 1.79 TB/s we're actually using. Profiling needed.

---

## Aggregated Sources

### Primary (HIGH confidence -- official docs, confirmed working)
- [torchao Quantized Inference Docs](https://docs.pytorch.org/ao/stable/workflows/inference.html)
- [PyTorch torch.compile Documentation](https://docs.pytorch.org/docs/stable/generated/torch.compile.html)
- [PyTorch FlexAttention Docs](https://docs.pytorch.org/docs/stable/nn.attention.flex_attention.html)
- [PyTorch Inductor Config Source](https://github.com/pytorch/pytorch/blob/main/torch/_inductor/config.py)
- [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v2)
- [NVIDIA RTX Blackwell GPU Architecture Whitepaper](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf)
- [cuDNN 9.13 Release Notes](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.13.0/release-notes.html)
- [CUDA 13.0 Release Blog](https://developer.nvidia.com/blog/whats-new-and-important-in-cuda-toolkit-13-0/)
- [Blackwell Tuning Guide](https://docs.nvidia.com/cuda/blackwell-tuning-guide/index.html)

### Secondary (MEDIUM confidence -- peer-reviewed papers, reputable community sources)
- [FlashAttention-4 SM120 Investigation (solatticus gist)](https://gist.github.com/solatticus/aab6ec3a0436748b021cbbdd12e8c739)
- [SageAttention GitHub (ICLR/ICML/NeurIPS)](https://github.com/thu-ml/SageAttention)
- [TurboQuant (ICLR 2026)](https://turbo-quant.com/)
- [Accelerating Codec-based Speech Synthesis (arXiv:2410.13839)](https://arxiv.org/abs/2410.13839)
- [VADUSA: Speculative Decoding for TTS (arXiv:2410.21951)](https://arxiv.org/abs/2410.21951v2)
- [PyGraph (arXiv:2503.19779)](https://arxiv.org/abs/2503.19779)
- [GPU-Accelerated INT8 KV Cache (arXiv:2601.04719)](https://arxiv.org/html/2601.04719v1)
- [PyTorch reduce-overhead Regression Issue #174575](https://github.com/pytorch/pytorch/issues/174575)

### Tertiary (LOW confidence -- community reports, needs validation on our setup)
- [Fish Speech Issue #971: --compile slows inference](https://github.com/fishaudio/fish-speech/issues/971)
- [Fish Speech Issue #966: SM120 Triton error](https://github.com/fishaudio/fish-speech/issues/966)
- [SageAttention SM120 prebuilt wheels](https://github.com/mobcat40/sageattention-blackwell)
- [s2-pro GGUF on HuggingFace](https://huggingface.co/mach9243/s2-pro-gguf)
- [cuBLAS 13.2: 20% speedup on RTX PRO 6000](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)

---

*Research completed: 2026-04-12*
*Ready for roadmap: yes*
