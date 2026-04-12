# SM120/Blackwell Hardware Optimization Research

> Research date: 2026-04-12
> Target: Fish Speech S2-Pro on RTX 5090 (SM120, 32GB GDDR7)
> Current stack: PyTorch 2.8.0+cu128, CUDA 13.0, INT8 W8A16, torch.compile reduce-overhead, BF16+TF32
> Current perf: 9.2GB VRAM, 0.263x RTF

## Critical Context: SM120 vs SM100

The single most important finding: **SM120 (consumer Blackwell / RTX 50-series) is architecturally distinct from SM100 (datacenter Blackwell / B200)**. They share the "Blackwell" brand but differ at the silicon level:

- SM100 has Tensor Memory (TMEM) and tcgen05 instructions -- SM120 does NOT
- SM100 uses WGMMA-successor instructions -- SM120 uses HMMA (Volta/Ampere-era MMA approach)
- SM120 has 128KB shared memory per SM (vs 228KB on SM100)
- SM120 supports max 48 concurrent warps per SM (vs 64 on SM100)
- Many Blackwell-optimized kernels (FA4, FlashMLA, tcgen05-based CUTLASS) are SM100-only

This means many "Blackwell optimization" blog posts and announcements do NOT apply to the RTX 5090.

Sources:
- [FlashAttention-4 Cannot Run on RTX 5090 (SM120)](https://gist.github.com/solatticus/aab6ec3a0436748b021cbbdd12e8c739)
- [Blackwell Wikipedia](https://en.wikipedia.org/wiki/Blackwell_(microarchitecture))
- [CUDA Toolkit 12.8 SM120 Forum Thread](https://forums.developer.nvidia.com/t/cuda-toolkit-12-8-what-gpu-is-sm-120/322128)

---

## 1. FP8 Quantization (W8A8 or W8A16)

**What**: SM120 has 5th-gen Tensor Cores with native FP8 (E4M3/E5M2) hardware support. FP8 GEMM is confirmed working on SM120 via m16n8k32 MMA tiles. cuBLAS 13.2 delivers up to 20% speedup for FP8 on RTX PRO 6000 (SM120). Our current INT8 W8A16 could potentially be upgraded to FP8 W8A8 for better throughput since FP8 uses tensor cores more efficiently than INT8 for mixed-precision workloads.

**Expected impact**: 10-25% inference speedup over INT8 W8A16, possible slight VRAM reduction with W8A8 (activations also 8-bit). FP8 has double the throughput of FP16 on Blackwell tensor cores.

**Requirements**: CUDA 13.0+ (we have this), cuBLAS 13.0+, PyTorch FP8 support. NVIDIA Model Optimizer or manual Q/DQ insertion for ONNX export path.

**Compatibility**: PyTorch 2.8.0 has partial FP8 support. torch.float8_e4m3fn dtype exists. However, full FP8 GEMM dispatch through torch.compile may require newer PyTorch. Can be used via direct cuBLAS calls or CUTLASS.

**Evidence**:
- [cuBLAS 13.2: 20% speedup for FP8/INT8 on RTX PRO 6000](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)
- [Blackwell Microbenchmarks: FP8 MMA confirmed on SM120](https://forums.developer.nvidia.com/t/how-to-load-fp8-using-ldmatrix-on-sm120-sm120a/330254)
- [NVIDIA RTX Blackwell GPU Architecture Whitepaper](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf)

**Risk**: Medium. FP8 quantization for TTS models (especially the VQ codebook decoder) needs careful calibration. FP8's reduced dynamic range vs INT8 could affect audio quality. The SM120 FP8 ISA path differs from SM100, so some library kernels may not be optimized yet.

**Verdict**: **Investigate further** -- Profile INT8 vs FP8 GEMM throughput on our specific model shapes. If Fish Speech's linear layers are GEMM-bound (likely for the transformer backbone), FP8 could help. Test audio quality with FP8 calibration.

---

## 2. NVFP4 Quantization (W4A8 or W4A16)

**What**: Blackwell's headline feature: native FP4 (NVFP4) tensor core operations. Uses two-level microscaling: FP8 (E4M3) scale per 16-value block + FP32 tensor-level scale. Delivers 2x throughput of FP8 and 3.5x memory reduction vs FP16. The RTX 5090 has hardware support, and NVIDIA + Black Forest Labs demonstrated FP4 on FLUX image generation on RTX 50-series.

**Expected impact**: Potentially 1.5-2x speedup over INT8, ~50% VRAM reduction (weights from 8-bit to 4-bit). Effective bandwidth: 4.5 bits per value (4-bit value + amortized scaling overhead).

**Requirements**: CUDA 13.0+ with `compute_120f` target, CUTLASS 4.4+, TensorRT-RTX, or cuBLAS with NVFP4 support. Requires careful PTQ calibration with representative audio data.

**Compatibility**: NOT directly usable through PyTorch 2.8.0 torch.compile. Requires either TensorRT-RTX export or custom CUTLASS kernels. PyTorch native NVFP4 support is not yet in stable releases.

**Evidence**:
- [NVIDIA Blog: Introducing NVFP4](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)
- [TensorRT Unlocks FP4 for RTX 50 Series](https://developer.nvidia.com/blog/nvidia-tensorrt-unlocks-fp4-image-generation-for-nvidia-blackwell-geforce-rtx-50-series-gpus/)
- [NVFP4 on FLUX.2 for Blackwell](https://developer.nvidia.com/blog/scaling-nvfp4-inference-for-flux-2-on-nvidia-blackwell-data-center-gpus/)
- MLPerf v5.0: B200 FP4 achieved ~2.8x better than H200 FP8

**Risk**: High. (1) NVFP4 software support on SM120 is still buggy -- CUTLASS grouped GEMM produces garbage on SM120 (requires compute_120f fix, CUDA 13.0+). (2) TTS audio quality degradation at 4-bit is unknown for Fish Speech. (3) Dynamic FP4 quantization (without PTQ calibration) has larger accuracy gaps. (4) FP4 quantization errors can compound in autoregressive decoding.

**Verdict**: **Skip for now** -- Too many software maturity issues on SM120 specifically. Revisit when CUTLASS 4.5+ and PyTorch have stable SM120 FP4 paths. The TensorRT-RTX export path (see section 5) may be the first viable route.

---

## 3. cuBLAS GEMM Autotune

**What**: CUDA 13.0 introduced `CUBLAS_GEMM_AUTOTUNE` as a valid algo parameter for `cublasGemmEx`, `cublasGemmBatchedEx`, and `cublasGemmStridedBatchedEx`. When used, cuBLAS benchmarks available algorithms internally and caches the optimal one within the current handle. This is separate from torch.compile's autotuning.

**Expected impact**: 5-15% GEMM speedup for our specific matrix shapes. The autotuner can find SM120-specific optimal tile sizes and pipeline depths that the default heuristic might miss.

**Requirements**: CUDA 13.0+ (we have this). Can be enabled via environment variable `CUBLAS_WORKSPACE_CONFIG` or programmatically.

**Compatibility**: Works with PyTorch 2.8.0 -- cuBLAS is called under the hood. Can also use `torch.backends.cuda.matmul.allow_tf32 = True` (already enabled) and explore `torch.backends.cudnn.benchmark = True`.

**Evidence**:
- [CUDA 13.0 Blog: cuBLAS autotune](https://developer.nvidia.com/blog/whats-new-and-important-in-cuda-toolkit-13-0/)
- [nvMatmulHeuristics achieves 104% of baseline for Blackwell](https://developer.nvidia.com/blog/improving-gemm-kernel-auto-tuning-efficiency-on-nvidia-gpus-with-heuristics-and-cutlass-4-2/)
- [cuBLAS 13.2: 20% speedup on RTX PRO 6000](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)

**Risk**: Low. Autotuning adds warmup time (first call is slower) but subsequent calls use cached results. No accuracy impact.

**Verdict**: **Try** -- Easy to enable, no downside. Set `CUBLAS_WORKSPACE_CONFIG` and test if PyTorch picks up the autotune flag. Also ensure we're on cuBLAS 13.2 for the SM120-specific 20% improvements.

---

## 4. cuDNN 9 Attention Optimizations

**What**: cuDNN 9.13+ has significant Blackwell attention optimizations: FP8 scaled dot-product attention (SDPA) forwards on Blackwell, ~5% SDPA improvement from skipping softmax correction, paged attention with FP8 inputs. Also block-scale matmul with flexible 1D/2D block sizes.

**Expected impact**: 5-15% attention speedup if we route through cuDNN SDPA instead of custom/PyTorch native attention.

**Requirements**: cuDNN 9.13+, CUDA 13.0+. Need to ensure PyTorch uses cuDNN SDPA backend.

**Compatibility**: PyTorch 2.8.0 should support cuDNN SDPA backend via `torch.nn.functional.scaled_dot_product_attention`. Check `torch.backends.cudnn.version()`.

**Evidence**:
- [cuDNN 9.13 Release Notes: Blackwell SDPA](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.13.0/release-notes.html)
- Known issue: "Runtime compilation of LayerNorm and RMSNorm execution plans might be protracted on compute capability 12.0 devices" -- this affects us

**Risk**: Low-Medium. The LayerNorm/RMSNorm compilation slowdown on SM120 (cc 12.0) is a known issue that could cause long first-inference latency. Need to test warm-up behavior.

**Verdict**: **Try** -- Verify cuDNN version, ensure SDPA is routing through cuDNN backend. Profile attention specifically to see if we get gains. Watch for the LayerNorm compilation issue.

---

## 5. TensorRT-RTX Export (ONNX Path)

**What**: TensorRT-RTX is a compact (<200MB) inference library for RTX GPUs supporting Turing through Blackwell. Supports ONNX import with FP8/INT8/FP4 quantization via Q/DQ nodes. Two-phase compilation (AOT + JIT) completes in under 30 seconds. NVIDIA has a documented TTS deployment workflow (Tacotron 2 + WaveGlow) that splits autoregressive models into Encoder/Decoder/Postnet components.

For Fish Speech specifically: the model could be split into (1) text encoder, (2) autoregressive VQ token predictor, (3) vocoder/decoder. Each component exported to ONNX separately, with the autoregressive loop managed in Python.

**Expected impact**: 30-60% potential speedup over PyTorch eager/compile. TensorRT excels at operator fusion, memory planning, and kernel selection. FP8 mixed-precision through TensorRT is more mature than through PyTorch on SM120.

**Requirements**: TensorRT-RTX (latest), ONNX export of Fish Speech components, NVIDIA Model Optimizer for quantization. Significant engineering effort to split and export the model.

**Compatibility**: Independent of PyTorch version for inference. Can coexist -- use PyTorch for development, TensorRT for production inference.

**Evidence**:
- [NVIDIA Blog: Deploy Real-Time TTS with TensorRT](https://developer.nvidia.com/blog/how-to-deploy-real-time-text-to-speech-applications-on-gpus-using-tensorrt/)
- [TensorRT-RTX Documentation](https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/index.html)
- [Transformer Engine ONNX Export Guide](https://docs.nvidia.com/deeplearning/transformer-engine/user-guide/examples/onnx/onnx_export.html)
- TensorRT-RTX supports INT4, INT8, FP4, FP8 on Blackwell

**Risk**: High engineering effort. (1) Fish Speech's architecture may have custom ops that don't map cleanly to ONNX. (2) The autoregressive loop adds complexity -- each decoder step is a separate TensorRT inference call. (3) Dynamic shapes (variable-length text/audio) need careful handling. (4) Known issue: "Support for B100 and B200 on Windows is considered experimental. Some networks may fail to run." -- need to verify SM120 support status.

**Verdict**: **Investigate further** -- This is the highest-potential optimization path but requires significant effort. Start with a POC: export just the transformer backbone to ONNX, benchmark TensorRT vs torch.compile on that component alone. If 30%+ faster, invest in full pipeline export.

---

## 6. FlashAttention Status on SM120

**What**: Current FlashAttention support on SM120:
- **FA4**: NOT supported. Requires SM100 TMEM/tcgen05 hardware that is physically absent on SM120.
- **FA3**: NOT supported. Hopper SM90-only (WGMMA instructions).
- **FA2**: NOT officially supported. Runtime check rejects SM120 ("FlashAttention only supports Ampere GPUs or newer" -- whitelist doesn't include SM120). Community-compiled wheels exist. FA2 via Triton works.

**Expected impact**: If we could use FA2 via Triton: 10-30% attention speedup with memory-efficient attention (no O(n^2) memory).

**Requirements**: Community FA2 wheels or Triton-based FA2. Set `TORCH_CUDA_ARCH_LIST="12.0"` for compilation.

**Compatibility**: Community wheels exist for PyTorch 2.8+. Triton-based FA2 works if Triton compiles for SM120 (see Triton section below).

**Evidence**:
- [FA SM120 Issue #1665](https://github.com/Dao-AILab/flash-attention/issues/1665)
- [FA4 Cannot Run on RTX 5090 Investigation](https://gist.github.com/solatticus/aab6ec3a0436748b021cbbdd12e8c739)
- [Community RTX 50 FA2 Wheels](https://github.com/Dao-AILab/flash-attention/issues/1683)
- FA2 via Triton is confirmed as the best available attention kernel for RTX 5090

**Risk**: Medium. Community wheels may have bugs. Triton on SM120 compiles kernels as SM80 (Ampere), disabling Blackwell-specific optimizations. Audio quality should be unaffected (FlashAttention is mathematically equivalent to standard attention).

**Verdict**: **Try** -- If we're not already using memory-efficient attention, FA2 via Triton or community wheels could help. Even with SM80-level Triton compilation, the algorithmic advantage of FlashAttention (O(n) memory, better cache utilization) applies.

---

## 7. Triton / torch.compile on SM120

**What**: TorchInductor's Triton backend has known issues on SM120:
- Triton treats SM120 as SM80 (Ampere), disabling all Blackwell optimizations
- `ptxas fatal: Value 'sm_120' is not defined for option 'gpu-name'` errors in some configurations
- Nightly PyTorch builds have better SM120 support but stable releases lag behind
- An NVIDIA engineer (ptrblck) confirmed the GPU itself works -- errors come from third-party library arch checks

For our setup (PyTorch 2.8.0 with torch.compile reduce-overhead): this likely means our compiled kernels are using SM80-level Triton codegen, missing SM120-specific features like larger register files, new memory hierarchy, and 5th-gen tensor core instructions.

**Expected impact**: Unknown but potentially significant. If Triton properly targeted SM120, we might see 10-20% improvement from better instruction scheduling and memory access patterns. Currently we're leaving performance on the table.

**Requirements**: For proper SM120 Triton support: likely PyTorch 2.10+ nightly (but this conflicts with our reduce-overhead regression). Alternative: write custom Triton kernels that manually specify SM120 features.

**Compatibility**: We CANNOT upgrade past PyTorch 2.8.0 due to the 40-55% reduce-overhead regression. This means we're stuck with Triton treating SM120 as SM80.

**Evidence**:
- [PyTorch Issue #159207: SM120 support](https://github.com/pytorch/pytorch/issues/159207)
- [Triton Issue #9181: Blackwell failure](https://github.com/triton-lang/triton/issues/9181)
- [PyTorch Issue #164342: Stable SM120 support](https://github.com/pytorch/pytorch/issues/164342)
- [PyTorch Forums: SM120 support thread](https://discuss.pytorch.org/t/pytorch-support-for-sm120/216099)

**Risk**: Low (current state is already degraded). Custom Triton kernels require significant kernel development expertise.

**Verdict**: **Skip for now** -- We can't upgrade PyTorch, and the Triton SM120 support gap is a known ecosystem issue. Monitor PyTorch 2.8.x patch releases for backported SM120 improvements. The TensorRT path (section 5) bypasses this issue entirely.

---

## 8. CUTLASS 4.x SM120 Kernels

**What**: CUTLASS has been actively adding SM120 support:
- **CUTLASS 3.9.0** (April 2025): First SM120 support in 3.x API -- block-scaled datatypes, dense GEMM, sparse ops
- **CUTLASS 4.x** (2025-2026): SM120 block-scaled sparse kernels, MoE grouped GEMM API
- **CUTLASS 4.4.2** (March 2026): Enabled SM120f compilation, exposed NVFP4/MX Grouped GEMM in profiler

SM120 GEMMs support both pingpong and cooperative kernel schedules. New narrow precision (FP4/FP6) block-scaled tensor cores are 1x-4x faster than Ada FP8 tensor cores.

**Expected impact**: If we write custom CUTLASS INT8 or FP8 GEMM kernels for our specific matrix shapes, we could see 10-30% improvement over default cuBLAS dispatch.

**Requirements**: CUTLASS 4.4+, CUDA 13.0+ with `compute_120f` (NOT `compute_120a`). The `f` suffix is critical -- `a` suffix causes TMA WS grouped GEMM failures.

**Compatibility**: CUTLASS kernels can be called from PyTorch via custom C++ extensions. Independent of torch.compile.

**Evidence**:
- [CUTLASS SM120 Examples (example 79, 87)](https://docs.nvidia.com/cutlass/latest/overview.html)
- [CUTLASS SM120 GEMM Tutorial (Colfax)](https://research.colfax-intl.com/cutlass-tutorial-writing-gemm-kernels-using-tensor-memory-for-nvidia-blackwell-gpus/)
- [CUTLASS Issue #3096: SM120 FP4 fix with compute_120f](https://github.com/NVIDIA/cutlass/issues/3096)
- [CUTLASS Changelog](https://github.com/NVIDIA/cutlass/blob/main/CHANGELOG.md)

**Risk**: High engineering effort. Writing and integrating custom CUTLASS kernels is complex. The SM120 CUTLASS path is still maturing -- bugs in grouped GEMM, sparse ops.

**Verdict**: **Skip for now** -- Unless we identify a specific GEMM bottleneck that cuBLAS autotune can't solve, custom CUTLASS kernels aren't worth the engineering investment at this stage. Keep this option for future optimization passes.

---

## 9. GDDR7 Memory Bandwidth Optimization

**What**: RTX 5090 delivers 1.79 TB/s memory bandwidth on a 512-bit bus with GDDR7 @ 28 Gbps -- a 78% improvement over RTX 4090. The 98MB L2 cache further reduces DRAM traffic. GDDR7 also has lower latency and better energy efficiency than GDDR6X.

For autoregressive TTS inference (like Fish Speech S2-Pro), the decode phase is memory-bandwidth-bound since each step reads the full model weights but only produces one token. This means bandwidth directly limits tokens/sec.

**Expected impact**: Already captured in baseline -- the RTX 5090's bandwidth is what gives us our current 0.263x RTF. Further optimization is about maximizing effective bandwidth utilization:
- Ensure coalesced memory access patterns (32-byte aligned)
- Minimize DRAM traffic via L2 cache residency
- Use smaller quantization (INT8 already good; FP4 would halve bandwidth needs)

**Requirements**: No special requirements -- hardware feature. Software optimizations focus on data layout and access patterns.

**Compatibility**: Fully compatible with current stack.

**Evidence**:
- [RTX 5090 Specs: 1.79 TB/s bandwidth](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/)
- [Impact of RTX 5090 Memory Bandwidth on LLMs](https://blog.neevcloud.com/the-impact-of-rtx-5090s-memory-bandwidth-on-llms)
- [Blackwell Tuning Guide: memory access patterns](https://docs.nvidia.com/cuda/blackwell-tuning-guide/index.html)

**Risk**: None for analysis. The main actionable item is profiling to find memory-bound bottlenecks.

**Verdict**: **Try** -- Profile with Nsight Compute to measure achieved memory bandwidth vs theoretical peak. If we're below 60% utilization, there's room to improve data layout, batch KV cache accesses, or use persistent kernels. Key metric: bytes moved per generated token.

---

## 10. CUDA 13 Tile-Based Programming (cuTile)

**What**: CUDA 13.0/13.1 introduces a new tile-based programming model with cuTile Python DSL. It abstracts tensor core usage and provides forward compatibility for SM120 GPUs. This is a new paradigm alongside traditional thread-based CUDA, aimed at making GPU kernel development more accessible.

**Expected impact**: Long-term potential for writing high-performance custom kernels. Not immediately actionable for Fish Speech optimization.

**Requirements**: CUDA 13.1+, experimental API.

**Compatibility**: New paradigm -- would need new kernels written from scratch.

**Evidence**:
- [NVIDIA Blog: CUDA 13.1 cuTile](https://developer.nvidia.com/blog/nvidia-cuda-13-1-powers-next-gen-gpu-programming-with-nvidia-cuda-tile-and-performance-gains/)

**Risk**: Experimental API, limited ecosystem support.

**Verdict**: **Skip** -- Interesting for future but not actionable today. cuTile is too new and we'd be writing kernels from scratch.

---

## 11. Distributed Shared Memory (Thread Block Clusters)

**What**: Blackwell supports thread block clusters where threads can read/write shared memory of other thread blocks within the same cluster. Distributed shared memory + L2 provides combined bandwidth. SM120 supports max portable cluster size of 8.

**Expected impact**: Minimal for inference workloads. This is primarily useful for custom kernels that need inter-SM communication (training, custom attention patterns).

**Requirements**: CUDA 13.0+, custom kernel development.

**Compatibility**: Available on SM120.

**Evidence**:
- [Blackwell Tuning Guide: Distributed Shared Memory](https://docs.nvidia.com/cuda/blackwell-tuning-guide/index.html)

**Risk**: High engineering effort for uncertain gain.

**Verdict**: **Skip** -- Not relevant to our inference optimization goals.

---

## 12. Environment Variables and Flags

**What**: Several CUDA/cuBLAS/cuDNN environment variables can tune SM120 performance:

| Variable | Purpose | Recommended |
|---|---|---|
| `CUDA_MODULE_LOADING=LAZY` | Lazy module loading, reduces startup time | Yes |
| `CUBLAS_WORKSPACE_CONFIG=:4096:8` | Deterministic cuBLAS, enables workspace | Test both |
| `TORCH_CUDA_ARCH_LIST="12.0"` | Force SM120 compilation target | Yes (for building) |
| `FLASHINFER_CUDA_ARCH_LIST=12.0f` | Force FlashInfer to use compute_120f | Yes (if using FlashInfer) |
| `CUDA_DEVICE_MAX_CONNECTIONS=1` | Limit concurrent kernel streams | Test (can help or hurt) |
| `NVIDIA_TF32_OVERRIDE=1` | Force TF32 tensor core usage | Already enabled |
| `CUDA_FORCE_PTX_JIT=1` | Force PTX JIT compilation | Test on SM120 |

**Expected impact**: 0-10% from correct flag combination.

**Requirements**: Just environment variables.

**Compatibility**: All work with PyTorch 2.8.0.

**Evidence**:
- [Blackwell Tuning Guide](https://docs.nvidia.com/cuda/blackwell-tuning-guide/index.html)
- [CUDA 13.0 Release Notes](https://developer.nvidia.com/blog/whats-new-and-important-in-cuda-toolkit-13-0/)

**Risk**: Low. Easy to test and revert.

**Verdict**: **Try** -- Quick wins. Test each flag and measure impact.

---

## Priority Ranking

Based on effort vs impact for our specific setup (PyTorch 2.8.0, Fish Speech S2-Pro, RTX 5090):

| Priority | Technique | Effort | Expected Impact | Verdict |
|---|---|---|---|---|
| 1 | cuBLAS GEMM Autotune | Low | 5-15% | **Try now** |
| 2 | Environment variable tuning | Low | 0-10% | **Try now** |
| 3 | cuDNN 9 SDPA optimizations | Low-Med | 5-15% | **Try now** |
| 4 | GDDR7 bandwidth profiling | Low | Diagnostic | **Try now** |
| 5 | FlashAttention 2 (Triton/community) | Medium | 10-30% | **Try soon** |
| 6 | FP8 quantization (W8A8) | Medium | 10-25% | **Investigate** |
| 7 | TensorRT-RTX export | High | 30-60% | **Investigate** (POC) |
| 8 | CUTLASS custom kernels | High | 10-30% | **Skip (revisit later)** |
| 9 | NVFP4 quantization | High | 50-100% | **Skip (SM120 bugs)** |
| 10 | CUDA Tile / cuTile | High | Unknown | **Skip** |
| 11 | Distributed Shared Memory | High | Minimal | **Skip** |

---

## Key Risks and Constraints

1. **PyTorch version lock**: We CANNOT upgrade past 2.8.0 due to the 40-55% reduce-overhead regression in 2.10+. This blocks us from better Triton SM120 support, native FP8 torch ops, and NVFP4 integration.

2. **SM120 kernel maturity**: The entire ML kernel ecosystem (FlashAttention, FlashInfer, CUTLASS grouped GEMM, Triton) is still catching up to SM120. Many kernels either don't compile, produce wrong results, or fall back to SM80 codegen.

3. **compute_120f vs compute_120a**: When building anything for SM120, use the `f` suffix (compute_120f), NOT the `a` suffix. The `a` suffix lacks TMA WS GEMM support and causes crashes. This requires CUDA 13.0+.

4. **cuDNN LayerNorm/RMSNorm compilation**: Known to be slow on SM120 (cc 12.0). First inference may have extended warmup time.

5. **TensorRT-RTX is the escape hatch**: If PyTorch-level optimizations hit a ceiling, TensorRT-RTX bypasses the Triton/TorchInductor SM120 limitations entirely. It has its own SM120-optimized kernel library.

---

## Next Steps

1. **Immediate** (< 1 day): Enable cuBLAS autotune, test env vars, verify cuDNN version and SDPA backend routing
2. **Short-term** (1-3 days): Profile with Nsight Compute to identify GEMM vs attention vs memory bottlenecks. Test FA2 via community wheels.
3. **Medium-term** (1-2 weeks): POC TensorRT-RTX export of the transformer backbone component. Benchmark FP8 calibration on Fish Speech.
4. **Long-term** (future): Revisit NVFP4 when CUTLASS/PyTorch SM120 support stabilizes. Monitor PyTorch 2.8.x patch releases for SM120 backports.
