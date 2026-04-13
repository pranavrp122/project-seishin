# Requirements: TTS Humanism (v2.0)

**Defined:** 2026-04-13
**Core Value:** TTS output sounds as natural and human-like as possible for AI companion use

## v2.0 Requirements

### Baseline Measurement

- [ ] **BASE-01**: Generate baseline recordings with current pipeline for A/B comparison (10+ diverse prompts)
- [ ] **BASE-02**: Measure F0 pitch variation using pyworld (voiced F0 std dev, contour shape)
- [ ] **BASE-03**: Measure pause distribution (location, duration, frequency) across test corpus
- [ ] **BASE-04**: Test model response to inline tags ([inhale], [slow], [fast], [pause]) and document effectiveness
- [ ] **BASE-05**: Establish adversarial test corpus (fragments, 50+ word sentences, numbers, questions, mixed emotion)

### Post-FX Chain (Audio Warmth & Presence)

- [ ] **WARM-01**: Low-shelf EQ at 250Hz adds body/warmth to voice
- [ ] **WARM-02**: High-shelf at 8kHz adds subtle air/shimmer
- [ ] **WARM-03**: Gentle compression (2:1 ratio, -20dB threshold) evens dynamics without pumping
- [ ] **WARM-04**: De-essing reduces sibilance (narrow cut at 6.5kHz)
- [ ] **WARM-05**: Asymmetric soft saturation adds even-harmonic analog warmth (tanh with quadratic asymmetry)
- [ ] **WARM-06**: Safety limiter prevents clipping after boosts
- [ ] **WARM-07**: Post-FX chain maintains streaming compatibility (no audible state-reset artifacts across chunks)
- [ ] **WARM-08**: Each post-FX effect has intensity parameter for A/B tuning

### Text Preprocessing & Pause Injection

- [ ] **PAUS-01**: Text preprocessor injects punctuation at clause boundaries for natural model-generated pauses
- [ ] **PAUS-02**: [pause]/[short pause] tag insertion at strategic points (sentence boundaries, before long clauses)
- [ ] **PAUS-03**: Pause duration varies with Gaussian jitter (+/-15-20%) to avoid robotic regularity
- [ ] **PAUS-04**: [slow]/[fast] tag injection for speech rate variation at emotional transition points
- [ ] **PAUS-05**: Text preprocessor produces per-chunk metadata (HumanismHints) for downstream audio processing
- [ ] **PAUS-06**: Text preprocessing adds < 10ms overhead to TTFA

### Breathing & Volume Dynamics

- [ ] **BRVL-01**: [inhale] tag injection before long phrases (15+ words), probability-based (not every phrase)
- [ ] **BRVL-02**: Breathing injection capped at max 1 per 3-5 sentences to avoid uncanny valley
- [ ] **BRVL-03**: [low volume] tag injection for asides/parentheticals, [volume up] for emphasis
- [ ] **BRVL-04**: Text-driven per-segment gain adjustment based on HumanismHints metadata
- [ ] **BRVL-05**: Each breathing/volume feature independently A/B tested and beats unmodified baseline

### Validation & Tuning

- [ ] **VALD-01**: Adversarial test corpus covers edge cases (fragments, long sentences, numbers, mixed-language, questions)
- [ ] **VALD-02**: 100+ diverse utterances generated and manually evaluated for naturalness
- [ ] **VALD-03**: Streaming-specific validation confirms no new artifacts at chunk boundaries
- [ ] **VALD-04**: Every humanism feature has 0.0-1.0 intensity dial for disable/tune capability
- [ ] **VALD-05**: Optimal parameter settings documented with rationale
- [ ] **VALD-06**: Regression baseline established (reference recordings + metrics for future comparison)

## v3+ Requirements (Deferred)

### Advanced Prosody

- **PROS-01**: Vocal fry / creaky voice via LoRA fine-tuning (requires model training, not post-processing)
- **PROS-02**: Content-word emphasis via POS tagging (requires spaCy dependency)
- **PROS-03**: Real-time prosody prediction model for dynamic emphasis

### Audio Enhancement

- **ENHC-01**: Room tone via convolution IR (A/B gate: add only if testing shows clear improvement)
- **ENHC-02**: Micro-pitch jitter for naturalness (high artifact risk, needs safe technique)

### LLM Integration

- **LLM-01**: LLM generates emotion tags inline based on semantic context
- **LLM-02**: LLM varies sentence structure for natural speech rhythm (short/long alternation)
- **LLM-03**: LLM inserts conversational markers (trailing off, self-correction patterns)

## Out of Scope (Anti-Features)

| Feature | Reason |
|---------|--------|
| Filler word injection (um, uh) | KTH research: misplaced fillers worse than none; anti-feature |
| Breathing sound synthesis | No convincing Python implementation; model generates breaths natively from reference audio |
| Rule-based pitch manipulation | Fights DualAR transformer's learned prosody from 10M+ hours; produces sing-song artifacts |
| Lip smacks / mouth sounds | Extremely sparse use case, high uncanny valley risk |
| Model retraining | Out of scope for this milestone; existing S2-Pro weights only |
| LLM sentence structure changes | Documented for v3+ but not implemented in this milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 1 | Pending |
| BASE-02 | Phase 1 | Pending |
| BASE-03 | Phase 1 | Pending |
| BASE-04 | Phase 1 | Pending |
| BASE-05 | Phase 1 | Pending |
| WARM-01 | Phase 2 | Pending |
| WARM-02 | Phase 2 | Pending |
| WARM-03 | Phase 2 | Pending |
| WARM-04 | Phase 2 | Pending |
| WARM-05 | Phase 2 | Pending |
| WARM-06 | Phase 2 | Pending |
| WARM-07 | Phase 2 | Pending |
| WARM-08 | Phase 2 | Pending |
| PAUS-01 | Phase 3 | Pending |
| PAUS-02 | Phase 3 | Pending |
| PAUS-03 | Phase 3 | Pending |
| PAUS-04 | Phase 3 | Pending |
| PAUS-05 | Phase 3 | Pending |
| PAUS-06 | Phase 3 | Pending |
| BRVL-01 | Phase 4 | Pending |
| BRVL-02 | Phase 4 | Pending |
| BRVL-03 | Phase 4 | Pending |
| BRVL-04 | Phase 4 | Pending |
| BRVL-05 | Phase 4 | Pending |
| VALD-01 | Phase 5 | Pending |
| VALD-02 | Phase 5 | Pending |
| VALD-03 | Phase 5 | Pending |
| VALD-04 | Phase 5 | Pending |
| VALD-05 | Phase 5 | Pending |
| VALD-06 | Phase 5 | Pending |

**Coverage:**
- v2.0 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0

---
*Requirements defined: 2026-04-13*
*Last updated: 2026-04-13 after roadmap creation*
