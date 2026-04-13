# Roadmap: TTS Humanism (v1.9)

## Overview

Make Fish Speech S2-Pro output sound like a person talking, not a machine reading. Five phases move from measurement through audio enhancement, text-level prosody, breathing/dynamics, and final validation. Each phase adds one layer of naturalness, A/B tested against baseline, with every feature gated by a 0.0-1.0 intensity dial. The guiding principle is "less is more" -- partially-humanized speech that is close-but-not-quite sounds worse than clean synthetic speech.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Baseline Measurement** - Quantify what the model already does before modifying anything
- [x] **Phase 2: Post-FX Chain** - Professional vocal chain for warmth, presence, and polish
- [x] **Phase 3: Text Preprocessor & Pauses** - Punctuation injection, pause tags, and speech rate variation via text-level manipulation
- [ ] **Phase 4: Breathing & Volume Dynamics** - Sparse breathing cues and per-segment volume variation for emotional range
- [ ] **Phase 5: Validation & Tuning** - Adversarial testing, parameter tuning, and regression baseline

## Phase Details

### Phase 1: Baseline Measurement
**Goal**: Quantitative and qualitative baseline of current model output exists, enabling data-driven decisions for all subsequent phases
**Depends on**: Nothing (first phase)
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04, BASE-05
**Success Criteria** (what must be TRUE):
  1. Baseline recordings exist for 10+ diverse prompts covering dialogue, narration, questions, exclamations, and long passages
  2. F0 pitch statistics (voiced F0 std dev, contour shapes) are computed and saved for baseline corpus
  3. Pause distribution (location, duration, frequency) is measured and documented across baseline corpus
  4. Inline tag responsiveness ([inhale], [slow], [fast], [pause]) is tested and documented with clear pass/fail per tag
  5. Adversarial test corpus exists with fragments, 50+ word sentences, numbers, questions, and mixed-emotion inputs
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Generate baseline + adversarial audio corpora (BASE-01, BASE-05)
- [x] 01-02-PLAN.md — Test inline tag responsiveness (BASE-04)
- [x] 01-03-PLAN.md — F0 pitch + pause distribution analysis (BASE-02, BASE-03)

### Phase 2: Post-FX Chain
**Goal**: Every utterance sounds warmer, more present, and more polished through a professional audio processing chain, with zero changes to text or generation pipeline
**Depends on**: Phase 1
**Requirements**: WARM-01, WARM-02, WARM-03, WARM-04, WARM-05, WARM-06, WARM-07, WARM-08
**Success Criteria** (what must be TRUE):
  1. A/B comparison against Phase 1 baseline shows audible improvement in warmth and presence across all test prompts
  2. Post-FX output has no audible pumping, distortion, or sibilance artifacts on any baseline corpus utterance
  3. Streaming mode produces no audible state-reset artifacts at chunk boundaries with post-FX applied
  4. Each effect (EQ, compression, saturation, de-essing, limiter) can be independently enabled/disabled and intensity-tuned via 0.0-1.0 parameter
  5. Post-FX chain does not clip output audio on any test utterance (limiter prevents it)
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Create HumanismPostFX class with all 6 effects and per-effect intensity controls (WARM-01, WARM-02, WARM-03, WARM-04, WARM-05, WARM-06, WARM-08)
- [x] 02-02-PLAN.md — Integrate into inference engine with stateful streaming + A/B corpus generation (WARM-07, WARM-08)

### Phase 3: Text Preprocessor & Pauses
**Goal**: Speech rhythm sounds natural through text-level punctuation injection, pause tags, and speech rate variation that guide the model's existing prosody capabilities
**Depends on**: Phase 2
**Requirements**: PAUS-01, PAUS-02, PAUS-03, PAUS-04, PAUS-05, PAUS-06
**Success Criteria** (what must be TRUE):
  1. Long clauses without punctuation receive injected commas/periods at natural boundaries, producing model-generated pauses
  2. Pause durations vary audibly across a single utterance (no metronomic regularity) due to Gaussian jitter
  3. [slow] and [fast] tags are inserted at emotional transition points, producing audible speech rate variation
  4. Per-chunk HumanismHints metadata is generated and available for downstream audio processing (Phase 4)
  5. Text preprocessing adds less than 10ms to time-to-first-audio
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — TextPreprocessor module with clause injection, [slow] tags, pause hints, breathing cues (PAUS-01, PAUS-02, PAUS-03, PAUS-04, PAUS-05)
- [x] 03-02-PLAN.md — Integrate into inference pipeline + verify <10ms overhead (PAUS-06)

### Phase 4: Breathing & Volume Dynamics
**Goal**: Sparse breathing cues and volume variation add the final layer of humanness that crosses the line from "good TTS" to "forgot it was a machine"
**Depends on**: Phase 3
**Requirements**: BRVL-01, BRVL-02, BRVL-03, BRVL-04, BRVL-05
**Success Criteria** (what must be TRUE):
  1. [inhale] tags appear before long phrases (15+ words) at a probability-based rate, producing audible breaths that sound natural
  2. Breathing injection never exceeds 1 per 3-5 sentences across any test corpus utterance
  3. Asides and parentheticals are quieter, emphasis points are louder, producing audible dynamic range
  4. Each breathing/volume sub-feature independently A/B tested against unmodified baseline and documented as pass/fail
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Validation & Tuning
**Goal**: The complete humanism stack is validated end-to-end on diverse inputs, parameters are tuned to optimal settings, and a regression baseline is locked for future changes
**Depends on**: Phase 4
**Requirements**: VALD-01, VALD-02, VALD-03, VALD-04, VALD-05, VALD-06
**Success Criteria** (what must be TRUE):
  1. Adversarial test corpus (fragments, long sentences, numbers, mixed-language, questions) produces no new artifacts compared to Phase 1 baseline
  2. 100+ diverse utterances generated and manually evaluated, with naturalness ratings documented
  3. Streaming pipeline with all humanism features produces no new artifacts at chunk boundaries
  4. Every humanism feature has a working 0.0-1.0 intensity dial that can fully disable or tune the feature
  5. Optimal parameter settings are documented with rationale, and regression reference recordings are saved
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Baseline Measurement | 3/3 | Complete | 2026-04-13 |
| 2. Post-FX Chain | 2/2 | Complete | 2026-04-13 |
| 3. Text Preprocessor & Pauses | 2/2 | Complete | 2026-04-13 |
| 4. Breathing & Volume Dynamics | 0/0 | Not started | - |
| 5. Validation & Tuning | 0/0 | Not started | - |
