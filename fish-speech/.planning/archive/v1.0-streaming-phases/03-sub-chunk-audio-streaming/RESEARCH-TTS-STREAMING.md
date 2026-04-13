# Research: Token-Level Audio Streaming in TTS Systems

## Purpose

Survey how existing TTS and audio codec systems handle streaming at the token/sub-chunk level, to inform the design of sub-chunk audio streaming for Fish Speech S2-Pro.

---

## 1. XTTS / Coqui TTS

### Architecture
XTTS uses a GPT-based autoregressive model that generates mel-spectrogram-like latent tokens, followed by a HiFi-GAN vocoder that converts those latents to audio waveforms.

### Streaming Approach
XTTS implements streaming through the `inference_stream()` method with a generator pattern:

1. **Token accumulation**: The GPT model yields tokens incrementally via `gpt.get_generator()`, which calls `gpt_inference.generate_stream()` with `do_stream=True`.
2. **Batched vocoder decoding**: Tokens accumulate in `last_tokens` until reaching `stream_chunk_size` (default: **20 tokens**), then the batch is decoded through HiFi-GAN: `wav_gen = self.hifigan_decoder(gpt_latents, g=speaker_embedding)`.
3. **Crossfade blending**: The `handle_chunks()` method applies linear crossfading between consecutive audio chunks with `overlap_wav_len=1024` samples to eliminate boundary artifacts.

### Key Parameters
- `stream_chunk_size`: 20 tokens per decode batch (configurable)
- `overlap_wav_len`: 1024 samples crossfade region
- Crossfade type: linear fade-in / fade-out

### Why It Works
HiFi-GAN is a feed-forward vocoder with no temporal state -- it can decode any batch of mel tokens independently. The crossfade handles boundary discontinuities. This is fundamentally simpler than codec decoder streaming because HiFi-GAN doesn't have the multi-layer stateful convolution problem that DAC/EnCodec decoders have.

---

## 2. Bark (Suno)

### Architecture
Three-stage sequential pipeline:
1. Text -> Semantic tokens (GPT, 10k vocabulary)
2. Semantic -> Coarse codec tokens (2 EnCodec codebooks at 75Hz)
3. Coarse -> Fine codec tokens (8 total codebooks)
4. Fine tokens -> Audio via EnCodec decoder

### Streaming Support
**No native streaming.** Each stage requires the complete output of the previous stage before it can begin. The three autoregressive stages are fully sequential with no incremental output capability. The EnCodec decode step also processes the full token sequence at once.

### Relevance
Bark demonstrates the challenge: multi-stage codec TTS pipelines are inherently difficult to stream because each stage depends on complete prior output. Fish Speech's DualAR approach (single-stage token generation) is more amenable to streaming.

---

## 3. VALL-E / VALL-E X (Microsoft)

### Architecture
Two-stage codec token generation:
1. **AR stage**: Autoregressive generation of the first EnCodec codebook (sequential, one token at a time)
2. **NAR stage**: Non-autoregressive parallel generation of remaining 7 codebooks (requires full AR output)

### Streaming Support
**No streaming implemented** in available open-source implementations. The AR stage generates tokens sequentially but doesn't yield intermediate audio. The NAR stage requires the complete AR sequence. EnCodec decoding processes the full multi-codebook tensor at once.

The architecture is theoretically streamable at the AR level (since tokens are generated causally), but the NAR refinement step is a blocking barrier -- you can't decode partial sequences because the fine codebooks aren't available yet.

### Relevance
Fish Speech's DualAR model generates all codebooks simultaneously (10 codebooks per timestep), which eliminates the AR/NAR staging bottleneck that VALL-E has. This is a significant architectural advantage for streaming.

---

## 4. SoundStorm (Google)

### Architecture
Uses bidirectional attention with confidence-based parallel decoding to generate SoundStream codec tokens. Accepts semantic tokens as conditioning and produces all codebook levels.

### Streaming Support
SoundStorm uses **bidirectional attention**, meaning it cannot stream by design -- it needs to see the full sequence to generate tokens. It achieves speed through parallelism (30s of audio in 0.5s on TPU-v4) rather than streaming.

### Relevance
Demonstrates that parallel/non-autoregressive approaches trade streamability for throughput. Fish Speech's causal DualAR is the right choice for streaming.

---

## 5. Parler-TTS (HuggingFace)

### Architecture
Transformer language model generating multi-codebook tokens with delay pattern interleaving, decoded by EnCodec/DAC.

### Streaming Approach
Parler-TTS implements a `ParlerTTSStreamer` class with a sophisticated token accumulation strategy:

1. **Token accumulation**: Tokens arrive one at a time via `put()` and are concatenated to `token_cache`.
2. **Threshold-based decoding**: Decoding triggers every `play_steps` tokens (default: **10 tokens**). The condition `token_cache.shape[-1] % play_steps == 0` gates decode calls.
3. **Delay pattern mask**: `apply_delay_pattern_mask()` offsets each codebook prediction by 1 position, managing the interleaved generation pattern.
4. **Stride-based overlap**: Audio chunks overlap by `stride` samples, calculated as `hop_length * (play_steps - num_codebooks) // 6`.
5. **Queue-based delivery**: `on_finalized_audio()` places decoded audio into a thread-safe queue consumed by an iterator.

### Key Parameters
- `play_steps`: 10 tokens (controls latency vs. efficiency tradeoff)
- `stride`: derived from hop_length and play_steps (overlap region)
- First audio output: after exactly `play_steps` tokens generated

### Key Insight
Parler-TTS decodes the **full accumulated token cache** each time (not just the new tokens), then uses stride/offset to extract only the new audio. This is computationally wasteful but avoids the stateful decoder problem entirely.

---

## 6. ChatTTS

### Architecture
GPT-based token generation with codec decoder.

### Streaming Approach
ChatTTS implements streaming through a generator-based system:

1. **Batch processing**: Uses `stream_batch=24` as processing batch size
2. **Fixed audio window**: Yields chunks of `stream_speed=12000` samples per iteration
3. **Skip initial batches**: `pass_first_n_batches=2` -- skips initial batches before outputting audio (warmup/priming)
4. **Silence filtering**: Post-processes with threshold `1e-5` to skip silent chunks

### Key Parameters
- `stream_speed`: 12000 samples per chunk
- `stream_batch`: 24
- Initial skip: 2 batches (for priming the generation)

### Relevance
ChatTTS takes a pragmatic approach: generate in larger batches, yield fixed-size audio windows. No sophisticated overlap handling.

---

## 7. AudioCraft / EnCodec Streaming Framework (Meta)

### Architecture
AudioCraft provides a comprehensive streaming framework for its EnCodec-based models (MusicGen, AudioGen). This is the most sophisticated streaming codec system in the open-source ecosystem.

### Streaming Module Framework
`StreamingModule` is the base class that enables incremental processing:

- **State dictionary**: `_streaming_state: Dict[str, torch.Tensor]` stores per-layer state tensors (batch size as first dim, keys cannot contain dots)
- **Context manager**: `with module.streaming():` propagates streaming mode to all child modules, auto-clears state on exit
- **Hierarchical state**: `get_streaming_state()` traverses child modules with dot-separated key prefixes; `set_streaming_state()` distributes state back
- **Flush mechanism**: `flush()` processes remaining buffered inputs (e.g., terminal padding for causal convolutions)

### Transformer Streaming (KV Cache)
`StreamingMultiheadAttention._complete_kv()` implements the core caching:
1. Retrieves `past_keys`/`past_values` from `_streaming_state`
2. Concatenates with current K/V along time dimension
3. Optionally trims older context if `past_context` limit is set
4. Updates streaming state for next call
5. Offset tracking enables correct positional embeddings across calls

### SEANet Decoder Streaming
The SEANet decoder (used in EnCodec) uses `StreamableConv1d` and `StreamableConvTranspose1d`:
- **Causal mode prerequisite**: `causal=True` ensures no lookahead, required for streaming
- **Padding strategy**: All padding applied to the left in causal mode
- **trim_right_ratio**: Controls trimming of transposed convolution output in causal mode

**Important caveat**: Despite the "Streamable" naming, these conv wrappers handle **padding geometry** rather than maintaining stateful buffers. The actual streaming state management happens at the `StreamingModule` level, not in individual conv layers. The convolutions themselves process their full input on each call -- there is no per-layer input caching in the conv modules.

### EnCodec Segment-Level Streaming
For longer audio, EnCodec uses overlap-add between decoded segments:
- `segment_stride = max(1, int((1 - overlap) * segment_length))` with default `overlap=0.01`
- `_linear_overlap_add(frames, stride)` blends decoded segments
- Each segment is decoded independently, then blended

### Key Insight
AudioCraft's streaming is primarily at the **transformer/LM level** (KV cache for incremental token generation), not at the codec decoder level. The codec decoder still processes segments in their entirety -- streaming granularity is controlled by how many tokens you accumulate before triggering a decode call.

---

## 8. EnCodec Codec Decoder Details

### Decoder Architecture
SEANet decoder with causal convolutions:
- Quantizer decode: discrete codes -> embeddings
- Transposed convolution stack: progressive upsampling
- Each stage: Snake activation -> ConvTranspose1d -> 3x ResidualUnit (dilations 1, 3, 9)

### Overlap-Add for Segment Boundaries
When processing long audio in segments:
```
stride = max(1, int((1 - overlap) * segment_length))  # default overlap=0.01
frames = [decode_frame(f) for f in encoded_frames]
output = linear_overlap_add(frames, stride)
```

### Minimum Decode Unit
The minimum decode unit is determined by the quantizer output -- one timestep of all codebooks produces `hop_length` audio samples. In practice, decoding is done in larger segments for efficiency.

---

## 9. Descript Audio Codec (DAC) -- Standard Version

### Architecture
Feed-forward encoder-decoder with RVQ:
- Encoder: Conv1d -> 4x EncoderBlock (downsample by 2, 4, 8, 8) -> Conv1d
- Decoder: Conv1d -> 4x DecoderBlock (upsample by 8, 8, 4, 2) -> Conv1d -> Tanh
- Each DecoderBlock: Snake1d -> ConvTranspose1d -> 3x ResidualUnit (dilations 1, 3, 9)
- Hop length: 2 * 4 * 8 * 8 = **512** (standard DAC), product of encoder rates
- Codebooks: 9 by default, 1024 entries, 8-dim embeddings

### Streaming Support
**No streaming support in standard DAC.** The decoder processes complete latent sequences end-to-end. The `CodecMixin.compress()`/`decompress()` methods provide chunked processing for long audio but with simple concatenation (no overlap-add):
- `win_duration`: 1.0s window for chunked processing
- `delay` compensation: symmetric zero-padding before/after signal
- Chunks are decoded independently and concatenated

### Community Status
GitHub issue #101 ("Streaming DAC") is the only streaming discussion. It remains open with no concrete implementation. Community consensus: streaming is "totally a fundamental feature to be built" but no neural codec has properly implemented it.

---

## 10. Fish Speech's Modified DAC (modded_dac.py)

### Critical Finding: Causal Architecture Already Exists
Fish Speech's DAC fork (`modded_dac.py`) has **causal convolutions built in**:

- `CausalConvNet`: Left-only padding, `padding = kernel_size - stride`
- `CausalTransConvNet`: Standard ConvTranspose1d followed by `unpad1d()` to trim causal excess
- `CausalWNConv1d` / `CausalWNConvTranspose1d`: Weight-normalized causal wrappers
- `ResidualUnit(causal=True)`: Uses `CausalWNConv1d` throughout
- `DecoderBlock(causal=True)`: All internal layers use causal variants
- `Decoder(causal=True)`: Full decoder with causal convolutions
- `DAC(causal=True)`: **Default is `causal=True`** in Fish Speech's config

### Architecture Specifics
- `encoder_rates = [2, 4, 8, 8]` -> hop_length = 512
- `decoder_rates = [8, 8, 4, 2]` (reverse of encoder)
- `decoder_dim = 1536`
- 10 codebooks (via external quantizer)
- Sample rate: 44100
- `frame_length = hop_length * 4 = 2048`
- Optional WindowLimitedTransformer layers in encoder/decoder blocks

### Current Decode Pipeline
```python
# VQManager.decode_vq_tokens():
self.decoder_model.from_indices(codes[None])[0].squeeze()

# DAC.from_indices():
z = self.quantizer.decode(indices)
return self.decoder(z)
```
No streaming state, no incremental decoding. Full tensor in, full audio out.

### Why Causal Matters for Streaming
Because all convolutions are causal (left-padded only), the decoder's output at time `t` depends only on inputs at times `<= t`. This means:
1. You can feed a partial sequence of VQ embeddings and get valid audio for those timesteps
2. No future context is needed -- each additional token extends the output
3. The main challenge is **efficiency** (avoiding redundant computation) not **correctness**

---

## 11. Fish Speech's Current Streaming Architecture

### Existing Pipeline
The current system (`TTSInferenceEngine.__init__.py`) streams at the **chunk level**, not the token level:

1. LLAMA model generates tokens for a text chunk (blocking `response_queue.get()`)
2. Full chunk of VQ codes decoded to audio via `get_audio_segment()` -> `decode_vq_tokens()`
3. `StreamingCrossfader` applies equal-power sin^2/cos^2 crossfade between chunks (1764 samples = 40ms overlap)
4. Audio segments yielded as `InferenceResult(code="segment")`

### Chunk-Level Parameters
- `chunk_length`: 300 bytes of text per batch (controls text splitting)
- Crossfade overlap: 1764 samples (40ms at 44.1kHz)
- `iterative_prompt`: previous batch output conditions next batch

### The Gap
The blocking `response_queue.get()` waits for the LLAMA model to finish generating **all** tokens for a text chunk before any audio decoding begins. Sub-chunk streaming requires decoding partial token sequences while generation continues.

### Relevant Issues/PRs
- **#1020**: "First Chunk Latency" -- documents 187ms-1152ms latency depending on text length, 75-91% from LLAMA wait time
- **#659**: "Streaming Agent" -- merged Nov 2024, added streaming agent for web UI
- **#150**: "Streaming support" -- merged May 2024, original streaming implementation
- **#1133**: "How to change return audio length in streaming mode"
- **#1193**: Draft PR with streaming support improvements (Mar 2026)

---

## 12. Google Lyra (SoundStream-based Streaming Codec)

### Architecture
Production streaming codec for real-time communication, based on SoundStream.

### Streaming Approach
Lyra demonstrates the gold standard for streaming codec decoding:

1. **Hop-aligned processing**: `DecodeSamples()` processes audio in `GetNumSamplesPerHop()`-sized chunks
2. **Stateful decoder**: Maintains state variables across calls (`concealment_progress_`, `fade_progress_`, `fade_direction_`)
3. **Multi-source blending**: Dynamically switches between generative model output, comfort noise, and feature estimation
4. **Cosine overlap crossfade**: `(1 + cos(fade_progress * pi / fade_duration)) / 2` for smooth transitions
5. **Pre-allocated buffers**: `result.reserve(internal_num_samples_to_generate)` minimizes allocations

### Key Insight
Lyra treats the decoder as a stateful streaming processor, not a batch function. Each `DecodeSamples()` call produces exactly the requested number of output samples and maintains internal state for the next call.

---

## 13. Overlap-Add / Overlap-Save Approaches

### Standard Signal Processing Approaches

**Overlap-Add (OLA)**:
- Split input into overlapping windows
- Process each window independently
- Add overlapping output regions together
- Requires: window function that sums to 1 in overlap regions
- Used by: EnCodec (linear OLA with 1% overlap)

**Overlap-Save**:
- Process overlapping input blocks
- Discard boundary regions from each output
- Keep only the valid (non-boundary) portion
- Used when: decoder has settling time at boundaries

**Crossfade Blending**:
- Process adjacent blocks with overlap region
- Apply complementary fade curves to overlapping outputs
- Types: linear, equal-power (sin^2/cos^2), cosine
- Used by: XTTS (linear, 1024 samples), Fish Speech (sin^2/cos^2, 1764 samples), Lyra (cosine)

### For Causal Decoders
Causal decoders have a special property: output at time `t` depends only on input `<= t`. This means:
- **No settling time** at the start of a new block (left edge is always valid)
- **Potential settling artifacts** only if there's internal state reset between blocks
- If the decoder processes a growing sequence, each new output sample is valid immediately
- The overlap-add approach is **unnecessary** for causal decoders that maintain state -- it's only needed when decoding independent blocks

---

## 14. Causal Convolutional Decoder Streaming Techniques

### Approach A: Growing Sequence (Re-decode)
Feed the full accumulated token sequence each time:
```python
for new_tokens in token_stream:
    all_tokens = concat(all_tokens, new_tokens)
    all_audio = decoder(all_tokens)
    new_audio = all_audio[prev_length:]
    yield new_audio
    prev_length = len(all_audio)
```
- **Pros**: Correct output, no state management, simple
- **Cons**: O(n^2) compute -- re-decodes everything each time
- **Used by**: Parler-TTS (effectively)

### Approach B: Overlapping Windows
Decode overlapping windows of tokens, blend at boundaries:
```python
for new_tokens in token_stream:
    window = tokens[-(window_size + overlap):]
    audio = decoder(window)
    new_audio = crossfade(prev_tail, audio[:overlap]) + audio[overlap:]
    yield new_audio
```
- **Pros**: Fixed compute per step, bounded memory
- **Cons**: Requires overlap tuning, potential quality loss at boundaries
- **Used by**: XTTS, Fish Speech (current chunk-level)

### Approach C: Stateful Streaming Decoder
Cache intermediate activations (conv buffers, attention KV) across calls:
```python
for new_tokens in token_stream:
    new_audio, state = decoder.stream_forward(new_tokens, state)
    yield new_audio
```
- **Pros**: O(n) compute, minimal latency, theoretically optimal
- **Cons**: Complex implementation, must cache state for every layer
- **Used by**: AudioCraft (transformer level), Lyra (full stack)

### Approach D: Hybrid -- Causal Decode with Overlap Safety Margin
For causal decoders without explicit streaming state:
```python
# Decode N+M tokens, yield audio for first N tokens, keep M as overlap
for new_tokens in token_stream:
    buffer = concat(overlap_tokens, new_tokens)
    audio = decoder(buffer)
    overlap_audio_len = M * hop_length
    yield audio[overlap_audio_len:-overlap_audio_len]  # trim margins
    overlap_tokens = buffer[-M:]
```
- **Pros**: Simpler than full stateful streaming, handles conv receptive field
- **Cons**: Wastes some compute on overlap re-decoding
- **Practical choice for Fish Speech's causal DAC**

---

## Synthesis: Recommended Approach for Fish Speech

### Our Advantages
1. **Causal DAC decoder**: Fish Speech's modded DAC uses causal convolutions throughout (`causal=True` default). Output at time `t` depends only on input at times `<= t`. This is the single most important architectural advantage.
2. **DualAR single-stage generation**: All 10 codebooks generated per timestep, no AR/NAR staging bottleneck like VALL-E.
3. **Existing crossfader**: `StreamingCrossfader` with equal-power blending already exists and works.

### Recommended Strategy: Hybrid Approach D with Causal Optimization

Since DAC's decoder is fully causal, we can use a simplified version of Approach D:

1. **Token accumulation buffer**: Accumulate N tokens from the DualAR model before triggering a decode.
2. **Overlap prefix**: Keep M tokens from the previous decode as context overlap.
3. **Decode window**: Feed `[overlap_tokens + new_tokens]` to the DAC decoder.
4. **Extract new audio**: Take only the audio corresponding to the new tokens (skip the overlap prefix audio).
5. **Crossfade at boundaries**: Apply the existing `StreamingCrossfader` at the junction between consecutive decode windows.

### Parameter Estimates

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Minimum decode tokens (N) | 20-40 tokens | At 82 tok/s, 20 tokens = 244ms generation time. At hop=512, 20 tokens = 10240 samples = 232ms audio. Balance between latency and decode efficiency. |
| Overlap prefix (M) | 4-8 tokens | Causal conv receptive field. DAC has dilations 1,3,9 with kernel_size=7, giving effective receptive field of ~63 samples per layer. With 4 decoder blocks, M=4-8 tokens provides sufficient context. |
| Crossfade region | 1764 samples (40ms) | Already proven in current implementation. |
| First chunk latency target | ~300ms | 20 tokens generation (244ms) + decode time (~10-20ms) + buffer |

### Why Not Full Stateful Streaming (Approach C)?

Approach C (caching every conv layer's state) would be theoretically optimal but:
- Requires modifying every layer in DAC's decoder to support streaming state
- DAC has ~50+ conv layers across 4 DecoderBlocks (each with ConvTranspose1d + 3x ResidualUnit with 2 convs each = 7 convs per block, plus initial/final convs)
- WindowLimitedTransformer layers in decoder blocks add KV cache complexity
- High implementation complexity with marginal benefit over Approach D
- Risk of introducing subtle bugs in a critical audio path

Approach D gives us 90% of the benefit with 20% of the complexity. If profiling shows the overlap re-computation is a bottleneck, we can upgrade to Approach C later.

### Implementation Priorities

1. **Modify `generate_long()`/token generation** to yield tokens incrementally (every N tokens) instead of blocking until chunk complete
2. **Add token buffer** in inference engine that accumulates tokens and triggers decode
3. **Implement overlap-prefix decode** using existing DAC `from_indices()` with concatenated overlap + new tokens
4. **Wire into existing `StreamingCrossfader`** for boundary blending
5. **Profile and tune** N, M, and crossfade parameters

### Performance Comparison

| System | Streaming Level | Decoder Type | Boundary Handling | Min Decode | Complexity |
|--------|----------------|--------------|-------------------|------------|------------|
| XTTS | Token-batch | HiFi-GAN (stateless) | Linear crossfade | 20 tokens | Low |
| Bark | None | EnCodec (full) | N/A | All tokens | N/A |
| VALL-E | None | EnCodec (full) | N/A | All tokens | N/A |
| Parler-TTS | Token-batch | EnCodec/DAC (re-decode) | Stride overlap | 10 tokens | Medium |
| ChatTTS | Batch-window | Codec (full batch) | Silence filter | 24 batch | Low |
| AudioCraft | Token (LM) | SEANet (segment) | Linear OLA | Per segment | High |
| Lyra | Sample-level | SoundStream (stateful) | Cosine crossfade | 1 hop | Very High |
| Fish Speech (current) | Chunk-level | Causal DAC (full) | sin^2 crossfade | Full chunk | Low |
| **Fish Speech (proposed)** | **Token-batch** | **Causal DAC (overlap)** | **sin^2 crossfade** | **20-40 tokens** | **Medium** |

---

## References

- XTTS: github.com/coqui-ai/TTS (inference_stream, handle_chunks)
- Bark: github.com/suno-ai/bark (generation.py)
- VALL-E: github.com/lifeiteng/vall-e (valle.py)
- AudioCraft: github.com/facebookresearch/audiocraft (streaming.py, conv.py, seanet.py, transformer.py)
- EnCodec: github.com/facebookresearch/encodec (model.py, conv.py)
- DAC: github.com/descriptinc/descript-audio-codec (dac.py, base.py, issue #101)
- Parler-TTS: github.com/huggingface/parler-tts (streamer.py)
- ChatTTS: github.com/2noise/ChatTTS (core.py)
- Lyra: github.com/google/lyra (lyra_decoder.cc)
- SoundStorm: arxiv.org/abs/2305.09636
- Fish Speech modded DAC: fish_speech/models/dac/modded_dac.py
- Fish Speech inference engine: fish_speech/inference_engine/__init__.py
- Fish Speech issues: #1020, #659, #150, #1133, #1193
