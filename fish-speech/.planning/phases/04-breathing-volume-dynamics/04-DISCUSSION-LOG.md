# Phase 4: Breathing & Volume Dynamics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 04-breathing-volume-dynamics
**Areas discussed:** Breathing mechanism, Volume dynamics, Audio processing approach, A/B testing
**Mode:** --auto (all areas auto-selected, recommended options auto-chosen)

---

## Breathing Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Silence gap insertion | Insert 80-150ms silence at BreathingCue positions in audio post-processing | ✓ |
| [inhale] tag injection | Inject [inhale] tags in text (as originally specified in BRVL-01) | |
| Skip breathing entirely | Model generates breaths natively from reference audio | |

**User's choice:** Silence gap insertion (auto-selected)
**Notes:** [inhale] tags confirmed non-responsive in Phase 1 testing. Breath synthesis out of scope per anti-features. Silence gaps are the only viable mechanism.

---

## Volume Dynamics

| Option | Description | Selected |
|--------|-------------|----------|
| Numpy gain scaling | Simple gain multipliers on audio segments (0.85x aside, 1.1x emphasis) | ✓ |
| [low volume]/[volume up] tags | Text-level tag injection for model-driven volume | |
| Full post-FX with compression | Re-enable HumanismPostFX for dynamic range processing | |

**User's choice:** Numpy gain scaling (auto-selected)
**Notes:** Inline tags assumed non-responsive. Post-FX disabled due to quality degradation. Simple gain scaling avoids both issues.

---

## Audio Processing Approach

| Option | Description | Selected |
|--------|-------------|----------|
| New HumanismAudioProcessor class | Lightweight class in audio_processor.py, separate from post_fx.py | ✓ |
| Extend HumanismPostFX | Add silence/gain features to existing post-FX class | |
| Inline in inference engine | Add gain/silence logic directly in __init__.py | |

**User's choice:** New HumanismAudioProcessor class (auto-selected)
**Notes:** Post-FX is disabled and has quality issues. New class keeps concerns separated. Inline would clutter inference engine.

---

## A/B Testing

| Option | Description | Selected |
|--------|-------------|----------|
| Per-feature corpus generation | Toggle each feature independently, compare against current baseline | ✓ |
| Combined-only testing | Test all features together against baseline | |

**User's choice:** Per-feature corpus generation (auto-selected)
**Notes:** BRVL-05 requires independent A/B testing per feature.

---

## Claude's Discretion

- Exact silence duration for breathing gaps (80-150ms range)
- Gain multiplier values (guideline: 0.85x aside, 1.1x emphasis)
- Cosine ramp duration for gain transitions
- VolumeHint dataclass design
- humanism_hints flow through streaming loop

## Deferred Ideas

- Post-FX re-tuning with gentler parameters → Phase 5
- Breath sound synthesis → out of scope (anti-feature)
