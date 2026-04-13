# Phase 3 Research Synthesis: Sub-Chunk Audio Streaming

## Executive Summary

Sub-chunk audio streaming is **fully feasible** with low implementation complexity. The critical discovery is that Fish Speech's DAC decoder is fully causal — decoding partial VQ token sequences produces audio that is **bit-identical** to the corresponding prefix of a full decode. This eliminates the need for crossfading, overlap-add, or any artifact mitigation at sub-chunk boundaries. Audio within a single text chunk is contiguous and seamless by construction.

**TTFA target**: ~127ms (down from ~1-2s), achieved by decoding every 10 VQ tokens.

## Key Findings Across Research Areas

### 1. DAC Decoder: Fully Causal, Zero Boundary Artifacts

Source: RESEARCH-DAC.md

- Every layer uses causal convolutions (left-padding only) and causal transposed convolutions (right-trimming)
- The only transformer (WindowLimitedTransformer in quantizer post_module, window=128) uses a causal attention mask
- **Proof of causality**: `decode(tokens[0:N])` produces audio that is bit-identical to `decode(tokens[0:N+M])[0:N*2048]`
- No overlap, crossfade, or state management needed at sub-chunk decode boundaries
- The decoder is stateless — no hidden state persists between calls

### 2. Natural Audio Transitions

The user's core requirement: sub-chunk boundaries must be **imperceptible** — audio should sound like one continuous clip.

**Within a text chunk (sub-chunk boundaries)**:
- Audio is mathematically contiguous. Sub-chunk decode points are invisible because the causal property guarantees bit-identical prefixes. There is literally nothing to "smooth over" — consecutive sub-chunk audio segments are already one continuous waveform split at arbitrary points.
- No crossfading applied at sub-chunk boundaries (it would be wasteful and could introduce artifacts by blending already-correct audio).

**Between text chunks (chunk boundaries)**:
- The existing StreamingCrossfader (40ms sin²/cos² equal-power blend) handles discontinuities between independently-generated text chunks.
- Text splitter's sentence-boundary lookahead already splits at natural pause points (periods, commas, semicolons), so chunk boundaries tend to align with prosodic pauses — further masking any transition.

**Result**: The combination of (a) causal DAC for seamless sub-chunk streaming, (b) crossfading at text-chunk boundaries, and (c) splitting text at natural pause points produces audio indistinguishable from non-streaming batch output.

### 3. Token Generation: Safe Yield Points

Source: RESEARCH-GENERATE-LONG.md

- Only `decode_one_token_ar` is torch.compiled — the outer loop (`decode_n_tokens`) is plain Python
- Yield points go between calls to the compiled function, in the `decode_n_tokens` loop
- KV cache (slow AR: static, pre-allocated at max_seq_len; fast AR: reset every step) is unaffected by yields
- 3 functions need generator conversion: `decode_n_tokens` → `generate` → `generate_long`

### 4. torch.compile / CUDA Graph: Fully Compatible

Source: RESEARCH-COMPILE-CUDA.md

- CUDA graphs are per-call to `decode_one_token_ar`, not per-loop — yield between calls is the standard LLM streaming pattern
- ~2ms GPU idle bubble between graph replays is the natural window for CPU-side streaming work
- DAC decoder is NOT compiled, runs eager, handles any sequence length
- Zero changes to compiled function or compilation settings

### 5. Industry Context

Source: RESEARCH-TTS-STREAMING.md

| System | Streaming Level | Decoder | Approach |
|--------|----------------|---------|----------|
| XTTS | Token-batch (20 tokens) | HiFi-GAN (stateless) | Linear crossfade |
| Parler-TTS | Token-batch (10 tokens) | Full re-decode | Stride overlap |
| AudioCraft | Segment-level | SEANet | KV cache + segments |
| Lyra | Sample-level | SoundStream (stateful) | Cosine crossfade |
| **Fish Speech (proposed)** | **Token-batch (10 tokens)** | **Causal DAC (grow-and-redecode)** | **Direct concatenation** |

Fish Speech has a unique advantage: its causal DAC allows direct concatenation of sub-chunk audio without crossfading — simpler than every other system surveyed.

## Recommended Architecture

### Approach: Grow-and-Redecode (Simplest, Correct)

Accumulate all VQ tokens generated so far. Every N new tokens, decode the **entire accumulated sequence** and emit only the new audio samples.

```
all_tokens = []
prev_audio_samples = 0

for partial_tokens in token_generator():        # yields every N tokens
    all_tokens.append(partial_tokens)
    full = torch.cat(all_tokens, dim=-1)         # [10, T_total]
    audio = dac.from_indices(full[None])          # [1, 1, T_total * 2048]
    new_audio = audio[..., prev_audio_samples:]   # only new samples
    prev_audio_samples = audio.shape[-1]
    emit(new_audio)                               # stream to client
```

**Why this over sliding window or overlap-prefix?**
- Bit-identical to batch decode (zero quality compromise)
- No overlap management, no state tracking, no parameter tuning
- O(T²) overhead is negligible: 10 decodes of growing buffer for a 5s utterance totals ~5x single decode, but each decode is <25ms on RTX 5090
- Sliding window (O(T)) is an optimization for >30s utterances — deferred to v2

### Parameter Choices

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `sub_chunk_tokens` | 10 | 10 tokens × 12.2ms/token (82 tok/s) = 122ms generation + ~5ms decode = **~127ms TTFA**. Meets <200ms target with margin. |
| Audio per sub-chunk | ~464ms (10 × 46.4ms) | Sufficient for smooth playback buffer |
| Crossfade at sub-chunk | **SKIP** | Audio is bit-identical/contiguous — crossfading would waste audio and could introduce artifacts |
| Crossfade at text-chunk | 1764 samples (40ms) | Keep existing behavior — text chunks are independently generated |

### Why N=10 (Not N=20)

The DAC research showed N=10 gives ~127ms TTFA, well under the 200ms target. N=20 would give ~244ms TTFA which exceeds the target. The decode overhead for N=10 vs N=20 is marginal (more decode calls but each is fast). The grow-and-redecode approach makes each decode slightly more expensive as tokens accumulate, but even the worst case (107 tokens, 10 decode calls) totals ~200ms of decode time spread over a 5s utterance.

## Implementation Chain

### Modified Functions (3 files, ~4 functions)

1. **`decode_n_tokens`** → generator, yields `(num_codebooks+1, N)` tensor every N tokens
2. **`generate`** → generator, propagates yields from `decode_n_tokens`, writes into seq tensor
3. **`generate_long`** → yields `GenerateResponse(is_partial=True)` for sub-chunk partials, `GenerateResponse(is_partial=False)` for final chunk
4. **`TTSInferenceEngine.inference`** → uses `is_partial` flag to skip crossfade for sub-chunk boundaries, direct-concatenate sub-chunk audio

### Unchanged (Critical Invariants)

- `decode_one_token_ar` — compiled function, zero changes
- `DualARTransformer` and KV cache — no changes
- `StreamingCrossfader` — no changes (just not applied to sub-chunk boundaries)
- `DAC.from_indices()` — called with growing sequence, no changes
- Thread architecture (`launch_thread_safe_queue`) — no changes
- `split_text_into_chunks` — no changes (text splitting is orthogonal)

### New Additions

- `GenerateResponse.is_partial: bool = False` — distinguishes sub-chunk yields from final chunk
- `sub_chunk_tokens` parameter threaded from `ServeTTSRequest` through the pipeline
- Grow-and-redecode logic in `TTSInferenceEngine.inference` (accumulate tokens, decode full sequence, emit delta audio)

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| GPU memory leak (#1025) amplified by more frequent DAC decodes | Medium | Investigate root cause; periodic `torch.cuda.empty_cache()` as stopgap |
| O(T²) decode overhead for very long utterances (>30s) | Low | Typical TTS utterances are 2-10s; sliding window optimization deferred to v2 |
| Consumer not draining sub-chunk audio fast enough | Low | Existing queue architecture handles backpressure; WAV streaming already works |
| First ~128 tokens have partial transformer context | None | Identical for batch and streaming decode — not a streaming-specific issue |

## Decision Log

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Decode strategy | Grow-and-redecode | Overlap-prefix, Sliding window, Cached conv | Simplest, bit-correct, overhead negligible for typical lengths |
| Sub-chunk size | N=10 tokens | N=20, N=30 | Only N=10 achieves <200ms TTFA target |
| Sub-chunk crossfade | Skip (direct concat) | Apply existing crossfader | Audio is contiguous — crossfading unnecessary and potentially harmful |
| Generator vs callback | Generator conversion | Callback, separate queue | Pythonic, minimal threading changes, natural with existing generator pattern |
| DAC compilation | Keep eager | Compile DAC | Variable lengths, marginal benefit, complexity not justified |

## Files to Read Before Planning

- `fish_speech/models/text2semantic/inference.py` — `decode_n_tokens`, `generate`, `generate_long`, `GenerateResponse`
- `fish_speech/inference_engine/__init__.py` — `TTSInferenceEngine.inference`, `get_audio_segment`
- `fish_speech/utils/schema.py` — `ServeTTSRequest` (add `sub_chunk_tokens` parameter)
- `fish_speech/models/dac/modded_dac.py` — `DAC.from_indices()` (understand decode path)
- `fish_speech/inference_engine/crossfader.py` — understand skip logic needed

## Success Metrics

1. **TTFA < 200ms** for 50-200 char input with cached reference
2. **Zero audible artifacts** at sub-chunk boundaries (guaranteed by causal property)
3. **Audio identical to batch decode** (guaranteed by grow-and-redecode)
4. **Existing crossfader works correctly** at text-chunk boundaries
5. **torch.compile compatibility maintained** (zero changes to compiled function)
6. **VRAM stays ≤ 10.7GB** peak
