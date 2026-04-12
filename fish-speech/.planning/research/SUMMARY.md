# Research Summary: Streaming Chunked Audio

## Key Findings

### Text Splitting
- **Current code doesn't split single-speaker text at all** — `split_text_by_speaker()` returns empty, falls through to single batch
- Regex-based clause/sentence boundary splitting is the practical winner (no NLP latency)
- Split priority: sentence boundaries (`.!?`) > clause boundaries (`,;:--`) > force-split at max bytes
- Minimum viable chunk: ~50 bytes / ~10 words (below this, prosody degrades)
- First chunk target: ~30-80 bytes for <500ms TTFA
- Subsequent chunks: ~100-200 bytes (TTFA less critical, quality benefits from larger context)

### Emotion Tag Propagation
- Prepend active emotion tag (e.g., `[angry]`) to every chunk — simple string manipulation
- Fish Speech treats tags as inline text instructions, not persistent state
- Handle mid-text emotion transitions by tracking most recently active tag
- 93.3% tag activation rate in S2-Pro — repeating tags produces consistent prosody, not escalating

### Crossfade/Overlap-Add
- **Current code does bare `np.concatenate(segments)` with zero overlap handling** — root cause of choppiness
- Equal-power (sin²) crossfade at 10-20ms (441-882 samples at 44.1kHz) is the standard fix
- DAC hop_length = 512 samples (~11.6ms) — natural alignment for overlap width
- StreamingCrossfader pattern: buffer tail of previous chunk, blend with head of next before yielding
- F5-TTS uses 150ms crossfade, Qwen3-TTS uses 1024 samples (~23ms at 44.1kHz)

### DAC Decoder Specifics
- **DAC is causal** (`causal=True`) — no lookahead, start of each chunk is valid
- Convolutional receptive field extends beyond single tokens — boundary artifacts from zero-padding
- `from_indices()` has NO overlap handling, NO windowing
- DAC PR #96 proposes equal-power crossfade at hop_length overlap
- Overlapped decoding (extra context tokens on each side) produces results identical to full-sequence

### Acoustic Tail Prompting (Differentiator)
- Feed previous chunk's last ~25 codec frames as context when decoding next chunk via DAC
- Provides smoother transitions than crossfade alone (operates at codec level)
- Complementary to audio-level crossfade — addresses decoder context, not just waveform continuity

### Context Management
- Conversation history already carries context between chunks (existing `generate_long` behavior)
- **Context grows unboundedly** — overflow at ~3000-3500 tokens with max_seq_len=4096
- Need context truncation/windowing for long texts (keep last 2-3 chunks)
- Variable prompt lengths cause CUDA graph recompilation (100-500ms per new shape)

### Architecture
- Zero new dependencies needed
- Only 3 files need modification: `inference.py`, `__init__.py`, `inference_wrapper`
- Each codec token = 2048 audio samples (~46.4ms at 44.1kHz)
- 25 tokens produce ~1.16s of playable audio — plenty for client to start playing
- TTFA ~392ms achievable with 30-byte first chunk at 80 tok/s

### WAV Streaming
- Set RIFF/data chunk sizes to `0xFFFFFFFF` for unknown length streaming
- Fix existing encoding mismatch: segments yielded as int16, final as float32
- Keep chunked HTTP (existing `StreamResponse`) — WebSocket unnecessary

### Fish Speech GitHub Issues
- Issue #1020: First chunk latency scales with text, `generate()` blocks until complete — closed "not planned"
- Issue #836: Voice inconsistency between chunks with small chunks
- Discussion #692: Maintainer says "generate all tokens needed because requires context"
- Fish Audio production achieves ~100ms TTFA with SGLang + H200 (different architecture)

## Cross-Cutting Concerns

| Concern | Impact | Mitigation |
|---------|--------|------------|
| Context overflow | Later chunks fail | Truncate to last 2-3 turns |
| CUDA graph recompilation | 100-500ms latency spikes | Pad prompts to fixed lengths or accept the cost |
| Emotion drift | Neutral prosody in later chunks | Prepend emotion tag to every chunk |
| DAC boundary artifacts | Audible clicks/pops | Crossfade + optional acoustic tail prompting |
| Buffer underrun | Silence gaps during playback | Pre-buffer first chunk, larger subsequent chunks |

## Recommended Implementation Order

1. **Clause-aware text splitter** with emotion tag propagation — highest leverage
2. **Equal-power crossfade** at ~20ms in audio concatenation — fixes choppiness
3. **Streaming crossfader** for real-time segment yielding
4. **WAV header fix** for streaming (0xFFFFFFFF sizes)
5. **Context window management** — truncate old turns for long texts
6. **Acoustic tail prompting** at DAC decoder level — quality improvement
7. **TTFA measurement and tuning** — empirical first-chunk size optimization

---
*Synthesized from 7 parallel research agents, 2026-04-12*
