# Research: Incremental/Streaming DAC Decoder for Sub-Chunk Audio

## Architecture

### Full Decode Pipeline: VQ Tokens to Audio

The decode path is `DAC.from_indices(indices)` which calls:

```
indices [B, 10, T_vq]
  -> quantizer.decode(indices)           # rvq.py:352
      -> semantic_quantizer.from_codes() # codebook lookup (pointwise)
      -> quantizer.from_codes()          # codebook lookup (pointwise)
      -> z_q = semantic + residual       # sum (pointwise)
      -> post_module(z_q)                # WindowLimitedTransformer(causal, window=128, 8 layers)
      -> upsample(z_q)                   # 2 stages: CausalTransConv(k=2,s=2) + ConvNeXtBlock(k=7)
      -> z_q [B, 1024, T_vq * 4]        # 4x upsample from quantizer
  -> decoder(z)                          # modded_dac.py:800
      -> CausalConv1d(1024, 1536, k=7)
      -> DecoderBlock(1536->768, stride=8)   # trans_conv + 3 ResUnits (d=1,3,9)
      -> DecoderBlock(768->384, stride=8)    # trans_conv + 3 ResUnits (d=1,3,9)
      -> DecoderBlock(384->192, stride=4)    # trans_conv + 3 ResUnits (d=1,3,9)
      -> DecoderBlock(192->96, stride=2)     # trans_conv + 3 ResUnits (d=1,3,9)
      -> CausalConv1d(96, 1, k=7)
      -> Tanh()
      -> audio [B, 1, T_vq * 2048]      # 512x upsample from decoder
```

**Total upsample**: 4 (quantizer) x 512 (decoder) = **2048x**. One VQ token = 2048 audio samples = ~46.4ms at 44.1kHz. Token rate = ~21.53 Hz.

### Decoder Layer Types

The decoder is **purely convolutional** (no RNNs, no hidden state between calls):

| Layer Type | Count | Purpose |
|-----------|-------|---------|
| `CausalConvNet` (Conv1d with left-padding) | ~26 | Strided/dilated causal convolutions |
| `CausalTransConvNet` (ConvTranspose1d with trimming) | 4+2 | Upsampling (decoder: 4 blocks, quantizer: 2 stages) |
| `Snake1d` | ~20 | Activation function (pointwise, no temporal deps) |
| `ConvNeXtBlock` | 2 | In quantizer upsample (depthwise causal conv + FFN) |
| `WindowLimitedTransformer` | 1 | In quantizer post_module (causal, window=128, 8 layers) |

**Note**: The `DecoderBlock` code has `transformer_module` commented out on line 742, so despite the config specifying `decoder_transformer_layers: [4, 0, 0, 0]`, the decoder has **zero transformer layers**. The only transformer is in the quantizer's `post_module`.

### What `causal=True` Means Architecturally

Every convolution in the network uses `CausalConvNet`, which applies **left-only padding**:

```python
# CausalConvNet.forward():
pad = self.padding  # = effective_kernel_size - stride
x = pad1d(x, (pad, extra_padding), mode="constant", value=0)  # LEFT pad only
return self.conv(x)
```

For transposed convolutions (`CausalTransConvNet`), the output is **right-trimmed**:

```python
# CausalTransConvNet.forward():
x = self.conv(x)           # standard transposed conv
pad = kernel_size - stride
padding_right = ceil(pad)
padding_left = pad - padding_right
x = unpad1d(x, (padding_left, padding_right))  # trim excess
```

The `WindowLimitedTransformer` in the quantizer uses a **causal mask** (lower-triangular) with window size 128:

```python
# WindowLimitedTransformer.make_window_limited_mask():
mask = torch.tril(torch.ones(max_length, max_length))  # causal
# Then restricts to window: column_indices >= (row - window_size + 1)
```

**Result**: Output at time `t` depends **only** on inputs at times `max(0, t - RF)` through `t`. There is **zero lookahead** -- no future tokens are needed.

### Decoder Receptive Field

Computed by propagating dependencies backwards through the network:

| Stage | RF at this resolution | Notes |
|-------|----------------------|-------|
| Audio output | 0 | Starting point |
| Final CausalConv1d (k=7) | 6 audio samples | |
| DecoderBlock 4 ResUnits (d=1,3,9) | 84 audio samples | 6+18+54+6 |
| DecoderBlock 4 TransConv (s=2) | ~43 at rate/2 | Resolution change |
| DecoderBlock 3 ResUnits + TransConv | ~32 at rate/8 | |
| DecoderBlock 2 ResUnits + TransConv | ~15 at rate/64 | |
| DecoderBlock 1 ResUnits + TransConv | ~13 at rate/512 | |
| Initial CausalConv1d (k=7) | ~19 latent samples | |
| Quantizer upsample (2 stages) | ~10 VQ tokens | ConvNeXt + TransConv |
| **Quantizer transformer (window=128)** | **~137 VQ tokens** | Dominates RF |

The **WindowLimitedTransformer with window_size=128** is the dominant factor. It means each output position in the quantizer depends on up to 128 past VQ tokens (128 * 46.4ms = ~5.9s of audio context).

### Causality Verification

The `rvq.py` test at the bottom of the file provides a direct proof of causality:

```python
result = rvq(x)               # encode full sequence (442 frames)
result1 = rvq(x[:, :, :40])   # encode prefix (40 frames)
assert torch.allclose(result.z[:, :, :40], result1.z, atol=1e-8)
```

This confirms: encoding/decoding a prefix produces **identical** results to encoding the full sequence and taking the prefix. This is the fundamental property enabling incremental decoding.

### Statelessness

The decoder is entirely **stateless** -- it's a `nn.Sequential` stack of convolutional layers with no hidden state, no recurrence, and no state that persists between calls. The transformer in the quantizer also has no persistent state in inference mode (it computes attention from scratch each call; its KV cache infrastructure exists but is only used during training/different inference modes).

## Feasibility

### Can We Decode Partial Token Sequences?

**Yes, absolutely.** Since every layer is causal:

1. Decode tokens `[0..N]` -> audio `[0..N*2048]`
2. Decode tokens `[0..N+M]` -> audio `[0...(N+M)*2048]`
3. Audio samples `[0..N*2048]` are **identical** in both cases

This means we can decode incrementally and concatenate the new audio without any boundary artifacts at the junction point. The causal property guarantees that previously decoded audio is not affected by future tokens.

### Minimum Token Count for Valid Output

There is no hard minimum. Even 1 token can be decoded. However, output **quality** depends on context:

- **Tokens 0-9** (~10 tokens): The convolutional receptive field of the decoder proper (~10 VQ tokens) is not fully satisfied. Output will be slightly different from what you'd get with more context, but only due to the zero-padding at the left edge. This is identical to the start of any sequence -- it's not a streaming-specific artifact.
- **Tokens 0-127**: The transformer window (128 tokens) doesn't have full context. Each position attends to all available past tokens (up to 128). Quality gradually improves as more context accumulates.
- **Tokens 128+**: Full receptive field is available. Output is identical to batch decoding.

**Key insight**: The quality at the start of a sequence is **the same whether decoded incrementally or in batch**. Both see zero context at position 0, partial context up to position 127, and full context beyond 128. There is no streaming penalty.

### Boundary Artifacts Between Partial Decodes

**There are none**, provided we use the correct approach. Since the decoder is causal and stateless:

- Decoding `[0..49]` produces audio `A[0..49*2048]`
- Decoding `[0..99]` produces audio `A[0..99*2048]`
- `A[0..49*2048]` is identical in both cases

So we simply: decode `[0..49]`, emit audio `[0..49*2048]`, then decode `[0..99]` and emit only `[49*2048..99*2048]` (the new audio). No crossfading or overlap-add is needed at the sub-chunk boundary because the audio is bit-identical.

### GPU Memory Leak Consideration

GitHub issue #1025 reports a GPU memory leak of ~10-20 MiB per DAC decode call when using `modded_dac_vq` with streaming. This is relevant because incremental decoding increases the number of decode calls. This will need investigation and mitigation (likely PyTorch CUDA allocator behavior or unreleased intermediate tensors).

## Approach Options

### Approach A: Grow-and-Redecode (Simplest, Recommended for MVP)

**Mechanism**: Maintain a growing buffer of all VQ tokens generated so far. Every N new tokens, decode the **entire buffer** and emit only the new audio samples.

```python
all_codes = []        # accumulates all VQ tokens
prev_audio_len = 0    # samples already emitted

for partial_codes in generate_tokens():
    all_codes.append(partial_codes)
    full_codes = torch.cat(all_codes, dim=-1)  # [10, T_total]
    
    audio = dac.from_indices(full_codes[None])  # [1, 1, T_total * 2048]
    new_audio = audio[..., prev_audio_len:]     # only new samples
    prev_audio_len = audio.shape[-1]
    
    yield new_audio
```

| Property | Value |
|----------|-------|
| Correctness | Bit-identical to batch decode |
| Boundary artifacts | None |
| Compute cost | O(T^2) total -- redecodes everything |
| Implementation complexity | Trivial |
| Memory | Stores all tokens + full audio each call |

**Overhead estimate for typical 5s utterance (~107 tokens, decode every 10 tokens):**
- 10 decode calls, total tokens decoded: 10+20+30+...+107 = ~550 (5.1x single decode)
- But each decode is ~15-25ms, so total extra decode time: ~100-200ms spread over the whole utterance
- Completely acceptable for an MVP

### Approach B: Sliding Window Decode (Balanced)

**Mechanism**: Keep a sliding window of the last W tokens. Decode only `[max(0, T-W)..T]`, emit audio for the newest N tokens only.

```python
WINDOW = 128  # match transformer RF
all_codes = []
prev_audio_len = 0

for partial_codes in generate_tokens():
    all_codes.append(partial_codes)
    full_codes = torch.cat(all_codes, dim=-1)
    
    # Decode only the window
    start = max(0, full_codes.shape[-1] - WINDOW)
    window_codes = full_codes[:, start:]
    
    audio = dac.from_indices(window_codes[None])
    # Extract only the new audio (at the end of the window)
    new_samples = N * 2048  # N new tokens worth
    new_audio = audio[..., -new_samples:]
    
    yield new_audio
```

| Property | Value |
|----------|-------|
| Correctness | Identical to batch for positions >= 128 from start |
| Boundary artifacts | None (causal property) |
| Compute cost | O(T) total -- fixed window per decode |
| Implementation complexity | Low |
| Memory | Fixed window buffer |

**Caveat**: For the first ~128 tokens, the sliding window and full-sequence approaches produce identical results (window >= available tokens). After 128 tokens, the sliding window output will differ **slightly** from batch decode for the earliest positions in the window, because the transformer doesn't see tokens before the window start. However, since we only emit the newest N tokens' audio, and those positions have full window context, the output is correct.

**Wait -- this needs more careful analysis.** The transformer at position `t` within a window starting at `s` will attend to tokens `[s..t]`. In full-sequence decode, it would attend to `[max(0, t-127)..t]`. If `s <= t - 127`, these are identical. If `s > t - 127` (which happens when `t < s + 128`, i.e., all positions in the window), these are identical because `s = max(0, T - W)` and we're looking at the tail. So the newest N tokens always have full context. **This approach is correct.**

### Approach C: Cached Convolution (Optimal, Complex)

**Mechanism**: Maintain per-layer activation caches. When new tokens arrive, only compute the forward pass for the new tokens, using cached activations as left-context.

This is the approach used by IRCAM's `cached_conv` library and is conceptually how SoundStream achieves real-time streaming. Each `CausalConvNet` layer needs a cache of its last `(kernel_size - 1) * dilation` input samples. Each `CausalTransConvNet` needs no cache (upsampling is local). The transformer needs its KV cache.

| Property | Value |
|----------|-------|
| Correctness | Bit-identical to batch decode |
| Boundary artifacts | None |
| Compute cost | O(T) total -- truly incremental |
| Implementation complexity | High |
| Memory | Per-layer caches (modest) |

**Implementation would require**:
1. Wrapping every `CausalConvNet` to maintain an activation buffer
2. Implementing KV cache management for the `WindowLimitedTransformer` in the quantizer
3. Handling the resolution changes at upsample boundaries correctly
4. Thorough testing to ensure cache state is managed correctly across calls

The existing codebase already has `KVCache` and `setup_caches()` on the Transformer, but these are used for the LLM's AR generation, not for the DAC decoder's quantizer transformer.

### Approach D: Parallel Decode on CPU/Second Stream (Orthogonal)

Run DAC decode on CPU or a secondary CUDA stream while the GPU continues token generation. This doesn't change the decode strategy but hides decode latency behind generation time.

Not recommended as primary approach -- DAC decode on CPU would be much slower, and CUDA stream parallelism with `torch.compile` + CUDA graphs is tricky.

## Risks

### R1: GPU Memory Leak (Known Issue)

GitHub #1025 documents memory growth per DAC decode call. More frequent decoding amplifies this. **Mitigation**: Investigate the root cause (likely intermediate tensor retention or CUDA allocator fragmentation). May need `torch.cuda.empty_cache()` periodically, or fix the underlying leak.

### R2: CUDA Graph Interference

The LLM token generation uses `torch.compile` with `mode="reduce-overhead"` (CUDA graphs). Running DAC decode on the same GPU interleaved with CUDA graph replay could cause issues. **Mitigation**: The current architecture already handles this -- LLM runs in a separate thread from the consumer that calls DAC decode. The queue-based design naturally serializes GPU access. No new risk from sub-chunk streaming.

### R3: Crossfader Interaction

The existing `StreamingCrossfader` with 1764-sample (40ms) overlap is designed for text-chunk boundaries. Sub-chunk boundaries within a single text chunk produce **contiguous** audio (no discontinuity), so crossfading is unnecessary and wastes ~40ms of audio per sub-chunk boundary. **Mitigation**: Use the `is_partial` flag from `GenerateResponse` to bypass crossfading for within-chunk sub-segments. Only crossfade at text-chunk boundaries.

### R4: First-Chunk Quality

The first 10 decoded tokens have limited transformer context (10 out of 128 window positions). This is inherent to the causal model and affects both streaming and batch decoding equally. In practice, the first ~128 tokens correspond to ~5.9s of audio -- for most TTS utterances, the transformer always operates with partial context. This is not a streaming-specific risk.

### R5: Token Rate vs Decode Overhead

At ~82 tok/s (observed generation rate), 10 tokens arrive every ~122ms. The decode call must complete within this window to avoid falling behind. Even Approach A (full redecode of growing buffer) takes only ~15-25ms for typical utterance lengths, well within budget. For very long utterances (>30s, >645 tokens), the redecode could grow to ~50ms+ but still fits within the 122ms budget.

## Recommendations

### Phase 1 (MVP): Approach A -- Grow-and-Redecode

1. **Implement sub-chunk token yielding** from `decode_n_tokens` as described in `RESEARCH-GENERATE-LONG.md` (the generator conversion is the main prerequisite, independent of the DAC strategy).

2. **Use the simplest correct decode strategy**: accumulate all tokens, redecode everything, emit only new audio. The compute overhead is negligible (~5x for a 5s utterance, but each decode is <25ms).

3. **Skip crossfading for sub-chunk boundaries**: Pass `is_partial=True` on sub-chunk yields. The consumer should concatenate sub-chunk audio directly without crossfading, since it's contiguous by the causal property. Only crossfade at text-chunk boundaries.

4. **Default sub-chunk size: N=10 tokens** (~464ms audio, ~122ms generation time). This gives a TTFA of ~127ms (122ms token gen + 5ms decode), well under the 200ms target.

5. **Investigate and fix the GPU memory leak** (#1025) before shipping, since more frequent decode calls will amplify it.

### Phase 2 (Optimization): Approach B -- Sliding Window

If Approach A's O(T^2) overhead becomes noticeable for long utterances (>30s), switch to sliding window decode with W=128 (matching the transformer receptive field). This caps decode cost at a fixed ~20ms regardless of utterance length.

### Phase 3 (Optional): Approach C -- Cached Convolution

Only pursue if profiling shows DAC decode is a significant bottleneck. The implementation complexity is high, and the existing approaches are likely sufficient given that decode time (~15-25ms) is small relative to token generation time (~122ms per 10 tokens).

### Parameter Recommendations

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `sub_chunk_tokens` | 10 | Achieves ~127ms TTFA, produces ~464ms audio buffer |
| Sliding window size | 128 | Matches transformer RF in quantizer post_module |
| Crossfade overlap | Skip for sub-chunks | Sub-chunk boundaries are contiguous, no artifacts |
| Crossfade overlap (text chunks) | 1764 samples (40ms) | Keep existing behavior at text-chunk boundaries |

### Why This Works

The fundamental enabler is that **the entire DAC decode pipeline is causal**:

1. Causal convolutions (left-padding only) -- no lookahead
2. Causal transposed convolutions (right-trimming) -- no lookahead
3. Causal transformer with window attention -- attends only to past
4. Codebook lookup is pointwise -- no temporal dependency

This means `decode(tokens[0:N])[-M:]` is **bit-identical** to `decode(tokens[0:N+K])[-M-K*2048:-K*2048]` for any K >= 0. No overlap-add, no crossfading, no artifact mitigation needed at sub-chunk boundaries. The only boundaries that need crossfading are between separate text chunks, where the LLM's generation may have slight discontinuities.
