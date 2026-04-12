# Roadmap: Streaming Chunked Audio

## Overview

Transform Fish Speech S2-Pro from a batch-generates-everything-then-returns model into a chunk-streaming pipeline. Phase 1 builds the text splitter and emotion tag propagation (input side). Phase 2 wires up per-chunk generation, crossfade stitching, and streaming emission (output side). Phase 3 hardens the pipeline for production: context management, VRAM bounds, backward compatibility, and torch.compile compatibility.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Text Splitting & Emotion Propagation** - Chunk text at clause/sentence boundaries with emotion tag carryover
- [ ] **Phase 2: Streaming Pipeline & Audio Quality** - Per-chunk generation, crossfade stitching, and streaming segment emission
- [ ] **Phase 3: Robustness & Validation** - Context management, VRAM bounds, backward compat, TTFA validation

## Phase Details

### Phase 1: Text Splitting & Emotion Propagation
**Goal**: Input text is split into correctly-sized chunks with emotion tags preserved, ready for per-chunk generation
**Depends on**: Nothing (first phase)
**Requirements**: SPLIT-01, SPLIT-02, SPLIT-03, SPLIT-04, SPLIT-05, EMOT-01, EMOT-02, EMOT-03
**Success Criteria** (what must be TRUE):
  1. A multi-sentence input is split into 2+ chunks at natural clause/sentence boundaries
  2. First chunk is 30-80 bytes; subsequent chunks are 100-200 bytes
  3. Text with no natural boundary within max bytes is force-split without crashing
  4. An input like "[angry] You betrayed me. I trusted you." produces chunks that each start with [angry]
  5. An input with mid-text emotion change (e.g., "[angry] Stop! [sad] I'm sorry.") assigns correct tags to each chunk
**Plans**: TBD

Plans:
- [ ] 01-01: TBD
- [ ] 01-02: TBD

### Phase 2: Streaming Pipeline & Audio Quality
**Goal**: Users hear the first audio chunk within 500ms, with seamless crossfaded boundaries and consistent encoding
**Depends on**: Phase 1
**Requirements**: STRM-01, STRM-02, STRM-03, STRM-04, STRM-05, QUAL-01, QUAL-02, QUAL-03, QUAL-04
**Success Criteria** (what must be TRUE):
  1. First audio segment is yielded to the client in under 500ms for a typical 50-200 char input
  2. Chunk boundaries have no audible clicks, pops, or discontinuities (crossfade applied)
  3. Streaming audio is subjectively indistinguishable from current non-streaming output
  4. WAV header uses 0xFFFFFFFF sizes and all segments use consistent int16 PCM encoding
  5. PeakFilter post-FX is applied per-chunk in streaming mode
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD
- [ ] 02-03: TBD

### Phase 3: Robustness & Validation
**Goal**: Streaming pipeline handles edge cases without exceeding resource limits and coexists with the existing non-streaming path
**Depends on**: Phase 2
**Requirements**: RBST-01, RBST-02, RBST-03, RBST-04
**Success Criteria** (what must be TRUE):
  1. A 2000+ character input generates audio without context overflow or degraded output on later chunks
  2. Peak VRAM stays at or below 10.7GB during streaming generation
  3. Non-streaming API requests produce identical output to pre-change behavior (backward compatible)
  4. INT8 W8A16 quantization and torch.compile reduce-overhead mode remain functional with streaming
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Text Splitting & Emotion Propagation | 0/0 | Not started | - |
| 2. Streaming Pipeline & Audio Quality | 0/0 | Not started | - |
| 3. Robustness & Validation | 0/0 | Not started | - |
