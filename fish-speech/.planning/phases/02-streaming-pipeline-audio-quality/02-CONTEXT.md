# Phase 2: Streaming Pipeline & Audio Quality - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Per-chunk audio generation with crossfade stitching and streaming segment emission. Input: list of text chunks (from Phase 1's `split_text_into_chunks()`). Output: streaming audio segments yielded to the client as each chunk completes, with seamless crossfaded boundaries and consistent int16 PCM encoding.

</domain>

<decisions>
## Implementation Decisions

### Crossfade Strategy
- **D-01:** Equal-power sin² crossfade applied at every chunk boundary to eliminate clicks/pops/discontinuities
- **D-02:** Crossfade duration 10-20ms (441-882 samples at 44.1kHz) — below auditory perception threshold for crossfade artifacts, sufficient to smooth boundary discontinuities
- **D-03:** Crossfade operates on decoded audio (numpy float32 arrays after PeakFilter), not on VQ tokens — tokens are discrete codebook indices, crossfading them is meaningless

### StreamingCrossfader Architecture
- **D-04:** New class `StreamingCrossfader` that buffers the tail `overlap_samples` from the previous segment and blends with the head of the next segment using equal-power sin² curves
- **D-05:** First segment: emit immediately after trimming the tail into the buffer (no prior segment to crossfade with)
- **D-06:** Subsequent segments: blend buffered tail with current head, emit blended region + non-overlapping body, buffer new tail
- **D-07:** Final flush: emit the remaining buffered tail when generation completes (no next segment to blend with)
- **D-08:** Crossfader state is per-sample (single `generate_long` call) — reset between different TTS requests

### Streaming Emission
- **D-09:** Segments yielded to client as they are crossfaded — the crossfader emits audio as soon as it has a complete blended region, not waiting for all chunks
- **D-10:** First audio segment emitted ASAP after first chunk decodes — this is the TTFA-critical path, no unnecessary buffering
- **D-11:** Each emitted segment is a complete, playable int16 PCM byte sequence — no partial frames

### WAV Header
- **D-12:** WAV header uses `0xFFFFFFFF` for both RIFF chunk size and data chunk size, signaling unknown/streaming length per WAV spec
- **D-13:** Replace current `wav_chunk_header()` implementation that produces 0-byte data size with explicit 0xFFFFFFFF construction

### Audio Encoding Consistency
- **D-14:** All streaming segments encoded as int16 PCM throughout the pipeline — no float32/int16 mismatch between header and data
- **D-15:** Amplitude scaling uses existing `* 32768` + `.astype(np.int16)` pattern (already in `tools/server/inference.py` line 33)

### PeakFilter Ordering
- **D-16:** PeakFilter stays per-chunk BEFORE crossfade (current behavior in `get_audio_segment()`) — crossfade operates on already-filtered audio, which is correct since the overlap region is tiny (10-20ms) and re-filtering would cause double-processing artifacts
- **D-17:** Non-streaming final audio path: PeakFilter is already applied per-segment before concatenation — this continues unchanged (QUAL-04)

### Backward Compatibility
- **D-18:** Non-streaming path (CLI `main()`) continues to merge VQ codes with `torch.cat` before single decode — no crossfade needed since single decode produces seamless audio
- **D-19:** Streaming=false API requests produce final concatenated audio with no behavior change from pre-Phase-2

### Claude's Discretion
- Exact sin² crossfade implementation (window functions, sample-level math)
- Internal method names and StreamingCrossfader API surface
- Whether to use overlap-add or overlap-save for the crossfade blending
- Buffer management details (pre-allocation vs dynamic)
- Logging verbosity for streaming segments

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Pipeline
- `fish_speech/inference_engine/__init__.py` — `TTSInferenceEngine.inference()` (line 45): streaming orchestration, segment collection, `np.concatenate(segments)` at line 139 — THE primary modification target
- `fish_speech/inference_engine/__init__.py` — `get_audio_segment()` (line 183): per-chunk DAC decode + PeakFilter — produces the float32 numpy arrays that crossfade will operate on
- `fish_speech/inference_engine/__init__.py` — `_post_fx` PeakFilter definition (lines 25-27)
- `fish_speech/models/text2semantic/inference.py` — `generate_long()` (line 780): the generator that yields `GenerateResponse(codes=...)` per-chunk — upstream of crossfade, not modified in Phase 2

### Streaming Transport
- `fish_speech/inference_engine/utils.py` — `wav_chunk_header()` (line 16): current WAV header construction — needs 0xFFFFFFFF modification
- `fish_speech/inference_engine/utils.py` — `InferenceResult` dataclass (line 9): result container for header/segment/final
- `tools/server/inference.py` — `inference_wrapper()` (line 12): converts InferenceResult to bytes, scales segments by AMPLITUDE=32768 to int16
- `tools/server/api_utils.py` — `inference_async()` (line 72): async generator wrapper for streaming HTTP response

### DAC Decoder
- `fish_speech/inference_engine/vq_manager.py` — `VQManager.decode_vq_tokens()` (line 16): VQ code → audio tensor via `decoder_model.from_indices()`
- `fish_speech/models/dac/modded_dac.py` — `DAC.from_indices()` (line 925): quantizer decode → convolutional decoder

### Research
- `.planning/research/SUMMARY.md` — synthesized findings on crossfade techniques, DAC decoder behavior, WAV streaming
- `.planning/REQUIREMENTS.md` — STRM-01..05, QUAL-01..04 acceptance criteria

### Phase 1 Output
- `.planning/phases/01-text-splitting-emotion-propagation/01-CONTEXT.md` — text splitting decisions that Phase 2 builds on

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_audio_segment()` — already decodes VQ tokens and applies PeakFilter per-chunk; returns float32 numpy array ready for crossfade
- `InferenceResult` dataclass — already has code="header"/"segment"/"final" variants for streaming
- `inference_wrapper()` — already handles int16 scaling and byte conversion for streaming segments
- `wav_chunk_header()` — needs modification but structure is reusable
- `AMPLITUDE = 32768` constant — already defined for int16 scaling

### Established Patterns
- Streaming uses generator-based architecture: `generate_long()` yields codes → `inference()` yields InferenceResults → `inference_wrapper()` yields bytes → `inference_async()` wraps as async
- PeakFilter applied per-segment before collection — crossfade should operate on these post-FX segments
- Segments stored as float32 numpy arrays internally, converted to int16 only at emission boundary

### Integration Points
- `TTSInferenceEngine.inference()` segment collection loop (lines 89-124) — insert StreamingCrossfader here between `get_audio_segment()` output and segment emission/collection
- `wav_chunk_header()` in utils.py — modify to produce 0xFFFFFFFF sizes
- `np.concatenate(segments)` at line 139 — crossfaded segments can still be concatenated for the final result, but seams should already be smooth

</code_context>

<specifics>
## Specific Ideas

- DAC codec is causal (causal=True) with hop_length=512 samples (~11.6ms at 44.1kHz) — natural alignment for crossfade window
- Each codec token = 2048 audio samples (~46.4ms at 44.1kHz) — even the smallest chunk produces enough audio for crossfade overlap
- First chunk at 80 bytes ≈ ~15-20 words ≈ ~1-2 seconds of audio — plenty of audio to start streaming immediately
- PeakFilter(cutoff_frequency_hz=3500, gain_db=1.5, q=0.7) — mild EQ boost, safe to apply per-chunk without audible artifacts at boundaries
- Equal-power crossfade: `fade_out = np.cos(t * pi/2)`, `fade_in = np.sin(t * pi/2)` where `t = np.linspace(0, 1, overlap_samples)` — ensures constant energy through the transition

</specifics>

<deferred>
## Deferred Ideas

- Acoustic tail prompting (ADVQ-01) — feeding previous chunk's last ~25 codec frames to next chunk's decoder for continuity (v2)
- Overlapped DAC decoding with extra context tokens (ADVQ-02) — v2
- Adaptive chunk sizing based on emotion (ADVQ-03) — v2
- KV cache accumulation between chunks (PERF-02) — v2

</deferred>

---

*Phase: 02-streaming-pipeline-audio-quality*
*Context gathered: 2026-04-12*
