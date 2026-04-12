# Feature Landscape: Streaming Chunked TTS Audio

**Domain:** Streaming chunk boundary handling for Fish Speech S2-Pro TTS
**Researched:** 2026-04-12

## Table Stakes

Features users expect. Missing = audible quality degradation or broken streaming.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Crossfade/overlap-add at chunk boundaries** | Without it, every chunk join produces an audible click or pop. The DAC codec decoder has a wide receptive field -- neighboring tokens influence audio reconstruction, so naive concatenation of independently-decoded chunks creates discontinuities. This was the exact problem in the previous attempt ("choppiness at boundaries"). | Low | Hann window crossfade is the standard approach. 512 samples (~12ms at 44.1kHz) overlap with `fade_out = 0.5*(1+cos(pi*t))`, `fade_in = 0.5*(1-cos(pi*t))`, `blended = prev_tail*fade_out + curr_head*fade_in`. The Descript Audio Codec ecosystem uses 10% overlap with averaging as an alternative. Both are signal-level operations, ~10 lines of numpy/torch. |
| **Silence/pause-aware text splitting** | Splitting mid-word or mid-clause destroys prosody. Fish Speech's current `group_turns_into_batches` splits on byte count only (`max_bytes=chunk_length`), not on linguistic boundaries. Splitting at "The cat sat on th-" vs "The cat sat on the mat." produces dramatically different quality. Punctuation (commas, periods) directly influences Fish Speech's pause generation. | Low-Med | Regex-based clause boundary detection (split at `.`, `,`, `;`, `:`, `!`, `?`, then coordinating conjunctions). The Voice Agent AI SDK pattern: `minChunkSize` (50 chars) / `maxChunkSize` (200 chars) with fallback to clause boundaries. Deepgram uses a similar approach. Fish Speech already has `split_text_by_speaker()` -- extend this to split within speaker turns at clause boundaries. |
| **Context carryover between chunks (conversation history)** | The model needs to know what it already said to maintain coherent voice, prosody, and style. Fish Speech's `generate_long()` already does this: it appends each generated VQPart back into the conversation before generating the next batch. This is the "iterative_prompt" pattern. Without it, each chunk sounds like the start of a new utterance. | Already implemented | The current code deep-copies the conversation, appends the user text, generates, then appends the assistant's VQ codes back. This is the correct pattern. The KV cache is reset between batches (full re-encode of conversation), which is safe but slower than KV cache accumulation. |
| **Emotion tag propagation across chunks** | When text starts with `[angry]` or `[whisper in small voice]`, that emotional state must apply to all chunks, not just the first. Fish Speech S2 supports 15,000+ free-form inline tags. If the tag only appears in the first chunk's text, subsequent chunks lose the emotional context. | Low | Prepend the emotion/style tag to each chunk's text before sending to the model. Since Fish Speech embeds tags as text within the prompt, this is string manipulation only. The conversation history (which includes prior generated audio) also reinforces the style, but explicit tag propagation is more reliable. |

## Differentiators

Features that set the implementation apart. Not expected by default, but valued when present.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **KV cache accumulation across chunks** | Instead of re-encoding the full conversation for each chunk (current behavior), keep the KV cache from the previous chunk and only encode the new text + generate. This reduces TTFA for the 2nd+ chunks from O(conversation_length) to O(new_text_length). For a 5-chunk utterance, chunks 2-5 skip re-encoding the system prompt + reference audio + all prior text/audio. | High | Requires modifying `generate_long()` to not deep-copy the conversation per batch, and instead reuse the model's KV cache with the correct `input_pos` offset. The challenge: `torch.compile` with `reduce-overhead` mode uses CUDA graphs that capture fixed tensor shapes. KV cache accumulation changes the prefill length each batch, which may require re-capture or careful padding. The DualAR slow transformer needs full accumulated context; the fast transformer resets per step (already the case). |
| **Prosody continuity via acoustic tail prompting** | Feed the last N codec frames (e.g., 25 frames = ~1.2s at 21 Hz) from the previous chunk as acoustic context when decoding the next chunk's codec tokens. This gives the DAC decoder explicit acoustic continuity, not just semantic continuity from conversation history. Similar to faster-qwen3-tts's "sliding window with 25-frame left context." | Med | Prepend previous chunk's tail codes to current chunk's codes before calling `decoder_model.from_indices()`, then trim the overlap from the output audio. This operates at the codec decode level (VQManager.decode_vq_tokens), not the text2semantic level. The DAC model's decoder is convolutional with a receptive field spanning multiple frames, so this provides real continuity. |
| **Adaptive chunk sizing based on content** | Instead of fixed byte-count chunking, analyze text structure to create chunks of variable size: short chunks for exclamations ("What!"), longer chunks for complex sentences. This produces more natural-sounding speech because chunk boundaries align with semantic boundaries. | Med | Requires a lightweight text analyzer that scores potential split points by: (1) punctuation strength (period > comma > no punctuation), (2) clause completeness, (3) minimum viable chunk size (avoid single-word chunks). The target: 100-300 bytes per chunk, with boundaries always at clause/sentence ends. The Voice Agent AI SDK and Deepgram both implement variants of this. |
| **Streaming vocoder decode (sub-chunk emission)** | Instead of waiting for the full chunk's semantic tokens to be generated before running the DAC decoder, decode audio incrementally as semantic tokens arrive. Each 21 Hz semantic token = ~46ms of audio. Emitting every 5-10 tokens would yield audio every ~230-460ms within a chunk. | High | The DAC decoder's convolutional architecture processes all tokens at once via `from_indices()`. Sub-chunk streaming would require either: (a) running the decoder on partial token sequences with overlap (wasteful), or (b) a streaming-capable vocoder like BigVGAN's chunked mode. Fish Speech's modded DAC has a `WindowLimitedTransformer` with window_size=128 in the quantizer, suggesting some locality, but the decoder itself has global receptive field from the transposed convolution stack. |

## Anti-Features

Features to explicitly NOT build. These add complexity without proportional value for this project's constraints.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Token-level streaming from text2semantic** | Yielding semantic tokens one-at-a-time from the slow AR transformer to the DAC decoder. This would require fundamentally restructuring `generate()` and `decode_n_tokens()` to yield mid-generation, plus the DAC decoder cannot produce quality audio from single tokens (needs context). The `torch.compile` with `reduce-overhead` captures CUDA graphs around the decode loop, making mid-loop yields incompatible. | Chunk at the text level (current approach, improved). Each chunk generates a full sequence of semantic tokens, then decodes to audio. TTFA improvement comes from smaller chunks, not from token-level streaming. |
| **Dynamic model switching per chunk** | Using different model configurations or temperatures per chunk to "optimize" for different content types (fast speech, slow speech, emotional vs neutral). | Keep sampling parameters constant across chunks. Consistency matters more than per-chunk optimization. The reference audio and conversation history already condition the model's behavior. |
| **Client-side crossfade** | Pushing overlap-add responsibility to the client (browser/player). This creates quality variance across clients and makes the server API harder to use correctly. | Server-side crossfade before yielding audio bytes. The server knows the codec's characteristics and can apply the optimal blend. Client receives seamless audio. |
| **Speculative decoding for faster chunk generation** | Speculative decoding with audio codebook tokens has lower acceptance rates than text LLMs (codebook distributions are more uniform), requires a draft model, and adds 2-3 weeks of engineering for uncertain gains. | Focus on smaller chunks + KV cache reuse for latency. The 80 tok/s generation speed is already fast; the bottleneck is TTFA from large chunk sizes, not per-token generation speed. |
| **Multi-speaker streaming** | Supporting speaker changes within a streaming session adds conversation management complexity (which speaker's emotion state? which reference audio?). | Single-speaker streaming only, as specified in PROJECT.md scope. |
| **Lookahead/future-text conditioning** | Research systems like the prosodic boundary-aware method (arXiv 2603.06444) use future text to improve prosody at chunk boundaries. This requires buffering future text before generating the current chunk, which increases TTFA. | Rely on conversation history (past context) and acoustic tail prompting for continuity. For this use case (dialogue lines), the text is fully available upfront, so text-level splitting with clause awareness gives similar benefits without the complexity. |

## Feature Dependencies

```
Silence/pause-aware splitting ──> Crossfade at boundaries
  (Better split points reduce the severity of boundary artifacts,
   but crossfade is still needed as a safety net)

Emotion tag propagation ──> Silence/pause-aware splitting
  (Tags must be propagated after splitting is done,
   so splitting logic must expose tag state)

Context carryover (conversation) ──> Chunk generation
  (Already implemented. Each chunk depends on prior chunks
   being appended to conversation history)

KV cache accumulation ──> Context carryover
  (Optimization of the existing conversation-based carryover;
   requires the carryover pattern to be stable first)

Acoustic tail prompting ──> Crossfade at boundaries
  (Tail prompting provides codec-level continuity;
   crossfade handles any remaining signal discontinuity)

Adaptive chunk sizing ──> Silence/pause-aware splitting
  (Adaptive sizing is an evolution of boundary-aware splitting,
   adding dynamic size targets based on content analysis)
```

## MVP Recommendation

Prioritize in this order:

1. **Silence/pause-aware text splitting** (table stakes) -- Replace byte-count splitting with clause/sentence boundary detection. This single change addresses the root cause of most boundary artifacts: bad split points. Fish Speech generates pauses at punctuation, so splitting at punctuation means chunks naturally end with silence.

2. **Crossfade/overlap-add at chunk boundaries** (table stakes) -- Hann window crossfade with ~512 samples overlap at 44.1kHz (~12ms). Apply server-side before yielding audio bytes. This is the safety net for any remaining discontinuities.

3. **Emotion tag propagation** (table stakes) -- Prepend emotion/style tags to each chunk's text. Simple string manipulation, but critical for the project's use case (emotional consistency for voice baking).

4. **Acoustic tail prompting** (differentiator, high value) -- Prepend previous chunk's last ~25 codec frames when decoding the next chunk. This gives the DAC decoder proper acoustic context across boundaries, producing smoother transitions than crossfade alone.

**Defer:**
- **KV cache accumulation**: High complexity, risk of breaking `torch.compile` + CUDA graphs. The latency win matters most for chunks 3+ in long text; for typical dialogue lines (2-3 chunks), the benefit is modest. Research-flag this for a later phase.
- **Adaptive chunk sizing**: Nice-to-have refinement on top of clause-aware splitting. Can be added incrementally.
- **Streaming vocoder decode**: Requires DAC architecture changes or a different vocoder. Not viable without model modification, which is out of scope.

## Complexity Budget

| Feature | Engineering Days | Risk | Priority |
|---------|-----------------|------|----------|
| Clause-aware text splitting | 1-2 | Low | P0 |
| Hann crossfade overlap-add | 0.5-1 | Low | P0 |
| Emotion tag propagation | 0.5 | Low | P0 |
| Acoustic tail prompting (codec) | 2-3 | Medium | P1 |
| KV cache accumulation | 3-5 | High (torch.compile) | P2 |
| Adaptive chunk sizing | 1-2 | Low | P2 |

## Sources

### High Confidence (official docs, code inspection)
- Fish Speech S2-Pro codebase: `generate_long()`, `TTSInferenceEngine`, `DualARTransformer`, `DAC` codec (directly inspected)
- [Fish Audio S2 Technical Report](https://arxiv.org/html/2603.08823v2)
- [DAC codec overlap handling](https://huggingface.co/hance-ai/descript-audio-codec-44khz) -- 10% overlap with averaging for chunked decode
- [Cartesia context continuation API](https://docs.cartesia.ai/api-reference/tts/working-with-web-sockets/contexts) -- production pattern for prosody across chunks

### Medium Confidence (verified across multiple sources)
- [Qwen3-TTS-streaming Hann crossfade](https://github.com/rekuenkdr/Qwen3-TTS-streaming) -- 512-sample Hann window overlap-add, open source implementation
- [faster-qwen3-tts sliding window decode](https://github.com/andimarafioti/faster-qwen3-tts) -- 25-frame left context for codec continuity
- [Prosodic boundary-aware streaming TTS](https://arxiv.org/html/2603.06444) -- boundary markers + lookahead for prosody, March 2026
- [SpeakStream interleaved streaming](https://arxiv.org/html/2505.19206v1) -- KV cache accumulation for context, Apple ML Research
- [Deepgram text chunking for TTS](https://developers.deepgram.com/docs/text-chunking-for-tts-optimization) -- clause boundary splitting pattern
- [Fish Speech streaming latency issue #1020](https://github.com/fishaudio/fish-speech/issues/1020) -- root cause analysis of first-chunk latency

### Low Confidence (single source or unverified)
- [EmoSteer-TTS activation steering](https://arxiv.org/html/2508.03543v1) -- training-free emotion control via internal activations (not directly applicable to Fish Speech without research)
- [Picovoice streaming TTS blog](https://picovoice.ai/blog/streaming-text-to-speech-for-ai-agents/) -- general patterns, not Fish Speech specific
