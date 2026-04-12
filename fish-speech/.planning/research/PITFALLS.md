# Domain Pitfalls: Streaming Chunked TTS Audio

**Domain:** Streaming chunked audio for Fish Speech S2-Pro (DualAR transformer + DAC codec decoder)
**Researched:** 2026-04-12

## Critical Pitfalls

Mistakes that cause the user's previous problem (choppiness) or require significant rework.

### Pitfall 1: DAC Decoder Boundary Discontinuities (The Core Problem)

**What goes wrong:** Each text chunk is independently encoded to semantic tokens by the DualAR transformer, then independently decoded to audio by the DAC codec. Even though Fish Speech's DAC uses causal convolutions (`causal=True` in config), the decoder still has a receptive field that extends backwards. When you decode chunk N independently, the decoder's causal convolutions start with zero-padded state at the left edge. When you decode chunk N+1, it also starts with zero-padded state. The left edge of chunk N+1's audio is synthesized without any context from chunk N's final state. This produces a waveform discontinuity at the boundary -- the exact choppiness the user experienced.

**Why it happens:** The DAC decoder architecture has `decoder_rates: [8, 8, 4, 2]` (total upsampling = 512x), with 4 transformer layers in the first decoder block and causal convolution kernels (size 7) at every stage. The causal padding `(kernel_size - stride)` adds zeros at the left edge of each chunk's input to the convolution. These zeros produce transient artifacts in the first few decoded samples of each chunk. At 44100 Hz sample rate, the first ~50-100 samples of each decoded chunk are "cold start" artifacts.

**Consequences:** Audible clicks, pops, or volume dips at every chunk boundary. For a 10-sentence passage with 5 chunks, that is 4 audible discontinuities. This is the user's exact reported problem.

**Prevention strategy (ranked by effectiveness):**

1. **Overlap-decode with crossfade (recommended).** When decoding chunk N+1's VQ codes, prepend the last K codes from chunk N (where K covers the decoder's receptive field). Decode the full overlapping sequence, then discard the first K*hop_length samples (they reconstruct chunk N's tail) and crossfade the remaining overlap region with the tail of chunk N's decoded audio using a Hann window. This ensures the decoder has proper context at the boundary.

   Concrete numbers for this DAC: The quantizer has `downsample_factor: [2, 2]`, so each VQ token spans `512 * 4 = 2048` audio samples (~46.4ms at 44100 Hz). The decoder's receptive field through 4 upsampling stages with kernel-7 causal convolutions is approximately 3-5 VQ tokens. Prepending 4-8 VQ tokens of overlap (~185-370ms of audio) and crossfading over 512-1024 samples (~12-23ms) should eliminate boundary artifacts.

2. **Hann window crossfade (simpler, less effective).** If overlap-decoding is too complex, apply a Hann crossfade directly on the raw decoded samples at boundaries. Save the last N samples of chunk K's audio, and blend with the first N samples of chunk K+1's audio using `fade_out = 0.5 * (1 + cos(pi * t))` and `fade_in = 0.5 * (1 - cos(pi * t))`. The Qwen3-TTS-streaming project uses 512 samples (~21ms at 24kHz, equivalent to ~1024 samples at 44100Hz). This masks the discontinuity but does not fix it -- the crossfaded region may have slightly different timbre.

3. **Fade-in the first chunk and fade-out the last chunk.** Even with crossfading between chunks, the very first chunk's start and very last chunk's end need a short fade (128-256 samples) to avoid transient pops from the decoder's initial zero state.

**Detection:** Compare the waveform at chunk boundaries to a reference generated from the full text in one pass. Plot the amplitude around boundaries -- discontinuities show as sudden jumps in the waveform envelope.

**Phase mapping:** Phase 1 (core implementation) -- this is the single most important technical challenge.

---

### Pitfall 2: Conversation Context Explosion Across Chunks

**What goes wrong:** Fish Speech's `generate_long` function appends each batch's generated VQ codes back into the conversation history (line 730 in inference.py). For each subsequent chunk, the entire conversation (system prompt + reference audio tokens + all previous user/assistant turns) is re-encoded from scratch. This means:
- Chunk 1: Encodes system + ref + text_1 (prompt)
- Chunk 2: Encodes system + ref + text_1 + audio_1 + text_2 (longer prompt)
- Chunk 3: Encodes system + ref + text_1 + audio_1 + text_2 + audio_2 + text_3 (even longer)

Each chunk's generation starts with a full KV cache rebuild from the growing prompt. The prompt length grows linearly. This is NOT a memory leak (the KV cache is fixed-size at `max_seq_len`), but it means:
1. **TTFA for later chunks degrades** because prefill time grows with prompt length.
2. **Risk of hitting max_seq_len** (4096 tokens). With a 372-token reference and ~50-80 tokens per generated audio chunk, you can only fit ~40-50 chunks before overflow.
3. **The `deepcopy(conversation)` on line 657 copies all accumulated VQ codes**, which is a CPU-side memory allocation growing linearly.

**Why it happens:** The conversation-based architecture is designed for multi-turn dialogue coherence -- each chunk "sees" all previous audio to maintain prosody consistency. But for streaming TTFA optimization, the full re-encode is the main bottleneck for second-and-later chunks.

**Consequences:** Second chunk takes longer than first. Third chunk longer than second. For long texts (10+ chunks), later chunks can take 2-3x the time of the first chunk, negating the TTFA benefit of chunking. With max_seq_len=4096 and a 372-token reference, overflow happens around 3000-3500 generated tokens.

**Prevention strategy:**

1. **Cap conversation history.** Only keep the last 1-2 assistant turns (VQ codes) in the conversation, not all of them. This bounds the prompt size while still providing prosody context.
2. **Pre-compute the KV cache for the static prefix** (system prompt + reference). Cache it once, and for each chunk only run prefill on the new user/assistant turns. This avoids redundant computation of the ~400+ token prefix.
3. **Monitor prompt length.** Add a guard that logs a warning when `encoded.size(1) > max_length - 2048` is approaching, and truncate old conversation history rather than failing.

**Detection:** Log the `encoded.shape` for each batch (the code already does this). If the prompt grows by 100+ tokens per batch, the conversation is accumulating unboundedly.

**Phase mapping:** Phase 2 (optimization) -- the naive approach works for short texts but breaks for long ones.

---

### Pitfall 3: Text Splitting at Wrong Boundaries

**What goes wrong:** The current `group_turns_into_batches` function in `inference.py` splits text by byte count (`max_bytes=chunk_length`, default 300 bytes). For text without `<|speaker:X|>` tags (the common case for single-speaker streaming), the text falls through to `batches = [text]` -- a SINGLE batch with NO splitting at all. This means the "streaming" endpoint currently does NOT actually chunk single-speaker text for progressive generation.

If you add splitting, naive byte-count splitting can cut mid-sentence or mid-word, producing:
- Unnatural prosody breaks (the model generates end-of-utterance falling intonation mid-sentence)
- Repeated or dropped words at boundaries
- Loss of emotion/tag context (e.g., `[angry]I can't believe you did that` split into `[angry]I can't` and `believe you did that` -- second chunk loses the emotion tag)

**Why it happens:** The current splitting logic is designed for multi-speaker dialogue with `<|speaker:X|>` tags. Single-speaker text has no tags to split on. The `chunk_length` parameter (default 200 bytes in `ServeTTSRequest`) only controls the byte-count grouping of speaker turns, not sentence-level splitting.

**Consequences:** Either no chunking happens (defeating the purpose of streaming) or naive chunking produces unnatural speech with wrong prosody.

**Prevention strategy:**

1. **Split at sentence boundaries** using regex for sentence-ending punctuation: `.!?` and their CJK equivalents. Fall back to clause boundaries (`,;:` and CJK commas) if sentences are too long.
2. **Propagate emotion/style tags** to all chunks. If the original text starts with `[angry]`, prepend `[angry]` to every chunk.
3. **Minimum chunk size.** Never split a chunk smaller than ~50 bytes / 3-4 words. Very short chunks produce worse audio quality because the model has insufficient context for natural prosody.
4. **Maximum chunk size.** Keep chunks under ~200 bytes to maintain fast TTFA per chunk.

**Detection:** Log each chunk's text content. If any chunk is a sentence fragment that does not end at punctuation, the splitting is wrong.

**Phase mapping:** Phase 1 (core implementation) -- must be solved before streaming works at all for single-speaker text.

---

### Pitfall 4: torch.compile + CUDA Graphs Recompilation with Variable Sequence Lengths

**What goes wrong:** The current pipeline uses `torch.compile(mode="reduce-overhead")` which activates CUDA Graphs. CUDA Graphs require fixed tensor shapes. When chunking produces different-length VQ code sequences per chunk (because different text chunks produce different numbers of tokens), each new sequence length triggers a CUDA Graph re-recording. This costs:
- 64 KB GPU memory per re-recording per kernel (pre-CUDA 12.4)
- 100-500ms compilation overhead per new shape
- Up to `recompile_limit` (default 8) re-recordings before falling back to eager mode

With streaming chunks, you will have different prompt lengths for every chunk (due to growing conversation context). The prefill step processes a different-length prompt each time, triggering recompilation.

**Why it happens:** The `generate()` function creates tensors sized to the prompt length (`T = prompt.size(1)`) and the KV cache is set to `max_seq_len`. The prefill step processes `input_pos = torch.arange(0, T)` where T varies per chunk. The `decode_one_token` function is compiled with `reduce-overhead`, and while the token-by-token generation loop uses fixed shapes (always 1 new token), the prefill call to `decode_one_token_ar` uses variable-length inputs.

**Consequences:** First few chunks may see 200-500ms compilation stalls. After 8 unique shapes, the compiled function falls back to uncompiled eager mode, losing the ~30-40% speedup.

**Prevention strategy:**

1. **Pad prompts to fixed sizes.** Pad the encoded prompt tensor to one of a few fixed lengths (e.g., powers of 2: 512, 1024, 2048, 4096). This ensures CUDA Graphs only need to be recorded for a small number of shapes.
2. **Separate prefill from decode.** Only apply `torch.compile(mode="reduce-overhead")` to the token-by-token `decode_one_token` function (which already uses fixed shapes). Leave the prefill step uncompiled or compiled with `mode="default"`.
3. **Pre-warm all expected shapes.** During server startup, run dummy inference with each expected prompt length to pre-record all CUDA Graphs.

**Detection:** Set `TORCH_LOGS=guards,perf_hints` and look for "recompiling" messages during streaming inference. Also monitor `torch.cuda.max_memory_reserved()` -- unexpected growth indicates CUDA Graph re-recordings.

**Phase mapping:** Phase 2 (optimization) -- the system works without this, but will have latency spikes.

---

## Moderate Pitfalls

### Pitfall 5: WAV Streaming Header Issues

**What goes wrong:** The current WAV streaming implementation (`wav_chunk_header()` in utils.py) writes a header with zero data length, then streams PCM chunks after it. This is the standard approach for WAV streaming with unknown length. However:

1. The header uses `bit_depth=16` but the segment data in `inference_wrapper` is converted with `(result.audio[1] * 32768).astype(np.int16).tobytes()` -- this is correct for int16 PCM.
2. The `final` result yields `result.audio[1]` WITHOUT the int16 conversion (line 38 in `tools/server/inference.py`). If a client receives the final audio after segments, the encoding is inconsistent (float32 vs int16).
3. Some audio players and libraries do not handle WAV files with zero/max-value chunk sizes properly. The `wave` module Python uses writes a RIFF header with `nframes=0`, and some parsers interpret this as "empty file."

**Prevention strategy:**

1. Ensure consistent encoding: all streamed chunks must use the same format (int16 PCM at 44100 Hz).
2. For the `final` result, apply the same `* AMPLITUDE` + `astype(np.int16)` conversion as segments.
3. Consider using raw PCM streaming instead of WAV for the streaming endpoint, and only produce a proper WAV header when `streaming=False`.

**Detection:** Save the raw bytes from a streaming request and try to open them as a WAV file. If the header is malformed, standard audio libraries will fail to parse it.

**Phase mapping:** Phase 1 -- should be fixed as part of the streaming implementation.

---

### Pitfall 6: Buffer Underrun (Next Chunk Not Ready When Current Finishes Playing)

**What goes wrong:** If the client plays audio chunks in real-time and the server cannot generate the next chunk fast enough, there is a gap of silence between chunks. At ~80 tokens/sec and each token representing ~46ms of audio, the model generates audio roughly 3.7x faster than real-time (80 * 46ms = 3.68 seconds of audio per second). This seems safe, but:

1. **First chunk is the bottleneck.** The prefill step for the first chunk (reference encoding + prompt encoding + first-token generation) takes ~1.5s currently. During this time, nothing is playing.
2. **Later chunks have growing prefill times** (Pitfall 2). If conversation history is not capped, chunk 5+ may take longer than real-time to generate.
3. **Network latency** for API clients adds another variable. A 200ms network round-trip per chunk adds up.

**Prevention strategy:**

1. **Generate-ahead buffer.** Start generating the next chunk immediately after yielding the current one. Maintain a buffer of 1-2 pre-generated chunks so the client always has the next chunk ready.
2. **Cap conversation context** (Pitfall 2 prevention) to keep generation speed constant across chunks.
3. **Monitor real-time factor.** Log `audio_duration / generation_time` for each chunk. If it drops below 1.5x, emit a warning.

**Detection:** On the client side, measure the gap between receiving the last byte of chunk N and the first byte of chunk N+1. If this gap exceeds the chunk's audio duration, there is a buffer underrun.

**Phase mapping:** Phase 2 (optimization) -- TTFA improvement is Phase 1, buffer management is Phase 2.

---

### Pitfall 7: Emotion/Prosody Drift Across Chunks

**What goes wrong:** When text is split into chunks, each chunk is generated as a separate "turn" in the conversation. The model's prosodic style (pitch contour, speaking rate, emotional intensity) may drift across chunks because:

1. Each chunk generates its own `im_end` token, signaling a complete utterance. The model is trained to produce utterance-final prosody (pitch dropping, tempo slowing) at the end of each chunk.
2. If emotion tags are only present in the first chunk, subsequent chunks revert to neutral tone.
3. The model may produce slightly different voice characteristics across chunks due to sampling randomness (top-p, temperature).

**Consequences:** Audio sounds like a sequence of short separate utterances stitched together, rather than a continuous flowing speech. Each chunk may have a "mini-conclusion" prosodic contour followed by a "new beginning."

**Prevention strategy:**

1. **Do NOT place `im_end` markers mid-text.** If the text is one continuous utterance split for streaming purposes, the last chunk should be the only one that ends naturally. Earlier chunks should be generated without the model producing a final-utterance prosodic pattern. This may require modifying the generation loop to suppress or defer `im_end`.
2. **Set a fixed seed** across all chunks of one request to reduce sampling variance.
3. **Use conversation context** (the existing mechanism) to let the model "hear" its previous output before generating the next chunk, maintaining prosodic continuity.
4. **Propagate all style/emotion tags** to every chunk's text input.

**Detection:** Generate the same text as one chunk and as multiple chunks. Compare the pitch contour (F0) and speaking rate across the two versions. Significant F0 drops at chunk boundaries indicate utterance-final prosody leaking in.

**Phase mapping:** Phase 1 (quality) -- directly affects the "no perceivable quality loss" requirement.

---

## Minor Pitfalls

### Pitfall 8: Memory Growth from deepcopy of Conversation Objects

**What goes wrong:** The `generate_long` function calls `deepcopy(conversation)` for every batch (line 657). Each conversation object contains all previous VQ codes as CPU tensors. For a 10-chunk generation, this creates 10 deep copies of progressively larger conversation objects. The VQ codes are `(9 codebooks, N tokens)` tensors where N grows per chunk.

**Prevention:** Use shallow copies or reference-counted views of the VQ code tensors instead of deep copies. The VQ codes are never mutated after creation, so sharing references is safe.

**Phase mapping:** Phase 2 (optimization).

---

### Pitfall 9: Post-Processing Filter Applied Per-Chunk

**What goes wrong:** The `_post_fx` PeakFilter (3500Hz, +1.5dB, Q=0.7) is applied to each chunk independently. IIR filters (which PeakFilter likely is) have internal state. Starting each chunk with fresh filter state causes a transient at the beginning of each chunk's filtered output. This transient overlaps with the crossfade region, potentially making crossfading less effective.

**Prevention:** Either (a) apply the post-processing filter to the full concatenated audio after all chunks are joined (for non-streaming), or (b) carry the filter state across chunks (requires modifying the pedalboard library usage or implementing the filter manually).

**Detection:** Filter a long audio file as one piece vs. as chunks. Compare the output at chunk boundaries.

**Phase mapping:** Phase 2 (quality refinement).

---

### Pitfall 10: Streaming Endpoint Returns Final Audio Redundantly

**What goes wrong:** In `TTSInferenceEngine.inference()`, streaming mode yields both individual segments AND a final concatenated audio (line 139). The `inference_wrapper` in `tools/server/inference.py` handles segments (yielding int16 bytes) and the final result (yielding raw float32 array). A streaming client receives all segments AND then the full audio at the end. This doubles bandwidth for streaming clients.

**Prevention:** For streaming mode, skip the final concatenation yield. Only yield segments. The client can concatenate if it needs the full audio.

**Phase mapping:** Phase 1 -- straightforward fix during streaming implementation.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Text splitting | Pitfall 3: Wrong boundaries for single-speaker text | Implement sentence-boundary splitting with emotion tag propagation |
| DAC decoding | Pitfall 1: Boundary discontinuities | Overlap-decode + Hann crossfade; this is THE core challenge |
| Streaming API | Pitfall 5: WAV header inconsistency | Fix int16/float32 encoding mismatch |
| Streaming API | Pitfall 10: Redundant final audio | Skip final yield in streaming mode |
| TTFA optimization | Pitfall 2: Context explosion | Cap conversation history to last 1-2 turns |
| TTFA optimization | Pitfall 4: CUDA Graph recompilation | Pad prompts to fixed sizes; separate prefill from decode compilation |
| Quality | Pitfall 7: Prosody drift | Propagate emotion tags; use conversation context; avoid im_end mid-text |
| Quality | Pitfall 9: Filter transients | Carry pedalboard filter state across chunks or apply post-concat |
| Buffer management | Pitfall 6: Buffer underrun | Generate-ahead buffer of 1-2 chunks |
| Memory | Pitfall 8: deepcopy growth | Use shallow copies of immutable VQ tensors |

## Confidence Assessment

| Pitfall | Confidence | Basis |
|---------|-----------|-------|
| DAC boundary discontinuities | HIGH | Verified causal=True in config, analyzed CausalConvNet zero-padding behavior in code, confirmed by Gibiansky's streaming synthesis analysis and DAC-JAX documentation |
| Conversation context explosion | HIGH | Directly verified in generate_long source code -- conversation grows linearly, deepcopy confirmed |
| Text splitting for single-speaker | HIGH | Verified in code -- `split_text_by_speaker` returns empty for text without speaker tags, falls through to single batch |
| CUDA Graph recompilation | MEDIUM | Verified torch.compile reduce-overhead is used; variable prompt lengths confirmed in code; recompilation behavior from PyTorch documentation |
| WAV header issues | HIGH | Verified encoding mismatch between segment (int16) and final (float32) in inference_wrapper source |
| Buffer underrun | MEDIUM | Calculated from known token rates; later-chunk degradation depends on context accumulation rate |
| Prosody drift | MEDIUM | Known TTS chunking issue per literature; Fish Speech uses im_end per chunk, but severity depends on model behavior |
| deepcopy growth | HIGH | Directly visible in source code |
| Filter transients | LOW | IIR filter state assumption; pedalboard library may handle this internally |
| Redundant final yield | HIGH | Directly visible in source code |

## Sources

- [Qwen3-TTS-streaming: Hann crossfade implementation](https://github.com/rekuenkdr/Qwen3-TTS-streaming) -- 512-sample Hann window crossfade, chunk processing order
- [Pipecat/Nemotron pipeline: COLA-compliant overlap-add](https://github.com/pipecat-ai/nemotron-january-2026/blob/main/docs/streaming-pipeline-architecture.md) -- Adaptive blending with correlation measurement
- [Andrew Gibiansky: Streaming Audio Synthesis](https://andrew.gibiansky.com/streaming-audio-synthesis/) -- Causal convolution state carryover, zero-padding boundary artifact analysis
- [DAC-JAX: Chunked compression/decompression](https://arxiv.org/html/2405.11554v1) -- DAC padding behavior changes for chunked operations
- [Fish Speech Issue #1020: First chunk latency](https://github.com/fishaudio/fish-speech/issues/1020) -- response_queue.get() blocking delay
- [Fish Speech Discussion #853: Multi-second TTFA](https://github.com/fishaudio/fish-speech/discussions/853) -- 3.5-6s delay for medium text
- [Fish Speech Issue #819: Streaming returns all fragments](https://github.com/fishaudio/fish-speech/issues/819) -- Streaming parameter bug
- [PyTorch CUDA Graph Trees documentation](https://docs.pytorch.org/docs/stable/torch.compiler_cudagraph_trees.html) -- Recompilation behavior with dynamic shapes
- [Deepgram: Text Chunking for TTS Optimization](https://developers.deepgram.com/docs/text-chunking-for-tts-optimization) -- Sentence/clause boundary splitting best practices
- [EnCodec: Overlapping chunk processing](https://github.com/facebookresearch/encodec) -- 1% overlap for 48kHz model
- [WAV file format specification](http://soundfile.sapp.org/doc/WaveFormat/) -- Header structure, unknown-length streaming
- [SpeakStream: Interleaved text-speech streaming](https://arxiv.org/html/2505.19206v1) -- Architectural alternative avoiding chunk boundaries
