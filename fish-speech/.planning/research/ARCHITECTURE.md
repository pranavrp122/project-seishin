# Architecture: Streaming Chunked TTS Pipeline

**Domain:** Real-time streaming TTS audio generation
**Researched:** 2026-04-12

## Current Architecture (Baseline)

Before describing the streaming architecture, here is how the system works today:

```
Client Request
    |
    v
API Server (kui.asgi) ─── StreamResponse
    |
    v
TTSInferenceEngine.inference()
    |
    ├── Load reference audio (cached) ──> DAC.encode() ──> prompt_tokens
    |
    ├── send_Llama_request() ──> llama_queue ──> worker thread
    |       |
    |       v
    |   generate_long():
    |       ├── Build Conversation (system prompt + reference audio VQ codes)
    |       ├── For each text batch:
    |       |     ├── split_text_by_speaker() ──> turns
    |       |     ├── group_turns_into_batches(max_bytes=chunk_length)
    |       |     ├── Append user message to Conversation
    |       |     ├── deepcopy Conversation + encode_for_inference()
    |       |     ├── generate() ──> DualAR token generation (prefill + decode)
    |       |     ├── Append assistant VQ codes back to Conversation
    |       |     └── yield GenerateResponse(action="sample", codes=codes)
    |       └── yield GenerateResponse(action="next")
    |
    ├── For each "sample" response:
    |       ├── get_audio_segment() ──> DAC.from_indices(codes) ──> audio
    |       ├── Apply post-FX (PeakFilter)
    |       └── yield InferenceResult(code="segment") [streaming]
    |
    └── Concatenate all segments ──> yield InferenceResult(code="final")
```

### Key Observations

1. **Text chunking already exists.** `group_turns_into_batches()` splits text by speaker tags and groups by byte limit (`chunk_length`, default 300 bytes). Each batch becomes a separate LLM generation call.

2. **Context carryover already exists.** `generate_long()` appends generated VQ codes back to the `Conversation` object before processing the next batch. The model sees previous audio context when generating the next batch.

3. **KV cache is NOT reused between batches.** Each batch re-encodes the full conversation from scratch (`deepcopy(conversation)` + `encode_for_inference()`). The KV cache is rebuilt from the growing prompt each time. This is the primary performance bottleneck for streaming.

4. **Audio segments are already streamed individually** via `inference_async()`. But each segment corresponds to a full text batch (hundreds of bytes), not a small chunk designed for low latency.

5. **DAC decode is synchronous and blocking.** `get_audio_segment()` runs on the main inference thread after each batch completes. There is no pipelining between LLM generation and DAC decoding.

6. **No crossfade exists.** Audio segments from different batches are simply concatenated (`np.concatenate(segments, axis=0)`), which can produce boundary artifacts.

## Codec Timing Parameters

Understanding the token-to-audio mapping is critical for buffer sizing:

| Parameter | Value | Source |
|-----------|-------|--------|
| DAC sample_rate | 44100 Hz | `modded_dac_vq.yaml` |
| DAC encoder_rates | [2, 4, 8, 8] | `modded_dac_vq.yaml` |
| DAC hop_length | 512 samples | `prod(encoder_rates)` |
| Quantizer downsample_factor | [2, 2] = 4x | `modded_dac_vq.yaml` |
| **Samples per codec token** | **2048** | `hop_length * downsample_factor` |
| **Audio duration per token** | **~46.4 ms** | `2048 / 44100` |
| DualAR generation rate | ~80 tok/s | Measured, PROJECT.md |
| **Time to generate 1 token** | **~12.5 ms** | `1 / 80` |
| DualAR num_codebooks | 4 (acoustic) + 1 (semantic) | `llama.py` config |
| n_codebooks in DAC | 9 | `modded_dac_vq.yaml` |
| Max context length | 8192 tokens | Model config |

Key implication: Each semantic token the DualAR generates maps to 2048 audio samples (~46.4ms). At 80 tok/s, 10 tokens takes ~125ms to generate but produces ~464ms of audio. The system generates audio faster than real-time (~3.7x real-time factor).

## Recommended Streaming Architecture

### Component Diagram

```
                          ┌─────────────────────────────────────┐
                          │         TTSInferenceEngine          │
                          │          (orchestrator)             │
                          └──────┬──────────────────────────────┘
                                 │
    ┌────────────────────────────┼───────────────────────────────┐
    │                            │                               │
    v                            v                               v
┌──────────┐           ┌─────────────────┐           ┌──────────────────┐
│  [C1]    │  text     │  [C2]           │  codes    │  [C3]            │
│  Text    │  chunks   │  LLM Token      │  (per     │  DAC Decoder     │
│  Chunker │ ────────> │  Generator      │  chunk)   │  + Post-FX       │
│          │           │  (generate_long) │ ────────> │                  │
└──────────┘           └─────────────────┘           └────────┬─────────┘
                                                              │ raw audio
                                                              │ segments
                                                              v
                                                    ┌──────────────────┐
                                                    │  [C4]            │
                                                    │  Crossfade       │
                                                    │  Stitcher        │
                                                    └────────┬─────────┘
                                                              │ stitched
                                                              │ audio
                                                              v
                                                    ┌──────────────────┐
                                                    │  [C5]            │
                                                    │  Stream          │
                                                    │  Emitter         │
                                                    └──────────────────┘
                                                              │
                                                              v
                                                         HTTP Response
                                                     (chunked WAV/PCM)
```

### Component Boundaries

| Component | Responsibility | Input | Output | Location |
|-----------|---------------|-------|--------|----------|
| **[C1] Text Chunker** | Split input text into small streaming chunks with intelligent boundaries | Full request text | Ordered list of text chunks | New: `fish_speech/inference_engine/text_chunker.py` |
| **[C2] LLM Token Generator** | Generate codec tokens for each chunk, maintaining context across chunks | Text chunks + reference tokens + conversation state | Codec token tensors per chunk | Modified: `generate_long()` in `inference.py` |
| **[C3] DAC Decoder + Post-FX** | Convert codec tokens to audio waveform and apply EQ | Codec token tensor | Raw float32 audio array | Existing: `get_audio_segment()` in `__init__.py` |
| **[C4] Crossfade Stitcher** | Blend chunk boundaries using Hann window overlap-add | Sequential raw audio segments | Seamless audio stream | New: `fish_speech/inference_engine/crossfade.py` |
| **[C5] Stream Emitter** | Package audio into WAV chunks and yield to HTTP response | Stitched audio segments | Bytes (WAV header + PCM data) | Modified: `inference_wrapper()` in `inference.py` |

---

## Component Details

### [C1] Text Chunker

**Problem:** The existing `group_turns_into_batches()` groups by speaker turns and byte limits (default 300 bytes). This produces large batches -- fine for throughput, bad for latency. We need smaller chunks to get first audio out faster.

**Strategy: Sentence-boundary splitting with minimum size floor.**

Split text at natural prosodic boundaries in this priority order:
1. Sentence boundaries (`.` `!` `?`)
2. Clause boundaries (`,` `;` `:` `--`)
3. Force-split at max byte limit if no boundary found

Constraints:
- **Minimum chunk: ~50 bytes** (~25 CJK chars or ~10 English words). Chunks smaller than this produce poor prosody because the model lacks context for natural intonation.
- **Maximum chunk: ~150 bytes** for streaming mode (vs. 300 default). Smaller max means faster TTFA.
- **First chunk should be smaller** (~80 bytes) to minimize TTFA. Subsequent chunks can be larger.
- **Emotion/speaker tags propagate.** If the input starts with `[angry]` or `<|speaker:0|>`, every chunk inherits the prefix tag. The tag is NOT repeated in token counting for byte limits.

**Interaction with existing code:** The text chunker replaces `split_text_by_speaker()` + `group_turns_into_batches()` for streaming mode only. Non-streaming requests continue using the existing path.

**Confidence:** HIGH -- sentence boundary splitting is well-established for TTS. The byte thresholds need empirical tuning.

### [C2] LLM Token Generator (generate_long modification)

**Problem:** Currently, `generate_long()` re-encodes the entire conversation for every batch. With a 17.27s reference audio (372 semantic tokens), the system prompt alone is substantial. Re-encoding this for every small chunk is wasteful.

**Current flow per batch:**
1. `deepcopy(conversation)` (includes all prior generated audio)
2. Append assistant message shell
3. `encode_for_inference()` -- tokenizes everything into a prompt tensor
4. `generate()` -- prefills the entire prompt through the model, rebuilding KV cache
5. Decode new tokens

**Recommended approach for streaming: Keep the existing re-encoding pattern, but with aggressive chunk sizing.**

Why NOT try to persist KV cache between chunks:
- The KV cache is set up once in `generate()` with `setup_caches()` and is tied to the `max_seq_len`. It does not support incremental appending across separate `generate()` calls.
- The `torch.compile` with `reduce-overhead` mode uses CUDA graphs, which capture fixed execution patterns. Changing the prefill length between calls would trigger recompilation/graph invalidation.
- The conversation accumulates VQ codes from previous chunks, so the prompt grows. But the reference audio tokens (372 tokens) and system prompt are the dominant prefix cost. With small text chunks, the incremental growth per chunk is modest.
- Attempting to persist KV cache state across calls would require deep changes to `generate()`, `setup_caches()`, and the compiled `decode_one_token`. This is high risk for the quality constraint.

**Instead, optimize by keeping chunks small and accepting the re-prefill cost:**
- With ~150 byte text chunks generating ~30-50 semantic tokens each, the prefill of ~500-600 tokens (system prompt + reference + growing context) completes in ~50-100ms.
- This is acceptable because the real-time factor is ~3.7x: while chunk N is being prefilled and decoded, the client is still playing chunk N-1's audio.

**Context carryover works as-is:** The existing `generate_long()` already appends generated VQ codes back to the conversation between batches. Smaller chunks mean more frequent context updates, which may actually improve prosodic consistency.

**What changes:**
- `generate_long()` accepts a `streaming_chunk_sizes` parameter (list of byte limits per chunk, with first chunk smaller)
- The existing `group_turns_into_batches()` is replaced by the new Text Chunker's output for streaming mode
- No changes to `generate()`, `decode_one_token`, or KV cache management

**Confidence:** HIGH for the conservative approach. The re-encoding overhead is real but bounded, and preserving `torch.compile` compatibility is critical.

### [C3] DAC Decoder + Post-FX

**No architectural changes required.** The existing `get_audio_segment()` correctly:
1. Takes codec token tensor `(num_codebooks, T)` from the LLM
2. Calls `DAC.from_indices(codes[None])` to decode to waveform
3. Applies PeakFilter post-FX

The only change: this component now processes smaller code tensors (fewer tokens per chunk), which is actually faster per call.

**Timing estimate:** DAC decode for ~40 tokens (~1.9s of audio) takes ~20-30ms. This is negligible compared to LLM generation time.

**Confidence:** HIGH -- existing code works correctly, just called more frequently with smaller inputs.

### [C4] Crossfade Stitcher

**Problem:** Adjacent audio segments from different LLM generation calls produce boundary artifacts. The model generates each chunk with context from previous chunks (via the conversation), so prosody is generally continuous, but the DAC decoder independently decodes each chunk's tokens. The waveform values at chunk boundaries may not align smoothly.

**Strategy: Hann window overlap-add crossfade.**

```
Chunk N audio:    [.......audio_data_N.......TAIL]
Chunk N+1 audio:  [HEAD.......audio_data_N+1.......]

                        overlap region
                   |<-- crossfade_samples -->|

Tail (fade out):   *= 0.5 * (1 + cos(pi * t))    where t = linspace(0, 1, crossfade_samples)
Head (fade in):    *= 0.5 * (1 - cos(pi * t))
Blended:           tail_faded + head_faded
```

**Parameters:**
- **crossfade_samples: 882** (~20ms at 44100 Hz). This matches the proven approach from Qwen3-TTS-streaming (512 samples at 24kHz = ~21ms). At 44100 Hz, 20ms = 882 samples.
- This is configurable. Start with 882, tune empirically. Range: 441 (10ms) to 2205 (50ms).

**Buffer management:**
1. Receive raw audio from DAC decoder
2. If this is the first chunk: store tail region (`audio[-crossfade_samples:]`), emit `audio[:-crossfade_samples]`
3. For subsequent chunks: crossfade `stored_tail` with `audio[:crossfade_samples]`, emit crossfaded region + `audio[crossfade_samples:-crossfade_samples]`, store new tail
4. For the final chunk: crossfade stored_tail with head, emit crossfaded + remaining audio (no tail withheld)

**Latency impact:** The crossfade introduces a delay of `crossfade_samples` (20ms) because we must withhold the tail of each chunk until the next chunk arrives. This is negligible.

**Implementation:**

```python
class CrossfadeStitcher:
    def __init__(self, crossfade_samples: int = 882):
        self.crossfade_samples = crossfade_samples
        self.stored_tail: np.ndarray | None = None
        # Pre-compute Hann curves
        t = np.linspace(0, 1, crossfade_samples, dtype=np.float32)
        self.fade_out = (0.5 * (1 + np.cos(np.pi * t))).astype(np.float32)
        self.fade_in  = (0.5 * (1 - np.cos(np.pi * t))).astype(np.float32)

    def process(self, audio: np.ndarray, is_last: bool = False) -> np.ndarray:
        """Process one audio chunk. Returns stitched audio to emit."""
        cs = self.crossfade_samples

        if self.stored_tail is None:
            # First chunk
            if is_last:
                return audio
            self.stored_tail = audio[-cs:].copy()
            return audio[:-cs]

        # Crossfade stored tail with current head
        blended = self.stored_tail * self.fade_out + audio[:cs] * self.fade_in

        if is_last:
            # Final chunk: emit everything
            result = np.concatenate([blended, audio[cs:]])
            self.stored_tail = None
            return result

        # Middle chunk: emit blended + middle, store new tail
        self.stored_tail = audio[-cs:].copy()
        return np.concatenate([blended, audio[cs:-cs]])

    def reset(self):
        self.stored_tail = None
```

**Confidence:** HIGH -- Hann window crossfade is the standard approach for audio stitching, validated by multiple TTS streaming implementations.

### [C5] Stream Emitter (WAV Header + PCM Streaming)

**Problem:** The current `wav_chunk_header()` emits a WAV header with zero data length, followed by raw PCM int16 chunks. This works because WAV players typically ignore the data length field when streaming. But it has a subtle issue: the header uses a placeholder size, so the resulting file is technically malformed if saved.

**Recommended approach: Keep the existing WAV streaming pattern.**

The current implementation is correct for streaming:
1. Emit WAV header with `data` chunk size set to 0 (or 0xFFFFFFFF)
2. Stream PCM int16 data chunks as they become available
3. Clients that support chunked transfer encoding play progressively

**What changes:**
- `inference_wrapper()` gains awareness of the crossfade stitcher
- Each yielded segment goes through the stitcher before being converted to int16 bytes
- The AMPLITUDE scaling (32768) and int16 conversion remain as-is

**Data flow through the emitter:**

```
inference() yields InferenceResult(code="segment", audio=(sr, float32_array))
    |
    v
CrossfadeStitcher.process(float32_array)
    |
    v
(stitched_audio * 32768).astype(np.int16).tobytes()
    |
    v
HTTP chunked response
```

**Confidence:** HIGH -- the existing pattern works and just needs the crossfade stitcher inserted.

---

## Data Flow (End to End)

```
1. Request arrives: text="Hello, how are you? I'm doing well, thanks for asking."

2. Text Chunker splits:
   chunk_0: "Hello, how are you?"         (~55 bytes, small for fast TTFA)
   chunk_1: "I'm doing well, thanks for asking."  (~100 bytes)

3. LLM generates chunk_0:
   - Conversation: [system + reference audio]
   - User: "Hello, how are you?"
   - generate() -> ~35 semantic tokens (~430ms generation, ~1.6s audio)
   - Append VQ codes to Conversation

4. DAC decodes chunk_0 codes -> raw_audio_0 (float32, ~71,680 samples)

5. Crossfade processes raw_audio_0 (first chunk):
   - Emit audio_0[:-882] (70,798 samples)
   - Store audio_0[-882:] as tail

6. Stream emitter converts to int16 PCM bytes and yields to HTTP

   >>> Client starts playback (~500ms from request) <<<

7. LLM generates chunk_1 (while client plays chunk_0):
   - Conversation: [system + reference + chunk_0 VQ + user chunk_0 text + assistant chunk_0 codes]
   - User: "I'm doing well, thanks for asking."
   - generate() -> ~50 semantic tokens

8. DAC decodes chunk_1 codes -> raw_audio_1

9. Crossfade: blend stored_tail with raw_audio_1[:882], emit, store new tail

10. Stream remaining audio from chunk_1

11. Final: flush stored tail (fade out to zero or emit as-is)
```

## TTFA Analysis

| Step | Time (estimated) | Cumulative |
|------|----------------:|----------:|
| Request parsing + reference load (cached) | ~5 ms | 5 ms |
| Text chunking | ~1 ms | 6 ms |
| Conversation encoding (system + ref) | ~20 ms | 26 ms |
| LLM prefill (~400 tokens prompt) | ~50 ms | 76 ms |
| LLM decode first token | ~12.5 ms | 89 ms |
| LLM decode ~34 more tokens (small first chunk) | ~425 ms | 514 ms |
| DAC decode ~35 tokens | ~20 ms | 534 ms |
| Crossfade + int16 conversion | ~1 ms | 535 ms |
| Network transmission (first chunk) | ~5 ms | 540 ms |

This is slightly over the 500ms target. To hit <500ms, the first chunk should target ~25 tokens (~30 bytes of text, roughly one short sentence or clause). Tuning the first-chunk size is the primary lever.

With a ~30-byte first chunk (~25 tokens, ~312ms generation):
- Prefill (~400 tokens): ~50ms
- Decode 25 tokens: ~312ms
- DAC + overhead: ~30ms
- **Total TTFA: ~392ms** -- well under 500ms target

## Anti-Patterns to Avoid

### Anti-Pattern 1: Persisting KV Cache Across generate() Calls
**What:** Attempting to save and restore the KV cache between chunk generation calls to avoid re-prefilling.
**Why bad:** The KV cache is tied to `torch.compile` CUDA graphs. Modifying cache state between graph executions causes silent corruption or recompilation storms. The conversation context changes between chunks (new user text + new assistant codes), making partial cache reuse complex and error-prone.
**Instead:** Accept the re-prefill cost. It is bounded (~50-100ms) and the system runs faster than real-time.

### Anti-Pattern 2: Parallel DAC Decoding
**What:** Attempting to decode multiple chunks' codes through DAC simultaneously on the same GPU.
**Why bad:** DAC is a GPU-bound operation. Running concurrent decodes on the same device does not improve throughput and can increase VRAM usage. The DualAR transformer already occupies most VRAM.
**Instead:** Sequential DAC decode per chunk. Each decode is ~20-30ms, which is negligible.

### Anti-Pattern 3: Raw PCM Without WAV Header
**What:** Streaming raw PCM bytes without any container format, expecting clients to know the sample rate and format.
**Why bad:** Clients need metadata to play audio. Raw PCM requires out-of-band format negotiation.
**Instead:** Keep the existing WAV header approach. A single WAV header at the start, followed by chunked PCM data.

### Anti-Pattern 4: Overlapping LLM Generation with DAC Decode via Threading
**What:** Running LLM token generation for chunk N+1 concurrently with DAC decode for chunk N using separate threads.
**Why bad:** Both operations use the same GPU. The LLM worker thread holds the model; DAC decode in `get_audio_segment()` also runs on GPU. Threading for GPU operations does not achieve parallelism -- it adds synchronization overhead and risks CUDA stream conflicts.
**Instead:** Sequential pipeline: generate chunk N tokens -> decode chunk N audio -> emit chunk N -> generate chunk N+1 tokens. The real-time factor (3.7x) provides sufficient headroom.

## Scalability Considerations

| Concern | Current (single user) | At 10 concurrent users |
|---------|----------------------|----------------------|
| VRAM | ~10.7 GB peak (fits in 32GB) | Not applicable -- single-worker, serialized via `llama_queue` |
| Latency | ~540ms TTFA (tunable to <400ms) | Queued; Nth user waits for N-1 completions |
| Throughput | ~3.7x real-time factor | Same per-request; concurrency via multiple GPU workers (out of scope) |
| Context growth | Conversation grows with each chunk; bounded by 8192 max_seq_len | Same per-request |

## Suggested Build Order

The components have these dependencies:

```
[C1] Text Chunker ──────────────────────────┐
                                             │
[C4] Crossfade Stitcher (standalone) ───────┐│
                                            ││
[C2] LLM Generator modifications ──────────┤│ all feed into
                                            ││
[C3] DAC Decoder (no changes needed) ──────┤│
                                            vv
                              [C5] Stream Emitter (integration)
```

**Phase 1: Crossfade Stitcher [C4]**
- Build and unit test independently with synthetic audio
- No dependencies on other components
- Can be validated with known audio samples for artifact-free stitching
- Estimated: 1-2 hours

**Phase 2: Text Chunker [C1]**
- Build sentence-boundary splitting with configurable chunk sizes
- Unit test with various text inputs (English, CJK, mixed)
- Test edge cases: very short text, single sentence, emotion tags
- No dependency on streaming infrastructure
- Estimated: 2-3 hours

**Phase 3: Integration [C2 + C5]**
- Modify `generate_long()` to accept chunker output
- Wire crossfade stitcher into `inference_wrapper()`
- Modify `TTSInferenceEngine.inference()` to use new chunking in streaming mode
- Integration test: full request -> streamed audio -> verify no artifacts
- This is where things get tested end-to-end
- Estimated: 3-4 hours

**Phase 4: Tuning and Validation**
- Measure TTFA with various first-chunk sizes
- A/B compare audio quality vs non-streaming output
- Tune crossfade_samples parameter
- Stress test with long text inputs (context growth toward 8192 limit)
- Estimated: 2-3 hours

## Sources

- [Qwen3-TTS-streaming (Hann crossfade implementation)](https://github.com/rekuenkdr/Qwen3-TTS-streaming) -- HIGH confidence, verified implementation
- [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v2) -- HIGH confidence, official architecture docs
- [Deepgram Text Chunking for TTS](https://developers.deepgram.com/docs/tts-text-chunking) -- MEDIUM confidence, industry practice reference
- [Prosodic Boundary-Aware Streaming TTS (arXiv 2603.06444)](https://arxiv.org/html/2603.06444) -- MEDIUM confidence, academic reference for boundary-aware approaches
- [RealtimeTTS (sentence boundary splitting)](https://github.com/KoljaB/RealtimeTTS) -- MEDIUM confidence, open source reference implementation
- [Fish Speech GitHub Discussion #692](https://github.com/fishaudio/fish-speech/discussions/692) -- MEDIUM confidence, community discussion on streaming context reuse
- Codebase analysis of `/home/prana/project-seishin/fish-speech/` -- HIGH confidence, direct code reading
