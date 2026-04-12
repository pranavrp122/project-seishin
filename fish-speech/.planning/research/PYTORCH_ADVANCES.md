# PyTorch & Quantization Advances for Fish Speech S2-Pro Inference

**Baseline**: PyTorch 2.8.0+cu128, torchao 0.12.0, INT8 W8A16 (`Int8WeightOnlyConfig`), `torch.compile(mode="reduce-overhead", fullgraph=False)`, BF16+TF32, RTX 5090 (SM120), 9.2GB VRAM, RTF 0.263x

**Research date**: April 2026

---

## 1. Torchao Quantization Beyond INT8 W8A16

### 1a. INT8 Dynamic Activation + INT8 Weight (`Int8DynamicActivationInt8WeightConfig`)

**What**: Quantizes both activations (dynamically, per-token symmetric) and weights (per-channel) to INT8, enabling true INT8 GEMM compute instead of dequantize-to-BF16 matmul.

**Expected impact**: ~7-15% speedup over INT8 weight-only at batch sizes >= 16. Larger speedups at bigger matrix dimensions. Minimal additional VRAM savings since weights are already INT8; the gain is purely computational.

**Compatibility**: Works on PyTorch 2.8.0, SM120, and composes with `torch.compile`. Drop-in replacement for `Int8WeightOnlyConfig`.

**Code**:
```python
from torchao.quantization import quantize_, Int8DynamicActivationInt8WeightConfig
quantize_(model, Int8DynamicActivationInt8WeightConfig())
model = torch.compile(model, mode="reduce-overhead")
```

**Evidence**: torchao benchmarks show ~7.7% speedup at batch size 16 on full model; more at larger batch sizes. The INT8 mm op is fused and optimized under `torch.compile`.

**Risk**: Slight accuracy degradation from activation quantization. Per-token dynamic scaling adds overhead on very small matrices. Need to verify speech quality with perceptual metrics (UTMOS, WER).

**Verdict**: **Try** -- Low-hanging fruit. Same VRAM footprint, potential 7-15% latency reduction.

---

### 1b. Float8 Dynamic Activation + Float8 Weight (`Float8DynamicActivationFloat8WeightConfig`)

**What**: FP8 (E4M3/E5M2) quantization of both weights and activations. On GPUs with compute capability >= 8.9, this uses hardware-accelerated FP8 tensor cores via `_scaled_mm`.

**Expected impact**: 1.5-1.6x speedup demonstrated on H100 for LLMs. On SM120, FP8 tensor cores are available but use the HMMA instruction path (not TMEM). Expect 1.2-1.4x speedup over BF16 baseline, roughly 10-20% over current INT8 W8A16.

**Compatibility**: Requires compute capability >= 8.9 (SM120 qualifies). Works with torchao >= 0.8. Composes with `torch.compile`. Available in torchao 0.12.0.

**Code**:
```python
from torchao.quantization import quantize_, Float8DynamicActivationFloat8WeightConfig
quantize_(model, Float8DynamicActivationFloat8WeightConfig())
model = torch.compile(model, mode="reduce-overhead")
```

**Evidence**: torchao docs: "For GPUs with compute capability of at least 8.9 (RTX-4090, Hopper, etc.), FP8 often provides the best speed, memory, and quality trade-off." 1.54x speedup on Flux.1-Dev, 1.27x on CogVideoX-5b (H100).

**Risk**: SM120 FP8 matmul performance may be lower than SM90 (H100) due to different tensor core architecture. Quality impact on speech codec tokens is unknown. FP8 has lower dynamic range than INT8 for some distributions.

**Verdict**: **Try** -- Potentially the best single optimization. Benchmark against INT8 dynamic activation on our specific model shapes.

---

### 1c. MXFP8 Microscaling (`MXFPInferenceConfig` / `MXDynamicActivationMXWeightConfig`)

**What**: OCP Microscaling FP8 format -- groups of 32 elements share a high-precision scale factor. Natively accelerated on Blackwell tensor cores. Better accuracy than standard FP8 due to fine-grained scaling.

**Expected impact**: Up to ~2x speedup vs BF16 on B200 hardware. On SM120 (RTX 5090), hardware acceleration is available. 1.26x end-to-end speedup demonstrated on diffusion workloads.

**Compatibility**: Requires Blackwell GPU (SM100/SM120 with CUDA >= 12.8). **PROTOTYPE API** in torchao -- subject to change. Requires torchao nightly builds (0.14+) or specific releases with MXFP8 support. May NOT work with torchao 0.12.0.

**Code**:
```python
from torchao.prototype.mx_formats import MXFPInferenceConfig
from torchao.quantization import quantize_
quantize_(model, MXFPInferenceConfig(block_size=32))
model = torch.compile(model, mode="reduce-overhead")
```

**Evidence**: PyTorch blog (2025): "MXFP8 achieves up to ~2x speedup vs bfloat16 baseline on common shapes when using cuBLAS backend on B200 hardware." 1.26x end-to-end on Flux.1-Dev.

**Risk**: Prototype API -- may break. Requires upgrading torchao beyond 0.12.0 (potentially torchao 0.14+ nightly with cu128/cu130). SM120 kernel support may differ from SM100 (B200). Selective quantization recommended (skip layers where min(M,K,N) < 1024).

**Verdict**: **Investigate further** -- High potential but requires torchao upgrade and SM120 kernel verification. Test on nightly builds first.

---

### 1d. NVFP4 Weight-Only or Dynamic (`NVFP4InferenceConfig`)

**What**: 4-bit floating point (E2M1) with FP8 scaling factors, block size 16. Uniquely accelerated by Blackwell tensor cores. ~3.5x smaller than BF16.

**Expected impact**: Up to 2.77x roofline speedup on B200. 1.68x end-to-end on diffusion workloads. Would cut model VRAM roughly in half (~4.5GB from ~9GB).

**Compatibility**: Requires compute capability >= 10.0 (SM100+). SM120 (RTX 5090) qualifies, but SM120 and SM100 have different kernel paths. NVFP4 GEMM ops that expected SM100 have been reported to fail on SM120 -- requires specific SM120 kernel implementations.

**Code**:
```python
from torchao.prototype.mx_formats import NVFP4InferenceConfig
from torchao.quantization import quantize_
quantize_(model, NVFP4InferenceConfig())
```

**Evidence**: NVIDIA blog: "NVFP4 KV cache reduces memory footprint by about 50% compared to FP8." torchao: "up to 61% end-to-end performance improvement in vLLM on Qwen3 models."

**Risk**: High risk of quality degradation on speech synthesis -- 4-bit weights may produce audible artifacts in codec token prediction. SM120 kernel compatibility is still being worked on. Prototype API. Requires torchao nightly + CUDA 12.8+.

**Verdict**: **Skip for now** -- Quality risk too high for speech synthesis without extensive validation. Revisit when SM120 kernel support stabilizes and we can run quality tests.

---

### 1e. Mixed-Precision Quantization (Per-Module Config)

**What**: Apply different quantization configs to different layers. For example, use FP8 for large FFN layers and INT8 for smaller attention projections. Skip quantization for layers where overhead exceeds benefit.

**Expected impact**: 5-15% additional speedup over uniform quantization by optimizing each layer individually.

**Compatibility**: Supported in torchao 0.12.0 via `quantize_` with a dict mapping module names to configs.

**Code**:
```python
from torchao.quantization import quantize_, Int8WeightOnlyConfig, Float8DynamicActivationFloat8WeightConfig

config_map = {
    "model.layers.*.feed_forward": Float8DynamicActivationFloat8WeightConfig(),
    "model.layers.*.attention": Int8DynamicActivationInt8WeightConfig(),
}
# Apply per-module (check exact torchao API for dict config)
quantize_(model, config_map)
```

**Evidence**: torchao supports "module level configuration by specifying a dictionary from fully qualified name of module and its corresponding quantization config." Selective quantization is recommended for MXFP8/NVFP4 (skip layers where min(M,K,N) < 1024).

**Risk**: Requires profiling each layer's shapes to determine optimal config. More complex to maintain. May interact unexpectedly with CUDA graphs.

**Verdict**: **Investigate further** -- Profile layer shapes first, then apply targeted configs.

---

## 2. torch.compile Improvements

### 2a. Coordinate Descent Tuning

**What**: After initial Triton kernel autotuning, applies coordinate descent optimization to find better kernel configurations. Can be combined with checking all directions.

**Expected impact**: 3-10% additional speedup on compiled kernels, especially for non-standard matrix shapes common in transformer inference.

**Compatibility**: Available in PyTorch 2.8.0. Works with `reduce-overhead` mode. Set via inductor config.

**Code**:
```python
import torch._inductor.config as inductor_config
inductor_config.coordinate_descent_tuning = True
inductor_config.coordinate_descent_check_all_directions = True

model = torch.compile(model, mode="reduce-overhead")
```

**Evidence**: Widely used in diffusion model optimization pipelines. The PyTorch inductor config source shows these as stable options.

**Risk**: Increases compilation time significantly (can 2-3x the initial compile). Cached after first run. May not help if current Triton configs are already near-optimal for our shapes.

**Verdict**: **Try** -- Free performance after first compile. Set it and forget it.

---

### 2b. Weight Freezing (`TORCHINDUCTOR_FREEZING=1`)

**What**: Constant-folds model parameters into the compiled graph, enabling additional optimizations like weight fusion and elimination of parameter lookups. Weights become embedded constants.

**Expected impact**: ~15% speedup observed in benchmarks. Eliminates parameter access overhead. Enables more aggressive constant folding and operator fusion.

**Compatibility**: Available in PyTorch 2.8.0. Requires `torch.no_grad()` context (which we already use for inference). Works with `reduce-overhead` mode.

**Code**:
```python
import os
os.environ["TORCHINDUCTOR_FREEZING"] = "1"

# Optional: discard original parameters to save memory
import torch._inductor.config as inductor_config
inductor_config.freezing_discard_parameters = True

with torch.no_grad():
    model = torch.compile(model, mode="reduce-overhead")
    output = model(input)  # first call triggers compilation with frozen weights
```

**Evidence**: PyTorch docs: "freezing is the process of inlining PyTorch module parameters and attributes values into the TorchScript internal representation." ~15% faster than non-frozen scripted models. "For better performance during CPU inference, it is suggested to enable freezing" -- same principle applies to GPU.

**Risk**: Weights become immutable after compilation. Cannot update model weights without recompilation. Not an issue for inference-only deployment. `freezing_discard_parameters=True` frees the original nn.Module parameters, saving memory but making the module unusable outside compiled calls.

**Verdict**: **Try** -- One environment variable for ~15% speedup. We're already inference-only. `freezing_discard_parameters=True` would free additional VRAM.

---

### 2c. Max-Autotune Mode (with manual CUDA graph control)

**What**: Instead of `reduce-overhead`, use `max-autotune-no-cudagraphs` to get the best kernel selection via autotuning, then manage CUDA graphs manually for finer control.

**Expected impact**: Better kernel selection than `reduce-overhead` (which uses heuristics). The mode profiles GEMM backends (ATEN, TRITON, CUTLASS) and selects the fastest.

**Compatibility**: Available in PyTorch 2.8.0. RTX 5090 has >= 68 SMs so max-autotune GEMM is supported.

**Code**:
```python
model = torch.compile(model, options={
    "max_autotune": True,
    "coordinate_descent_tuning": True,
    "triton.cudagraphs": False,  # manage manually
    "epilogue_fusion": True,     # fuse pointwise ops into GEMM templates
})
# Then manually capture CUDA graphs for specific input shapes
```

**Evidence**: `max_autotune_gemm_backends` profiles ATEN, TRITON, and CPP backends. Epilogue fusion (pointwise ops into GEMM templates) requires `max_autotune=True`.

**Risk**: Much longer compilation time (profiles many kernel variants). Loses automatic CUDA graph management from `reduce-overhead` -- must implement manually. More engineering effort. Could conflict with our existing CUDA graph setup.

**Verdict**: **Investigate further** -- Try adding `max_autotune` and `coordinate_descent_tuning` to the existing `reduce-overhead` mode first (via `options` dict). If that doesn't work, test `max-autotune-no-cudagraphs` separately.

---

### 2d. AOTInductor (Ahead-of-Time Compilation)

**What**: Pre-compile the model to a `.pt2` artifact that can be loaded with zero warm-up time. Eliminates the JIT compilation overhead on first inference.

**Expected impact**: Zero warm-up latency (currently first inference triggers full compilation). Same runtime performance as JIT-compiled model. Can also be deployed in C++ for even lower overhead.

**Compatibility**: Beta in PyTorch 2.8.0. Requires `torch.export.export()` first (may have issues with dynamic shapes in DualAR). Linux-only for packaging.

**Code**:
```python
# Compile phase (run once, offline)
import torch
exported = torch.export.export(model, example_inputs)
torch._inductor.aoti_compile_and_package(exported, package_path="model.pt2")

# Runtime phase (instant load, no compile overhead)
compiled_model = torch._inductor.aoti_load_package("model.pt2")
output = compiled_model(*inputs)
```

**Evidence**: PyTorch docs: "At deployment time, after loading the model, running inference does not have any additional cost." 2-5x inference speedups over eager reported. Eliminates the 30-60s warmup we currently experience.

**Risk**: `torch.export` may struggle with dynamic control flow in DualAR (slow/fast AR switching). Beta API -- may have edge cases. Input shapes must be fixed at export time (need bucketing strategy). Version-locked to the exact PyTorch used for compilation.

**Verdict**: **Investigate further** -- Worth trying for eliminating warmup. Test `torch.export` on our model first to see if it succeeds.

---

## 3. CUDA Graph Optimizations

### 3a. Input Shape Bucketing for Variable-Length Sequences

**What**: Pre-capture CUDA graphs at discrete sequence lengths (e.g., 128, 256, 384, 512, 1024) and pad inputs to the nearest bucket. At runtime, select the matching graph.

**Expected impact**: Reduces padding waste by 50-75% compared to always padding to max length. Each bucket runs at optimal CUDA graph speed.

**Compatibility**: Works with PyTorch 2.8.0 `torch.compile(mode="reduce-overhead")`. CUDAGraph Trees already handle multiple capture shapes.

**Implementation strategy**:
```python
# Warm up at each bucket size to pre-capture graphs
BUCKETS = [128, 256, 384, 512, 768, 1024]
for bucket_size in BUCKETS:
    dummy_input = create_dummy_input(seq_len=bucket_size)
    with torch.no_grad():
        model(dummy_input)  # triggers graph capture for this shape
```

**Evidence**: AWS Neuron docs: "We define a set of ascending bucket sizes and pre-compile program graphs with input sizes according to these bucket values." vLLM, SGLang, TensorRT-LLM all use bucketing. Typical 20-40% latency reduction from avoiding max-length padding.

**Risk**: Memory overhead proportional to number of buckets (each graph stores all intermediate activations). With 6 buckets, expect ~6x the single-graph memory overhead for intermediates. Need to profile VRAM impact. Bucket selection adds minor CPU overhead.

**Verdict**: **Try** -- Standard practice for production inference. Start with 4-5 buckets based on our actual sequence length distribution.

---

### 3b. Selective CUDA Graphs (PyGraph Approach)

**What**: Only deploy CUDA graphs for kernel sequences where replay overhead is less than the launch overhead savings. The PyGraph paper (2025) found ~25% of CUDA graph replays actually hurt performance.

**Expected impact**: Up to 29% geomean speedup over PyTorch's default CUDA graph strategy (up to 3.36x in best cases). Avoids performance-degrading graph replays.

**Compatibility**: PyGraph is a research framework, not yet integrated into PyTorch mainline. The concepts can be applied manually by profiling which graph segments benefit from CUDA graphs.

**Evidence**: PyGraph paper (arXiv:2503.19779): "Across 25 ML applications, PyGraph provides a geomean speedup of 29% over PyTorch2's CUDA Graph feature on H100." Parameter indirection reduced copy overhead by >99% (from ~1GB to ~312 bytes).

**Risk**: Requires manual implementation of selective graph deployment. Not available as a PyTorch API. Complex to integrate with `torch.compile` automatic graph capture.

**Verdict**: **Skip** -- Interesting research but not actionable without significant custom engineering. Monitor for PyTorch integration.

---

### 3c. `cudagraph_support_input_mutation` and Dynamic Graph Skipping

**What**: Inductor config flags for fine-tuning CUDA graph behavior.

**Code**:
```python
import torch._inductor.config as cfg
cfg.cudagraph_support_input_mutation = True  # handle in-place ops on graph inputs
cfg.triton.cudagraph_skip_dynamic_graphs = True  # skip graphs with dynamic shapes, use eager
```

**Evidence**: PyTorch source `torch/_inductor/config.py`. These flags exist in PyTorch 2.8.0.

**Risk**: `cudagraph_skip_dynamic_graphs` may cause some forward passes to fall back to eager mode, introducing latency variance.

**Verdict**: **Try** -- Small config changes that may improve stability and avoid bad graph captures.

---

## 4. KV Cache Quantization

### 4a. INT8 KV Cache

**What**: Quantize the Key and Value tensors in the attention cache to INT8, reducing KV cache memory by 4x (from FP32) or 2x (from BF16/FP16).

**Expected impact**: For our model (2560 dim, 8 KV heads, 36 layers), KV cache at BF16 for a 1024-token sequence is approximately:
- Per layer: 2 * 1024 * (2560/4) * 2 bytes = 2.5 MB (8 KV heads = 2560/4 = 640 dim per head)
- Total: 36 layers * 2.5 MB = ~90 MB
- With INT8: ~45 MB (50% savings)
The VRAM savings are modest for single-sequence inference but significant for batched inference.

**Compatibility**: torchao supports KV cache quantization but primarily through model-level integration (not a simple `quantize_()` call). Requires modifying the attention/cache implementation in the model code.

**Implementation approach**: The KV cache quantization in torchao is implemented at the attention layer level. For our custom DualAR model, we would need to:
1. Quantize K,V tensors to INT8 before storing in cache
2. Dequantize on read before attention computation
3. Use per-channel or per-token scaling factors

**Evidence**: torchao blog: "quantize weights to int4 and the kv cache to int8 to support Llama 3.1 8B at the full 128K context length running in under 18.9GB of VRAM" -- 55% peak memory reduction. January 2026 paper: "GPU-accelerated INT8 quantization for KV cache compression, achieving 4x memory reduction with minimal accuracy degradation."

**Risk**: Requires custom integration into our attention module. Quantization/dequantization adds per-step overhead. For our relatively small KV cache (~90 MB at BF16), the absolute VRAM savings are small. May impact attention precision for audio token prediction.

**Verdict**: **Skip for single-sequence** -- The ~45 MB saving is not worth the integration complexity. **Investigate for batched inference** where KV cache grows proportionally with batch size.

---

### 4b. FP8 KV Cache with Low-Precision Attention

**What**: Store KV cache in FP8 and use FP8 attention computation end-to-end via `apply_low_precision_attention`.

**Expected impact**: 2x memory reduction vs BF16 KV cache. Potential speedup from FP8 attention kernel (FlashAttention-3 FP8 path).

**Compatibility**: torchao's `apply_low_precision_attention` requires PyTorch >= 2.11 and Flash Attention 3 on SM90 or FA4 on SM100. **SM120 (RTX 5090) does NOT support FA4** due to missing TMEM hardware. FA3 is Hopper-only. Therefore, this specific API **will not work on RTX 5090**.

**Evidence**: torchao docs: "FP8 low-precision attention for inference is built on Flash Attention backends. Currently supports FA3 on Hopper (SM90) and FA4 on Blackwell (SM100). Requirements: PyTorch >= 2.11."

**Risk**: Not supported on our hardware (SM120).

**Verdict**: **Skip** -- Hardware incompatible. SM120 lacks TMEM needed for FA4, and FA3 requires SM90.

---

### 4c. NVIDIA NVFP4 KV Cache

**What**: Store KV cache at 4-bit precision using NVIDIA's FP4 format with FP8 scaling factors.

**Expected impact**: 50% smaller than FP8 KV cache, 75% smaller than BF16. "Less than 1% accuracy loss on benchmarks" per NVIDIA.

**Compatibility**: Available via TensorRT Model Optimizer on Blackwell GPUs. Not yet available as a standalone torchao API for custom models. Primarily integrated through TensorRT-LLM.

**Evidence**: NVIDIA blog (December 2025): "NVFP4 KV cache quantization reduces KV cache memory footprint by 50% compared to FP8, enables doubling of context length and batch size."

**Risk**: Not available in our PyTorch-native stack. Would require migrating to TensorRT-LLM. Not applicable for custom DualAR model without significant work.

**Verdict**: **Skip** -- Not available in PyTorch-native stack.

---

## 5. Speculative Decoding for DualAR

### 5a. Multi-Token Prediction (MTP) for Slow AR

**What**: Add multiple prediction heads to the Slow AR transformer to predict N future tokens per step instead of 1. Uses lightweight linear heads on top of the existing hidden state.

**Expected impact**: The codec-TTS paper (Nguyen et al., 2024) reports **4-5x reduction in time per token** with Viterbi-based speculative decoding. Even with just 2-3 prediction heads, 1.5-2x speedup is achievable. For our RTF of 0.263x, this could push to 0.13-0.18x RTF.

**Compatibility**: Requires training additional prediction heads. The DualAR architecture's Slow AR (~20 tokens/s time axis) is the bottleneck -- this directly addresses it. The Fast AR (filling codebooks) runs per-timestep and is already fast.

**Implementation approach**:
1. Add N linear prediction heads to the Slow AR's final hidden layer
2. Train them with a multi-token prediction objective (predict tokens t+1, t+2, ..., t+N)
3. At inference, generate N draft tokens, verify with the full model in parallel
4. Accept verified tokens, reject and regenerate from first rejected position

**Evidence**: "Accelerating Codec-based Speech Synthesis with Multi-Token Prediction and Speculative Decoding" (arXiv:2410.13839): "The time required to predict each token is reduced by a factor of 4 to 5 compared to baseline models, with minimal quality trade-off or even improvement in terms of speech intelligibility."

**Risk**: Requires retraining or fine-tuning with additional prediction heads (significant training cost). Quality with >4 heads degrades without Viterbi decoding. The DualAR architecture complicates verification -- the Fast AR depends on Slow AR outputs, so the verification step must account for this coupling. CUDA graph compatibility needs careful engineering.

**Verdict**: **Investigate further (medium-term)** -- Highest potential speedup (2-5x) but requires training investment. Should be a separate project phase. Start with 2-head MTP as a proof of concept.

---

### 5b. Draft Model Approach (Small Model Generates, Large Verifies)

**What**: Use a smaller, faster transformer as a draft model for the Slow AR, then verify with the full 4B model.

**Expected impact**: VADUSA (TTS-specific) reports ~1.4x speedup. General LLM speculative decoding achieves 2-3x. For TTS, the acceptance rate depends heavily on draft model quality.

**Compatibility**: Architecturally feasible but requires training a separate smaller model on the same codec vocabulary.

**Evidence**: TorchSpec (PyTorch, 2026): "+60% output throughput at batch size 1, +30% at batch size 8" for LLM with EAGLE-3 draft model. VADUSA: "significantly improves inference speed" for auto-regressive TTS.

**Risk**: Need to train a separate draft model (e.g., a 400M parameter version of the Slow AR). Draft model must share the same tokenizer/codec. Overhead of running two models may negate gains if acceptance rate is low. Complex engineering for the DualAR two-stage pipeline.

**Verdict**: **Skip for now** -- MTP (5a) is simpler and more promising for our architecture. Draft model approach requires training a separate model from scratch.

---

### 5c. DualAR as Built-in Speculative Decoding

**What**: The DualAR architecture already has a form of speculative execution -- the Fast AR fills in codebook details "speculatively" conditioned on Slow AR outputs. Could the Fast AR be used as a lightweight predictor for the next Slow AR token?

**Expected impact**: Unknown -- would need novel research to determine if Fast AR hidden states can predict next Slow AR tokens.

**Compatibility**: Would require architectural changes to the model.

**Risk**: Highly speculative (pun intended). The Fast AR operates on a different axis (codebook depth vs. time). No existing research validates this approach.

**Verdict**: **Skip** -- Too speculative without supporting evidence.

---

## 6. FlashAttention / Memory-Efficient Attention

### 6a. FlashAttention-2 via Triton on SM120

**What**: FlashAttention-2 compiled via Triton, which is the default `flex_attention` backend. This is what PyTorch's SDPA uses when Triton is available.

**Expected impact**: Already likely active if using `torch.nn.functional.scaled_dot_product_attention`. Provides O(N) memory instead of O(N^2) and is significantly faster than naive attention.

**Compatibility**: Fully supported on SM120 (RTX 5090). FlashAttention package v2.8.3 can be compiled with `TORCH_CUDA_ARCH_LIST="12.0"`.

**Installation**:
```bash
export TORCH_CUDA_ARCH_LIST="12.0"
pip install flash-attn==2.8.3 --no-build-isolation
```

**Evidence**: Multiple sources confirm FA2 works on SM120. Recent releases added SM120 varlen attention support (PR #2333 in flash-attention repo).

**Risk**: Building from source can be slow (2h without ninja, 3-5 min with). May need to verify our model actually uses SDPA/FlashAttention rather than manual attention implementation.

**Verdict**: **Try/Verify** -- Check if our model already uses SDPA. If using manual attention, switch to `F.scaled_dot_product_attention` for automatic FlashAttention dispatch.

---

### 6b. FlashAttention-4 on SM120

**What**: FA4 written in CuTeDSL, targeting Hopper (SM90) and Blackwell (SM100) with warp-specialized kernels exploiting TMEM (Tensor Memory).

**Expected impact**: 1.2-3.2x faster than FA2/Triton on compute-bound workloads.

**Compatibility**: **NOT COMPATIBLE with SM120 (RTX 5090)**. SM120's tensor cores use HMMA instructions (Volta/Ampere family), not the TMEM-based path. The TMEM hardware is physically absent from the GB202 die. This is a silicon-level difference, not a software limitation.

**Evidence**: Detailed investigation (GitHub gist by solatticus): "SM120 uses the older HMMA instruction family... TMEM hardware is physically absent from the GB202 die." PyTorch blog (March 2026) confirms FA4 targets SM90 and SM100 only.

**Risk**: N/A -- hardware incompatible.

**Verdict**: **Skip** -- Hardware limitation. FA2 via Triton remains the best available path for SM120.

---

### 6c. PyTorch Native SDPA Improvements

**What**: `torch.nn.functional.scaled_dot_product_attention` (SDPA) automatically selects the best available backend (FlashAttention, Memory-Efficient, Math). PyTorch 2.8 includes improvements to the Triton FlashAttention backend.

**Expected impact**: If our model uses custom attention code, switching to SDPA gives automatic backend selection and fusion with `torch.compile`.

**Compatibility**: Native in PyTorch 2.8.0. Works on all GPUs.

**Code**:
```python
# In attention module, replace manual attention with:
from torch.nn.functional import scaled_dot_product_attention
attn_output = scaled_dot_product_attention(
    query, key, value,
    attn_mask=mask,
    dropout_p=0.0,
    is_causal=True  # for autoregressive
)
```

**Evidence**: Without FlashAttention: "vLLM on GB10 is stuck in eager SDPA -- no CUDA graphs, no paged attention, no kernel fusion." Performance jumped from 13 tok/s to 65-100+ tok/s after enabling proper FlashAttention.

**Risk**: May require refactoring attention code if using custom implementation. Causal masking semantics must match existing behavior. GQA (grouped-query attention with 32 heads / 8 KV heads) is supported by SDPA.

**Verdict**: **Try** -- Verify our attention implementation uses SDPA. If not, migrate to it.

---

## 7. Bonus: 2:4 Structured Sparsity

### 7a. Semi-Structured (2:4) Sparsity + Quantization

**What**: Prune 2 out of every 4 elements in weight matrices, then quantize the remaining weights. Tensor cores can skip zero elements, effectively doubling throughput.

**Expected impact**: 2:4 sparsity alone: 1.3x speedup (2x with torch.compile on BERT). Combined INT4 + 2:4 sparsity: 2.37x throughput with 67.7% memory reduction on Llama-3-8B.

**Compatibility**: torchao supports `SparseSemiStructuredTensor`. Benchmarks exist for SM80 (A100) and SM90 (H100). **SM120 benchmarks are not yet available** -- kernel support is still being finalized.

**Evidence**: torchao: "Int4 + 2:4 Sparsity achieved 2.37x throughput with 67.7% memory reduction on Llama-3-8B." 2:4 sparsity paper accepted to SLLM @ ICLR 2025.

**Risk**: Requires pruning the model (fine-tuning/retraining to maintain quality). SM120 kernel support unconfirmed. Industry adoption outside Chinese AI labs is limited. Speech quality impact unknown.

**Verdict**: **Skip** -- Requires retraining, SM120 unproven, and quality risk for speech synthesis is high.

---

## 8. Critical: PyTorch 2.10+ Regression

### The Regression (Confirmed)

**What**: `torch.compile(mode="reduce-overhead")` has a 40-55% throughput regression in PyTorch 2.10 vs 2.9. Root cause: 7x slower `cudaGraphLaunch` calls and new Python-level overhead in `cudagraph_trees.py`.

**Tracked**: GitHub Issue [#174575](https://github.com/pytorch/pytorch/issues/174575) (opened February 8, 2026).

**Details**: Even keeping CUDA 12.8 while upgrading to torch 2.10 shows 17% regression. No workaround via mode switching (`max-autotune`, `default`, `no-cudagraph`) recovers the lost performance.

**Impact on us**: Validates our decision to stay on PyTorch 2.8.0. Do NOT upgrade to 2.10+ until this is resolved.

**Monitoring**: Watch the GitHub issue for a fix. If resolved in 2.11 or 2.12, upgrading would also unlock MXFP8/NVFP4 APIs and newer torchao features.

---

## Priority Ranking (Effort vs. Impact)

| Priority | Technique | Expected Impact | Effort | Risk |
|----------|-----------|----------------|--------|------|
| 1 | Weight Freezing (`TORCHINDUCTOR_FREEZING=1`) | ~15% speedup | 1 line | Low |
| 2 | Coordinate Descent Tuning | 3-10% speedup | 2 lines | Low |
| 3 | Verify/Enable FlashAttention-2 via SDPA | 10-50% on attention | Medium | Low |
| 4 | `Int8DynamicActivationInt8WeightConfig` | 7-15% speedup | 1 line change | Low |
| 5 | `Float8DynamicActivationFloat8WeightConfig` | 10-20% speedup | 1 line change | Medium |
| 6 | CUDA Graph Bucketing | 20-40% less padding waste | Medium | Low |
| 7 | `cudagraph_support_input_mutation` + dynamic skip | Stability improvement | 2 lines | Low |
| 8 | Mixed-precision per-module quantization | 5-15% additional | High | Medium |
| 9 | MXFP8 (requires torchao upgrade) | Up to 2x on matmuls | High | High |
| 10 | Multi-Token Prediction (speculative decoding) | 2-5x on Slow AR | Very High | High |
| 11 | AOTInductor | Zero warmup | High | Medium |

---

## Recommended Action Plan

### Phase 1: Quick Wins (1-2 days)
1. Set `TORCHINDUCTOR_FREEZING=1` + `freezing_discard_parameters=True`
2. Enable `coordinate_descent_tuning` + `coordinate_descent_check_all_directions`
3. Verify model uses SDPA / FlashAttention (if not, migrate)
4. Set `cudagraph_support_input_mutation=True`

### Phase 2: Quantization Exploration (3-5 days)
5. Benchmark `Int8DynamicActivationInt8WeightConfig` vs current `Int8WeightOnlyConfig`
6. Benchmark `Float8DynamicActivationFloat8WeightConfig` vs both INT8 options
7. Run quality evaluation (UTMOS, WER, MOS) on each quantization variant
8. Profile per-layer shapes and test mixed-precision configs

### Phase 3: CUDA Graph Refinement (3-5 days)
9. Analyze sequence length distribution from production traffic
10. Implement bucketing strategy with 4-6 sequence length buckets
11. Measure VRAM overhead vs. latency improvement tradeoff

### Phase 4: Advanced (weeks-months)
12. Evaluate MXFP8 on torchao nightly when SM120 kernels stabilize
13. Prototype 2-head multi-token prediction for Slow AR
14. Test AOTInductor for zero-warmup deployment

---

## Sources

- [torchao Quantized Inference Docs](https://docs.pytorch.org/ao/stable/workflows/inference.html)
- [Faster Diffusion on Blackwell: MXFP8 and NVFP4 with Diffusers and TorchAO (PyTorch Blog)](https://pytorch.org/blog/faster-diffusion-on-blackwell-mxfp8-and-nvfp4-with-diffusers-and-torchao/)
- [PyTorch Inductor Config Source](https://github.com/pytorch/pytorch/blob/main/torch/_inductor/config.py)
- [torch.compile Documentation](https://docs.pytorch.org/docs/stable/generated/torch.compile.html)
- [CUDAGraph Trees Documentation](https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/torch.compiler_cudagraph_trees.html)
- [PyGraph: Robust Compiler Support for CUDA Graphs in PyTorch](https://arxiv.org/abs/2503.19779)
- [CUDA Graphs in LLM Inference Deep Dive](https://dev.to/sfahad/cuda-graphs-in-llm-inference-deep-dive-36pb)
- [CUDA Graphs Best Practice for PyTorch (NVIDIA)](https://docs.nvidia.com/dl-cuda-graph/torch-cuda-graph/best-practices.html)
- [How CUDA Graph Works in torch.compile](https://fkong.tech/posts/2025-12-23-cuda-graph-in-torch-compile/)
- [PyTorch reduce-overhead Regression Issue #174575](https://github.com/pytorch/pytorch/issues/174575)
- [GPU-Accelerated INT8 Quantization for KV Cache Compression](https://arxiv.org/html/2601.04719v1)
- [NVIDIA NVFP4 KV Cache Blog](https://developer.nvidia.com/blog/optimizing-inference-for-long-context-and-large-batch-sizes-with-nvfp4-kv-cache/)
- [Accelerating Codec-based Speech Synthesis with Multi-Token Prediction and Speculative Decoding](https://arxiv.org/abs/2410.13839)
- [TorchSpec: Speculative Decoding Training at Scale (PyTorch Blog)](https://pytorch.org/blog/torchspec-speculative-decoding-training-at-scale/)
- [FlexAttention + FlashAttention-4 (PyTorch Blog)](https://pytorch.org/blog/flexattention-flashattention-4-fast-and-flexible/)
- [FlashAttention-4 Cannot Run on RTX 5090 (SM120) Investigation](https://gist.github.com/solatticus/aab6ec3a0436748b021cbbdd12e8c739)
- [Flash Attention SM120 Issue #1665](https://github.com/Dao-AILab/flash-attention/issues/1665)
- [FlashAttention Releases](https://github.com/Dao-AILab/flash-attention/releases)
- [AOTInductor Documentation](https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/torch.compiler_aot_inductor.html)
- [State of torch.compile for Training (August 2025)](https://blog.ezyang.com/2025/08/state-of-torch-compile-august-2025/)
- [torchao Sparsity Overview](https://docs.pytorch.org/ao/stable/contributing/sparsity.html)
- [PyTorch Native Architecture Optimization: torchao Blog](https://pytorch.org/blog/pytorch-native-architecture-optimization/)
- [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v1)
- [VLLM CUDA Graphs Design](https://docs.vllm.ai/en/stable/design/cuda_graphs/)
- [Autotuning in PyTorch & Triton (Ian's Blog)](https://ianbarber.blog/2025/05/04/autotuning-in-pytorch-triton/)
- [torchao GitHub Repository](https://github.com/pytorch/ao)
- [PyTorch GPU Quantization Tutorial](https://docs.pytorch.org/tutorials/unstable/gpu_quantization_torchao_tutorial.html)
- [Int8DynamicActivationInt8WeightConfig API Docs](https://docs.pytorch.org/ao/stable/generated/torchao.quantization.Int8DynamicActivationInt8WeightConfig.html)
