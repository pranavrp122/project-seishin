# Requirements: Streaming Chunked Audio

**Defined:** 2026-04-12
**Core Value:** Users hear first audio within 500ms with no perceivable quality loss or choppiness

## v1 Requirements

### Text Splitting

- [x] **SPLIT-01**: System splits single-speaker text at clause/sentence boundaries (`.!?,;:--`)
- [x] **SPLIT-02**: First chunk targets 30-80 bytes for fast TTFA
- [x] **SPLIT-03**: Subsequent chunks target 100-200 bytes for quality
- [x] **SPLIT-04**: Minimum chunk size of 50 bytes enforced (below this, prosody degrades)
- [x] **SPLIT-05**: Force-split at max byte limit when no natural boundary exists

### Emotion Consistency

- [x] **EMOT-01**: Leading emotion tag (e.g., `[angry]`) extracted from input text
- [x] **EMOT-02**: Active emotion tag prepended to every chunk before generation
- [x] **EMOT-03**: Mid-text emotion transitions tracked and applied to correct chunks

### Audio Quality

- [x] **QUAL-01**: Equal-power crossfade at chunk boundaries eliminates clicks/pops/discontinuities
- [x] **QUAL-02**: Crossfade duration tuned to ~10-20ms (441-882 samples at 44.1kHz)
- [x] **QUAL-03**: Audio quality subjectively matches non-streaming output across all emotions
- [x] **QUAL-04**: PeakFilter post-FX applied consistently (per-chunk for streaming, full audio for non-streaming)

### Streaming Pipeline

- [x] **STRM-01**: TTFA < 500ms for typical dialogue lines (50-200 chars)
- [x] **STRM-02**: Audio segments yielded to client as each chunk completes
- [x] **STRM-03**: StreamingCrossfader buffers tail of previous chunk and blends with head of next
- [x] **STRM-04**: WAV header uses 0xFFFFFFFF sizes for streaming unknown length
- [x] **STRM-05**: Streaming encoding consistent (int16 PCM throughout, no float32 mismatch)

### Sub-Chunk Audio Streaming

- [ ] **SUBCHK-01**: generate_long yields partial VQ code tensors every N tokens during generation (not after full chunk)
- [ ] **SUBCHK-02**: DAC decoder produces valid audio from partial VQ token sequences (minimum 10 tokens)
- [ ] **SUBCHK-03**: DAC decoder state managed correctly across partial decode calls (no boundary artifacts)
- [ ] **SUBCHK-04**: TTFA < 200ms for typical dialogue lines (50-200 chars) with cached reference
- [ ] **SUBCHK-05**: Sub-chunk decode boundaries produce no audible artifacts within a text chunk
- [ ] **SUBCHK-06**: Existing between-chunk crossfader integrates correctly with sub-chunk streaming

### Robustness

- [ ] **RBST-01**: Context window managed -- old conversation turns truncated for long texts
- [ ] **RBST-02**: VRAM does not exceed current 10.7GB peak
- [ ] **RBST-03**: Non-streaming path continues to work unchanged (backward compatible)
- [ ] **RBST-04**: Compatible with existing INT8 W8A16 + torch.compile reduce-overhead

## v2 Requirements

### Advanced Quality

- **ADVQ-01**: Acoustic tail prompting -- feed previous chunk's last ~25 codec frames to DAC decoder
- **ADVQ-02**: Overlapped DAC decoding with extra context tokens at boundaries
- **ADVQ-03**: Adaptive chunk sizing based on emotion (shorter for high-energy, longer for low-energy)

### Performance

- **PERF-01**: CUDA graph recompilation mitigation (prompt length padding or caching)
- **PERF-02**: KV cache accumulation between chunks (avoid re-prefill)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Speculative decoding | Audio codebook tokens have low acceptance rates; 2-3 weeks for 1.3-1.7x |
| SGLang serving | Fundamentally different architecture, requires infrastructure change |
| WebSocket streaming | Chunked HTTP sufficient when full text submitted upfront |
| NLP-based splitting (spaCy) | Adds 50-100ms latency per split, regex sufficient for pre-split text |
| Multi-speaker streaming | Single voice only for this project |
| Model retraining | Working within existing S2-Pro weights |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SPLIT-01 | Phase 1 | Complete |
| SPLIT-02 | Phase 1 | Complete |
| SPLIT-03 | Phase 1 | Complete |
| SPLIT-04 | Phase 1 | Complete |
| SPLIT-05 | Phase 1 | Complete |
| EMOT-01 | Phase 1 | Complete |
| EMOT-02 | Phase 1 | Complete |
| EMOT-03 | Phase 1 | Complete |
| QUAL-01 | Phase 2 | Complete |
| QUAL-02 | Phase 2 | Complete |
| QUAL-03 | Phase 2 | Complete |
| QUAL-04 | Phase 2 | Complete |
| STRM-01 | Phase 2 | Complete |
| STRM-02 | Phase 2 | Complete |
| STRM-03 | Phase 2 | Complete |
| STRM-04 | Phase 2 | Complete |
| STRM-05 | Phase 2 | Complete |
| SUBCHK-01 | Phase 3 | Pending |
| SUBCHK-02 | Phase 3 | Pending |
| SUBCHK-03 | Phase 3 | Pending |
| SUBCHK-04 | Phase 3 | Pending |
| SUBCHK-05 | Phase 3 | Pending |
| SUBCHK-06 | Phase 3 | Pending |
| RBST-01 | Phase 4 | Pending |
| RBST-02 | Phase 4 | Pending |
| RBST-03 | Phase 4 | Pending |
| RBST-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-04-12*
*Last updated: 2026-04-12 after roadmap creation*
