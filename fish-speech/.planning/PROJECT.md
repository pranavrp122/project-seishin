# Streaming Chunked Audio for Fish Speech S2-Pro

## What This Is

A streaming audio emission system for Fish Speech S2-Pro TTS that splits text into small chunks, generates audio per chunk, and emits audio as soon as each chunk is ready. Reduces time-to-first-audio (TTFA) from ~1.5s to <500ms while maintaining the current audio quality and emotional consistency.

## Core Value

Users hear the first audio within 500ms of submitting text, with no perceivable quality loss or choppiness at chunk boundaries.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Small-chunk text splitting with intelligent boundary detection
- [ ] Per-chunk audio generation with context carryover from previous chunks
- [ ] Streaming audio emission (first chunk plays while remaining chunks generate)
- [ ] Crossfade/overlap-add at chunk boundaries to eliminate choppiness
- [ ] Emotion tag propagation across chunks (e.g., [angry] applies to all chunks)
- [ ] TTFA < 500ms for typical dialogue lines
- [ ] Audio quality parity with current non-streaming output
- [ ] Compatible with existing INT8 W8A16 + torch.compile + reduce-overhead pipeline

### Out of Scope

- Speculative decoding — research-stage for audio codebooks, high engineering cost for uncertain gains
- LoRA fine-tuning — separate initiative, not required for streaming
- Model architecture changes — working within existing DualAR transformer
- Multi-speaker streaming — single voice only

## Context

- Fish Speech S2-Pro: DualAR transformer (36 layers, 2560 dim) + DAC codec decoder
- Current TTFA: ~1.5s avg (measured with streaming API, but text fits single chunk)
- Token generation: ~80 tok/s with INT8 W8A16 + torch.compile reduce-overhead
- chunk_length parameter already exists (controls max_bytes per text batch)
- Streaming API endpoint already exists (yields header + segments)
- Previous attempt at chunked audio resulted in choppiness at boundaries
- Reference audio: 17.27s clip, encoded to 372 semantic tokens
- Hardware: RTX 5090, 32GB GDDR7, CUDA 13.0, PyTorch 2.8.0+cu128

## Constraints

- **Quality**: No perceivable degradation vs current non-streaming output
- **Architecture**: Must work within existing inference pipeline (no model retraining)
- **VRAM**: Must not exceed current 10.7GB peak
- **Compatibility**: Must preserve torch.compile reduce-overhead + INT8 quantization

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Skip speculative decoding | Audio codebook tokens have lower acceptance rates than text; 2-3 weeks engineering for 1.3-1.7x gain | — Pending |
| Focus on chunk streaming first | Biggest TTFA improvement with least engineering risk | — Pending |

## Current Milestone: v2.0 TTS Humanism

**Goal:** Make Fish Speech TTS engine output sound as natural and human-like as possible through engine-side modifications only

**Target features:**
- Research how humans actually speak (rhythm, breath, micro-pauses, pitch variation, vocal fry, trailing off)
- Dynamic pause/delay injection at punctuation and clause boundaries
- Prosody enhancements (speech rate variation, emphasis patterns, natural cadence)
- Breathing and filler sound evaluation (implement or document skip rationale)
- Post-processing for warmth/presence (EQ, subtle compression, room tone)
- Any other TTS-engine-side humanism techniques discovered during research

**Scope boundary:** TTS engine modifications only. LLM sentence structure changes documented for future milestone but not implemented here.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-13 after milestone v2.0 start*
