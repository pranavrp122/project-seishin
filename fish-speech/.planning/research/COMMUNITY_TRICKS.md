# Community & Forum Optimization Tricks

Research date: 2026-04-12
Stack: Fish Speech S2-Pro, RTX 5090 (SM120 Blackwell, 32GB), PyTorch 2.8.0+cu128, INT8 W8A16, torch.compile reduce-overhead
Current: 9.2GB VRAM, RTF 0.263x

---

## 1. SGLang Inference Engine (Official Recommendation)

**Source**: [Fish Audio S2 Technical Report (arXiv 2603.08823)](https://arxiv.org/html/2603.08823v2), [Fish Speech inference docs](https://github.com/fishaudio/fish-speech/blob/main/docs/en/inference.md), [Fish Audio blog on inference engines](https://fish.audio/blog/open-source-llm-inference-engines-2026/)
**What**: Replace torch.compile-based inference with SGLang serving framework. Fish Audio's own production stack uses SGLang, achieving RTF 0.195 on H200. SGLang provides continuous batching, paged KV cache, CUDA graph replay, and RadixAttention prefix caching. Because Dual-AR is structurally isomorphic to standard LLMs, it inherits all SGLang optimizations with zero modification.
**Claimed impact**: RTF 0.195 (H200), TTFA 100ms, 3000+ tokens/sec throughput, 86.4% prefix-cache hit rate for voice reuse. SGLang is 29% faster than vLLM on throughput benchmarks.
**Applicable to us?**: YES -- this is the official recommended path. Our current torch.compile approach (RTF 0.263x) is explicitly described as the fallback. SGLang with RadixAttention would be especially valuable if we reuse reference voices across requests.
**Risk**: Integration complexity. SGLang is a serving framework, not a drop-in replacement for torch.compile. Need to adapt our inference pipeline to SGLang's API. Single-user latency may not improve as much as throughput.
**Verdict**: **Try (high priority)** -- This is what Fish Audio themselves use in production. Largest expected single improvement.

---

## 2. Static KV Cache + CUDA Graphs for Autoregressive Decode

**Source**: [HuggingFace LLM inference optimization docs](https://huggingface.co/docs/transformers/en/llm_optims), [Compact Inference with CUDA Graph and StaticCache](https://xenshinu.github.io/cuda_graph/), [NVIDIA CUDA Graph Best Practices](https://docs.nvidia.com/dl-cuda-graph/latest/torch-cuda-graph/handling-dynamic-patterns.html), [Fireworks blog on CUDA graphs](https://fireworks.ai/blog/speed-python-pick-two-how-cuda-graphs-enable-fast-python-code-for-deep-learning)
**What**: Pre-allocate a fixed-size KV cache (StaticCache) instead of growing it dynamically. This enables CUDA graph capture of the decode step, eliminating Python/CPU kernel launch overhead. Pad inputs to bucketed sizes (e.g., 128, 256, 512) so CUDA graphs can be replayed without recapture. The decode step runs identically every iteration.
**Claimed impact**: 40-60% reduction in per-token decode latency vs eager mode on A100s. Fireworks reported 2.3x speedup on LLaMA-7B with CUDA graphs. The combination of torch.compile(mode="reduce-overhead") + StaticCache is described as "the highest-impact configuration for latency-sensitive single-request generation."
**Applicable to us?**: YES -- we already use torch.compile with reduce-overhead, but may not be using a StaticCache. The DualAR model's autoregressive decode loop is exactly the pattern that benefits most. Our Fish Speech code likely uses a dynamic cache.
**Risk**: Wastes some computation on masked-out positions in the static cache. Requires code changes to the KV cache implementation. Need to choose max cache size carefully -- too large wastes attention compute, too small truncates generation.
**Verdict**: **Try (high priority)** -- Likely gives 30-50% decode speedup on top of what we have. May already be partially in effect via reduce-overhead mode.

---

## 3. max-autotune Mode with Inductor Options

**Source**: [PyTorch torch.compile docs](https://docs.pytorch.org/docs/stable/generated/torch.compile.html), [Maximizing AI/ML Performance with PyTorch Compilation (Chaim Rand)](https://chaimrand.medium.com/maximizing-ai-ml-model-performance-with-pytorch-compilation-7cdf840202e6), [Autotuning in PyTorch & Triton (Ian Barber)](https://ianbarber.blog/2025/05/04/autotuning-in-pytorch-triton/), [vLLM torch.compile blog](https://blog.vllm.ai/2025/08/20/torch-compile.html)
**What**: Switch from reduce-overhead to max-autotune mode, or use granular inductor options. Key flags:
- `max_autotune`: Profiles multiple Triton kernel configs and matmul implementations (Triton vs cuBLAS)
- `epilogue_fusion`: Fuses pointwise ops into templates (requires max_autotune)
- `shape_padding`: Pads tensor shapes for better Tensor Core alignment
- `triton.cudagraphs`: Wraps compiled regions in CUDA graphs
- For models with dynamic + static parts, compile submodules separately: dynamic parts with `max-autotune-no-cudagraphs`, static parts with `max-autotune`
**Claimed impact**: max-autotune can be faster than reduce-overhead but takes much longer to compile. shape_padding improves Tensor Core utilization. epilogue_fusion reduces kernel count. Real-world gains of 15-60% for transformer inference depending on model/GPU.
**Applicable to us?**: MAYBE -- max-autotune profiles matmul variants, which matters for the attention layers. On the 5090 with its large SM count (`is_big_gpu` gate should pass), the autotuning should find good configs. However, if we move to SGLang, this becomes less relevant.
**Risk**: Much longer compilation time (minutes vs seconds). May not significantly improve over reduce-overhead if model isn't matmul-bottlenecked. Autotuning results are GPU-specific and cached.
**Verdict**: **Try (medium priority)** -- Quick experiment: `torch.compile(model, mode="max-autotune", fullgraph=True)`. Compare RTF vs reduce-overhead. If < 5% difference, stick with reduce-overhead.

---

## 4. FP8 W8A8 Quantization (Replace Current INT8 W8A16)

**Source**: [TensorRT-LLM quantization docs](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/blogs/quantization-in-TRT-LLM.md), [FP8 vs INT8 paper (arXiv 2303.17951)](https://ar5iv.labs.arxiv.org/html/2303.17951), [SGLang FP8 W8A16 issue](https://github.com/sgl-project/sglang/issues/3007), [vLLM FP8 performance issue](https://github.com/vllm-project/vllm/issues/16261)
**What**: Our current W8A16 (INT8 weights, FP16 activations) only reduces memory bandwidth for weight loading but still uses FP16 compute. W8A8 (FP8 weights + FP8 activations) enables the faster FP8 Tensor Cores for the actual matrix multiplication, potentially doubling compute throughput. The RTX 5090 has native FP8 support with 2nd-gen FP8 Transformer Engine.
**Claimed impact**: W8A8 FP8 provides 2.3x inference speedup over FP16 on H100 (LLaMA-7B, batch 16). For autoregressive decode at batch=1 (memory-bound), W8A16 is actually reasonable since the bottleneck is weight loading. But if we increase batch size at all, W8A8 dominates. FP8 is described as "lossless across all model scales."
**Applicable to us?**: MAYBE -- At batch=1 (single user), autoregressive decode is memory-bandwidth bound, and our current W8A16 already halves weight memory traffic. W8A8 would help more if we batched requests or if the prefill phase is significant. However, the RTX 5090's massive 1.79 TB/s bandwidth may shift the bottleneck toward compute, making W8A8 more valuable even at batch=1.
**Risk**: FP8 quantization requires re-quantizing the model with a calibration dataset. Quality impact should be minimal (<1% degradation on benchmarks). Need to ensure the quantization library supports Fish Speech's architecture.
**Verdict**: **Investigate further** -- Profile whether decode is memory-bound or compute-bound on the 5090. If compute-bound, W8A8 FP8 could be a significant win.

---

## 5. NVFP4 Quantization (Blackwell-Native)

**Source**: [NVIDIA TensorRT FP4 blog](https://developer.nvidia.com/blog/nvidia-tensorrt-unlocks-fp4-image-generation-for-nvidia-blackwell-geforce-rtx-50-series-gpus/), [FP4 Quantization on Blackwell (Spheron)](https://www.spheron.network/blog/fp4-quantization-blackwell-gpu-cost/), [RTX 5090 NVFP4 testing (Zenn)](https://zenn.dev/toki_mwc/articles/rtx5090-nvfp4-quantization-reality?locale=en), [Quartet FP4 training paper](https://arxiv.org/html/2505.14669v1)
**What**: NVFP4 uses 4-bit floating point with dual-level scaling (FP8 micro-blocks + FP32 tensor scale). Blackwell's Tensor Cores natively accelerate FP4 operations, achieving ~2x throughput over FP8 and ~3.1x for FC layers in optimized pipelines. VRAM usage drops to roughly half of FP8.
**Claimed impact**: 1.9-2x faster than FP8 inference. FC layers specifically up to 3.1x faster. Less than 1% accuracy loss on standard LLM benchmarks. VRAM could drop from 9.2GB to ~5-6GB.
**Applicable to us?**: MAYBE -- TTS audio quality is more sensitive than LLM text quality. One report showed FP4 loses pixel-level features in image generation that QAD distillation couldn't recover. Speech quality degradation at FP4 is an open question. PyTorch native FP4 support is still maturing -- most FP4 deployment uses TensorRT-LLM.
**Risk**: Speech quality degradation. "Software support is basically nonexistent" for end-users as of early 2026. Would need TensorRT-LLM integration, which is a significant engineering effort. The Fish Speech architecture uses custom layers that may not map cleanly to TensorRT.
**Verdict**: **Skip for now** -- Wait for PyTorch native FP4 support to mature. Revisit when torchao or SGLang adds FP4 support. Audio quality risk too high without careful evaluation.

---

## 6. KV Cache Quantization (INT8/FP8)

**Source**: [GPU-Accelerated INT8 KV Cache (arXiv 2601.04719)](https://arxiv.org/html/2601.04719v1), [NVIDIA NVFP4 KV Cache blog](https://developer.nvidia.com/blog/optimizing-inference-for-long-context-and-large-batch-sizes-with-nvfp4-kv-cache/), [vLLM FP8 KV Cache docs](https://docs.vllm.ai/en/latest/features/quantization/quantized_kvcache/), [HuggingFace KV cache quantization blog](https://huggingface.co/blog/kv-cache-quantization)
**What**: Quantize the KV cache tensors to INT8 or FP8 instead of storing them in FP16/BF16. This reduces KV cache memory by 2-4x and reduces memory bandwidth during attention computation. vLLM supports per-tensor and per-attention-head FP8 KV cache quantization. INT8 KV cache achieves ~4x memory reduction with reconstruction error below 0.004.
**Claimed impact**: 2-4x KV cache memory reduction. Enables longer context windows or larger batch sizes. Negligible accuracy loss. For TTS with short sequences (~500-2000 tokens), the absolute memory savings are modest but the bandwidth reduction helps decode speed.
**Applicable to us?**: MAYBE -- Our sequences are relatively short (TTS), so KV cache isn't the primary memory hog. But the bandwidth reduction during attention could improve decode latency. More impactful if we batch multiple requests. If using SGLang, this may come for free.
**Risk**: Low risk -- FP8 KV cache is well-tested in production LLM serving. Need to verify that Fish Speech's attention implementation supports quantized KV cache.
**Verdict**: **Investigate further** -- Low-hanging fruit if SGLang supports it natively for our model. Otherwise, manual integration effort may not justify modest gains for single-user TTS.

---

## 7. Speculative Decoding for TTS (VADUSA)

**Source**: [VADUSA paper (arXiv 2410.21951)](https://arxiv.org/abs/2410.21951v2), [Accelerating Codec-based Speech Synthesis (arXiv 2410.13839)](https://arxiv.org/html/2410.13839v1), [Speech Speculative Decoding (arXiv 2505.15380)](https://arxiv.org/html/2505.15380)
**What**: VADUSA applies MEDUSA-style speculative decoding to autoregressive TTS. Multiple draft heads predict future speech tokens in parallel, then a tolerance mechanism verifies and accepts good predictions. This avoids the sequential one-token-at-a-time bottleneck. A related paper uses 8 prediction heads for multi-token prediction, achieving 4-5x acceleration.
**Claimed impact**: Up to 5x faster than baseline autoregressive TTS (VADUSA). 4-5x with multi-token prediction. Quality actually improves because selecting from multiple candidates reduces collapse probability. Content consistency improves (WER decreases).
**Applicable to us?**: YES but requires research -- Fish Speech's Dual-AR architecture is different from VALL-E. The Slow AR predicts one codebook token at a time, which is the bottleneck. Adding MEDUSA-style draft heads to the Slow AR could work since it's a standard transformer. The Fast AR already generates multiple codebooks per step, so that's less relevant.
**Risk**: Requires training additional draft head parameters. The Slow AR may have different token prediction characteristics than text LLMs (speech tokens may be harder to speculate). Integration with the Dual-AR pipeline needs care. Significant engineering and training effort.
**Verdict**: **Investigate further (long-term)** -- High potential (2-5x speedup) but requires training new components. Worth prototyping with a simple 1-head draft on the Slow AR to measure acceptance rate.

---

## 8. DAC Decoder Optimization

**Source**: [DAC GitHub repo](https://github.com/descriptinc/descript-audio-codec), [DAC-JAX paper (arXiv 2405.11554)](https://arxiv.org/abs/2405.11554), [DAC HuggingFace docs](https://huggingface.co/docs/transformers/en/model_doc/dac), [NVIDIA TTS deployment with TensorRT blog](https://developer.nvidia.com/blog/how-to-deploy-real-time-text-to-speech-applications-on-gpus-using-tensorrt/)
**What**: The DAC decoder is a convolutional neural network that converts quantized tokens back to audio waveforms. Multiple optimization paths exist:
1. **torch.compile the DAC decoder separately** -- it's a standard nn.Module with no dynamic shapes (fixed token count -> fixed audio length)
2. **ONNX/TensorRT export** -- DAC's convolutional architecture is very TensorRT-friendly. NVIDIA showed 13x speedup for audio model inference via TensorRT on T4.
3. **DAC-JAX** -- JAX JIT compilation outperforms PyTorch DAC at all chunk sizes on consumer GPUs
4. **FP16/BF16 mixed precision** -- if not already applied to the decoder
**Claimed impact**: DAC-JAX outperforms original DAC at all chunk sizes on consumer GPU. TensorRT achieves 6.2x RTF (13x faster than CPU) for similar audio models. torch.compile should provide significant gains since DAC has purely static shapes (no autoregressive component).
**Applicable to us?**: YES -- The DAC decoder is the other half of our inference pipeline. Since it has static shapes and is purely convolutional, it's an ideal torch.compile or TensorRT target. We may not be compiling it currently.
**Risk**: Low for torch.compile (already using it for the transformer). TensorRT export requires more effort and testing. ONNX export for DAC has known challenges with weight normalization layers.
**Verdict**: **Try (high priority)** -- First ensure DAC decoder is separately compiled with torch.compile(mode="max-autotune", fullgraph=True). It should compile cleanly with static shapes. Profile to see what fraction of total inference time is DAC decode.

---

## 9. Triton/SM120 Compatibility Issues on Blackwell

**Source**: [PyTorch forum: sm_120 error on RTX 5070 Ti](https://discuss.pytorch.org/t/rtx-5070-ti-blackwell-pytorch-nightly-triton-still-getting-sm-120-is-not-defined-for-option-gpu-name-error/220460), [PyTorch issue #164342: sm_120 support](https://github.com/pytorch/pytorch/issues/164342), [WSL2 setup guide for RTX 5090](https://medium.com/@getnetdemil/getting-pytorch-to-actually-use-your-rtx-5090-a-complete-wsl2-setup-guide-for-blackwell-sm-120-61f86f64abc4), [Fish Speech issue #966: 5060Ti](https://github.com/fishaudio/fish-speech/issues/966)
**What**: Stable PyTorch (as of early 2026) does not officially support sm_120 (Blackwell). Users on RTX 50-series GPUs encounter "Value 'sm_120' is not defined for option 'gpu-name'" errors with Triton/torch.compile. The Fish Speech repo has issue #966 reporting this exact error on RTX 5060 Ti. Workarounds: PyTorch nightly with CUDA 12.8+, or build from source with TORCH_CUDA_ARCH_LIST="sm_120".
**Claimed impact**: Without proper sm_120 support, torch.compile falls back to slower code paths or fails entirely. Fish Speech issue #971 reports --compile actually making inference slower (29 seconds vs 2 seconds expected), possibly related to recompilation loops on unsupported architectures.
**Applicable to us?**: YES -- we're on RTX 5090 (sm_120) with PyTorch 2.8.0+cu128. We may be hitting this issue. If torch.compile is silently falling back or recompiling constantly, our RTF 0.263x may be suboptimal.
**Risk**: Using nightly PyTorch introduces instability. Building from source is time-consuming but gives most control. CUDA 12.8 may be sufficient but 12.9 is recommended.
**Verdict**: **Try (high priority)** -- Verify our torch.compile is actually working correctly on sm_120. Check for Triton compilation warnings/errors in logs. If hitting issues, upgrade to PyTorch nightly with CUDA 12.9. This could explain surprisingly poor compile performance.

---

## 10. s2.cpp / GGUF Quantization

**Source**: [s2-pro GGUF on HuggingFace (mach9243)](https://huggingface.co/mach9243/s2-pro-gguf), [s2-pro GGUF (rodrigomt)](https://huggingface.co/rodrigomt/s2-pro-gguf), [Fish Speech S2 overview (emelia.io)](https://emelia.io/hub/fish-speech-s2-tts)
**What**: Community-built GGUF quantizations of S2-Pro running via s2.cpp (llama.cpp-based). Available in F16, Q8_0 (7GB VRAM), and Q4_K_M (4GB VRAM). The RTX 3090 achieves RTF 1.3 with GGUF models. This is a completely different inference stack from PyTorch.
**Claimed impact**: Dramatic VRAM reduction: 21GB (original) -> 12GB (F16 GGUF) -> 7GB (Q8) -> 4GB (Q4). RTX 3090 RTF 1.3 with GGUF. No RTX 5090 benchmarks yet.
**Applicable to us?**: MAYBE -- We already have 9.2GB VRAM usage with INT8 quantization in PyTorch, so VRAM isn't our bottleneck. The question is whether s2.cpp/llama.cpp inference is faster than our PyTorch path on the 5090. llama.cpp is highly optimized for autoregressive decode but may not leverage all Blackwell features.
**Risk**: Different inference stack entirely. May not support all Fish Speech features. Quality may differ from PyTorch path. llama.cpp Blackwell support is also evolving.
**Verdict**: **Investigate further** -- Benchmark s2.cpp Q8 on the 5090 vs our current PyTorch setup. If it's faster, consider hybrid: s2.cpp for the transformer, PyTorch for DAC decoder.

---

## 11. fish-speech.rs (Rust/Candle Implementation)

**Source**: [fish-speech.rs GitHub](https://github.com/EndlessReform/fish-speech.rs), [fish-speech-rs on PyPI](https://pypi.org/project/fish-speech-rs/)
**What**: Pure Rust implementation of Fish Speech 1.5 inference using HuggingFace's Candle framework. Compiles to a 15MB static binary. Supports NVIDIA (CUDA), Apple Silicon (Metal), and CPU. Eliminates Python overhead entirely.
**Claimed impact**: No Python GIL or dispatch overhead. Rust ML inference can be 3-5x faster than Python for overhead-dominated workloads. However, the developer notes that on RTX 4090, "the bottleneck is actually elsewhere (in inefficient memory copies and kernel dispatch), so Flash Attention currently has less impact."
**Applicable to us?**: NO -- Only supports Fish Speech 1.5 and below, not S2-Pro. The Dual-AR architecture of S2-Pro is significantly different. Would need a complete rewrite for S2-Pro support.
**Risk**: N/A (not applicable to S2-Pro).
**Verdict**: **Skip** -- Architecture mismatch. Interesting for future reference if someone ports S2-Pro to Candle/Rust.

---

## 12. W8A16 vs W8A8 for Memory-Bound Decode

**Source**: [TensorRT-LLM quantization blog](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/blogs/quantization-in-TRT-LLM.md), [AWS blog on AWQ/GPTQ](https://aws.amazon.com/blogs/machine-learning/accelerating-llm-inference-with-post-training-weight-and-activation-using-awq-and-gptq-on-amazon-sagemaker-ai/)
**What**: Important nuance: for small-batch autoregressive decode (batch=1), inference is memory-bandwidth bound, not compute-bound. This means W8A16 (weight-only quantization) is actually the correct choice because the bottleneck is fetching weights from memory, and W8A16 halves that traffic. W8A8 adds the overhead of quantizing activations on-the-fly with no benefit when compute isn't the bottleneck.
**Claimed impact**: TensorRT-LLM docs explicitly rate W8A16 as "Low" speedup and W8A8 as "Medium" speedup. But for batch=1 decode, W8A16 can match or exceed W8A8 because activation quantization overhead isn't recovered. The crossover happens around batch=4-8 where compute becomes the bottleneck.
**Applicable to us?**: YES -- This validates our current W8A16 approach for single-user inference. Our RTX 5090 has 1.79 TB/s bandwidth, which may shift the crossover point, but for batch=1 TTS, W8A16 is likely optimal.
**Risk**: None -- this is confirming our current approach is sound.
**Verdict**: **Keep current approach** -- W8A16 is correct for batch=1 memory-bound decode. Only switch to W8A8 if we add batching.

---

## 13. Prefix Caching for Voice Cloning (RadixAttention)

**Source**: [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v2), [SGLang GitHub](https://github.com/sgl-project/sglang)
**What**: When the same reference voice is used across multiple TTS requests, the KV cache for the reference audio encoding is identical. RadixAttention (in SGLang) uses a radix tree to detect and reuse these shared prefixes. Fish Audio reports 86.4% average prefix-cache hit rate in production, with peaks over 90%.
**Claimed impact**: Skips the reference-audio prefill stage entirely on cache hit. Makes "prompt-processing overhead nearly negligible." For a system that primarily uses one or a few voices, this means the first request pays full cost but subsequent requests are dramatically faster.
**Applicable to us?**: YES -- If we're using the same voice reference repeatedly (likely for a personal TTS system), prefix caching would eliminate redundant computation on every request after the first.
**Risk**: Requires SGLang integration (see item #1). Memory cost of caching KV states. Only helps if voices are reused.
**Verdict**: **Try (bundled with SGLang migration)** -- This comes free with SGLang and could be a major win for our use case.

---

## 14. Streaming with Chunked Audio Emission

**Source**: [Fish Speech issue #1020: First chunk latency](https://github.com/fishaudio/fish-speech/issues/1020), [L3Speech (ICLR 2025)](https://openreview.net/forum?id=RK3Gj9J5my), [SpeakStream (Bai et al.)](https://www.emergentmind.com/topics/streaming-speech-decoder), [TTS-1 Technical Report](https://arxiv.org/html/2507.21138v1)
**What**: Instead of generating all audio tokens then decoding, overlap token generation with DAC decoding. Emit audio chunks as soon as enough tokens are generated. SpeakStream achieves 42ms first-token latency. TTS-1 achieves 70% faster first-audio delivery vs vanilla vLLM. Fish Speech issue #1020 reports that first-chunk latency increases linearly with text length due to blocking on response_queue.get().
**Claimed impact**: SpeakStream: 42ms first-token latency. TTS-1: 70% faster time-to-first-audio. Reduces perceived latency without improving total generation time.
**Applicable to us?**: YES -- If we care about time-to-first-audio (e.g., for interactive/conversational use), streaming token generation + chunked DAC decoding can dramatically reduce perceived latency. Issue #1020 confirms this is a real problem in Fish Speech.
**Risk**: Chunked DAC decoding may produce artifacts at chunk boundaries. Need overlap-add or similar smoothing. Implementation complexity in the inference pipeline.
**Verdict**: **Try (medium priority)** -- Most impactful for interactive use cases. Profile our current time-to-first-audio and determine if it's a bottleneck.

---

## 15. RTX 5090 Specific: Memory Bandwidth Advantage

**Source**: [RunPod RTX 5090 review](https://www.runpod.io/articles/guides/nvidia-rtx-5090), [Jarvis Labs RTX 5090 specs](https://jarvislabs.ai/ai-faqs/nvidia-rtx-5090-specs), [NVIDIA Blackwell architecture whitepaper](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf)
**What**: RTX 5090 has 1.79 TB/s memory bandwidth (78% more than 4090's ~1 TB/s) and 96MB L2 cache. For memory-bandwidth-bound autoregressive decode, this directly translates to faster token generation. The large L2 cache (96MB vs 72MB on 4090) means more model weights and KV cache can stay in fast cache.
**Claimed impact**: 1.5-1.8x inference speedup for bandwidth-bound workloads vs RTX 4090. With 32GB VRAM, can fit the full S2-Pro model without any quantization (21GB), leaving room for KV cache and activations.
**Applicable to us?**: YES -- We're already benefiting from this. Our RTF 0.263x is likely already leveraging the bandwidth. But we should ensure we're not leaving performance on the table by:
1. Using CUDA 12.8+ for Blackwell-optimized memory access patterns
2. Ensuring our model weights are in contiguous memory
3. Using pinned memory for CPU-GPU transfers
**Risk**: None -- hardware feature we already have.
**Verdict**: **Verify** -- Ensure we're actually hitting peak bandwidth. Profile with nvidia-smi or Nsight to check memory bandwidth utilization.

---

## 16. torch.compile Pitfalls: Fish Speech-Specific Issues

**Source**: [Fish Speech issue #971: --compile slows inference](https://github.com/fishaudio/fish-speech/issues/971), [Fish Speech issue #860: --compile crash](https://github.com/fishaudio/fish-speech/issues/860), [Fish Speech issue #966: 5060Ti sm_120 error](https://github.com/fishaudio/fish-speech/issues/966)
**What**: Multiple Fish Speech users report that --compile actually makes inference SLOWER (29 seconds vs expected 2 seconds). Issue #860 reports crashes from deprecated torch.cuda.amp.autocast usage. Issue #966 confirms Triton doesn't recognize sm_120 on Blackwell GPUs. These issues suggest torch.compile may not be functioning correctly in the current Fish Speech codebase for Blackwell GPUs.
**Claimed impact**: Compile can make inference 15x slower if it hits recompilation loops. Crashes on some GPU/driver combinations.
**Applicable to us?**: YES (CRITICAL) -- If we're hitting these issues, our current RTF 0.263x may include significant torch.compile overhead. The 29-second-per-iteration report suggests constant recompilation, possibly triggered by dynamic shapes in the DualAR pipeline.
**Risk**: We may be running in a degraded state right now.
**Verdict**: **Investigate immediately** -- Check torch.compile logs for graph breaks, recompilation warnings, and Triton sm_120 errors. If compile is broken, fixing it or removing it could improve performance significantly.

---

## 17. Regional Compilation for Large Models

**Source**: [vLLM torch.compile integration](https://docs.vllm.ai/en/latest/design/torch_compile/), [PyTorch compilation FAQ](https://docs.pytorch.org/docs/stable/torch.compiler_faq.html)
**What**: For models with many identical layers (like our 36-layer DualAR transformer), compiling the full model means Dynamo inlines and unrolls every layer -- compile time scales linearly with depth. Instead, compile individual transformer blocks (or a single block template) to reduce compile time while maintaining the same runtime performance.
**Claimed impact**: Dramatically reduces compilation time. Same runtime performance since all blocks are identical. vLLM uses this approach internally.
**Applicable to us?**: MAYBE -- If our compile time is long (it shouldn't be with just 36 layers), regional compilation could help. More relevant if we're experiencing compile time issues or memory issues during compilation.
**Risk**: Minimal -- this is how production systems like vLLM do it.
**Verdict**: **Try if compile time is an issue** -- Profile compilation time. If > 60 seconds, switch to regional compilation of individual transformer blocks.

---

## 18. CUDA Memory Best Practices

**Source**: [PyTorch memory tuning (Paul Bridger)](https://paulbridger.com/posts/pytorch-memory-tuning/), [PyTorch memory optimization (torchtune)](https://docs.pytorch.org/torchtune/0.5/tutorials/memory_optimizations.html)
**What**: Several practical memory optimizations:
1. `torch.inference_mode()` -- completely disables activation storage (more aggressive than no_grad)
2. `torch.cuda.empty_cache()` between tasks to prevent fragmentation
3. Profile peak memory with `torch.cuda.max_memory_allocated()` not nvidia-smi
4. CUDA memory allocator config: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` reduces fragmentation
5. Memory-mapped weights for faster model loading
**Claimed impact**: inference_mode() vs no_grad() can save additional memory. Fragmentation reduction can prevent OOM on long-running servers.
**Applicable to us?**: YES -- Quick checks: Are we using inference_mode() or just no_grad()? Are we setting expandable_segments? These are free wins.
**Risk**: None.
**Verdict**: **Try (quick wins)** -- Audit our inference code for these patterns. 5-minute fix for potential memory savings.

---

## 19. Fish Speech S2-Pro Quantization Request (Community Demand)

**Source**: [Fish Speech issue #1168: Quantization or Optimization for S2-Pro](https://github.com/fishaudio/fish-speech/issues/1168)
**What**: As of March 2026, the community has filed a request for official quantization support for S2-Pro. Contributors are interested in helping. This suggests that quantization beyond the basic --half flag is not yet officially supported or well-tested.
**Claimed impact**: N/A -- this is a feature request, not an implementation.
**Applicable to us?**: YES -- We're already doing INT8 W8A16 quantization, which is ahead of what the community has. We should monitor this issue for official quantization support and potentially contribute our findings.
**Risk**: Our custom quantization may diverge from future official support.
**Verdict**: **Monitor** -- Watch this issue for official quantization work. Consider contributing our INT8 quantization implementation.

---

## 20. Attention-Free / Alternative Decoder Architectures

**Source**: [Latency-Aware TTS Pipeline topic (Emergent Mind)](https://www.emergentmind.com/topics/latency-aware-text-to-speech-tts-pipeline)
**What**: Some recent TTS systems replace global attention in the decoder with ConvNeXt blocks or per-token flow modules (Flamed-TTS, CLEAR). This enables block-parallel operations and constant per-frame latency, avoiding the O(n^2) attention cost.
**Claimed impact**: Constant per-frame latency vs growing latency with sequence length. Better suited for streaming.
**Applicable to us?**: NO -- We can't change the S2-Pro model architecture without retraining from scratch. This is a design consideration for future models, not an optimization for our current setup.
**Risk**: N/A.
**Verdict**: **Skip** -- Architecture is fixed. Interesting for future model development only.

---

# Priority Summary

## Immediate Actions (This Week)
1. **Verify torch.compile is working on SM120** (#9, #16) -- Check for recompilation loops, Triton errors
2. **Profile DAC decoder separately** (#8) -- Determine what fraction of time is DAC vs transformer
3. **Audit inference code for quick wins** (#18) -- inference_mode(), expandable_segments, empty_cache()

## High Priority (Next 2 Weeks)
4. **SGLang integration** (#1, #13) -- The biggest single expected improvement. Start with basic SGLang serving, then enable prefix caching.
5. **Static KV Cache + CUDA graphs** (#2) -- If staying with torch.compile path, implement StaticCache
6. **torch.compile DAC decoder with max-autotune** (#8) -- Static shapes = ideal compile target

## Medium Priority (Next Month)
7. **max-autotune vs reduce-overhead benchmark** (#3) -- Quick A/B test
8. **Streaming/chunked audio emission** (#14) -- If time-to-first-audio matters
9. **Profile bandwidth utilization** (#15) -- Ensure we're hitting peak 5090 bandwidth

## Long-Term / Research
10. **Speculative decoding for Slow AR** (#7) -- Train draft heads, measure acceptance rate
11. **FP8 W8A8 quantization** (#4) -- Only if profiling shows compute bottleneck
12. **s2.cpp benchmark on 5090** (#10) -- Compare alternative inference stacks
13. **NVFP4** (#5) -- Wait for ecosystem maturity

## Confirmed Good (Keep Current Approach)
- **INT8 W8A16 quantization** (#12) -- Correct for batch=1 memory-bound decode
- **torch.compile reduce-overhead** -- Good default, but verify it's actually compiling

---

# Key Sources

- [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v2)
- [Fish Speech GitHub](https://github.com/fishaudio/fish-speech)
- [Fish Speech Issue #971: --compile slows inference](https://github.com/fishaudio/fish-speech/issues/971)
- [Fish Speech Issue #1168: S2-Pro quantization request](https://github.com/fishaudio/fish-speech/issues/1168)
- [Fish Speech Issue #966: RTX 5060Ti sm_120 error](https://github.com/fishaudio/fish-speech/issues/966)
- [SGLang GitHub](https://github.com/sgl-project/sglang)
- [VADUSA: Speculative Decoding for TTS](https://arxiv.org/abs/2410.21951v2)
- [DAC GitHub](https://github.com/descriptinc/descript-audio-codec)
- [DAC-JAX](https://arxiv.org/abs/2405.11554)
- [PyTorch torch.compile docs](https://docs.pytorch.org/docs/stable/generated/torch.compile.html)
- [NVIDIA CUDA Graph Best Practices](https://docs.nvidia.com/dl-cuda-graph/latest/torch-cuda-graph/handling-dynamic-patterns.html)
- [HuggingFace LLM Inference Optimization](https://huggingface.co/docs/transformers/en/llm_optims)
- [vLLM torch.compile integration](https://blog.vllm.ai/2025/08/20/torch-compile.html)
- [KV Cache Quantization blog](https://huggingface.co/blog/kv-cache-quantization)
- [TensorRT-LLM Quantization](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/blogs/quantization-in-TRT-LLM.md)
- [RunPod RTX 5090 Review](https://www.runpod.io/articles/guides/nvidia-rtx-5090)
- [s2-pro GGUF](https://huggingface.co/mach9243/s2-pro-gguf)
- [fish-speech.rs](https://github.com/EndlessReform/fish-speech.rs)
- [PyTorch SM120 Support Issue](https://github.com/pytorch/pytorch/issues/164342)
- [WSL2 RTX 5090 Setup Guide](https://medium.com/@getnetdemil/getting-pytorch-to-actually-use-your-rtx-5090-a-complete-wsl2-setup-guide-for-blackwell-sm-120-61f86f64abc4)
- [NVIDIA Blackwell Architecture Whitepaper](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf)
