---
phase: 02-post-fx-chain
plan: 01
subsystem: audio-processing
tags: [pedalboard, numpy, dsp, eq, compression, saturation, post-fx]

# Dependency graph
requires:
  - phase: 01-baseline-measurement
    provides: baseline F0/pause metrics and analysis scripts for A/B comparison
provides:
  - HumanismPostFX class with 6-effect vocal processing chain
  - PostFXConfig dataclass with per-effect 0.0-1.0 intensity controls
  - Stateful streaming support via reset=False pedalboard processing
affects: [02-post-fx-chain plan 02 integration, 05-validation A/B testing]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-request stateful pedalboard, asymmetric numpy saturation, Clipping not Limiter]

key-files:
  created:
    - fish_speech/utils/post_fx.py
    - tests/test_post_fx.py
  modified: []

key-decisions:
  - "Used Clipping(threshold_db=-0.1) instead of Limiter per pedalboard issue #282 (Limiter normalizes quiet audio)"
  - "Saturation applied outside pedalboard chain as numpy post-process (pedalboard lacks asymmetric saturation plugin)"
  - "First process() call uses reset=True, subsequent calls use reset=False for streaming state continuity"

patterns-established:
  - "Per-request HumanismPostFX instances for thread safety (not class-level shared state)"
  - "Effects with intensity 0.0 are omitted from pedalboard chain entirely (not just set to neutral)"
  - "Final np.clip(-1.0, 1.0) as redundant safety after all processing"

requirements-completed: [WARM-01, WARM-02, WARM-03, WARM-04, WARM-05, WARM-06, WARM-08]

# Metrics
duration: 2min
completed: 2026-04-13
---

# Phase 02 Plan 01: HumanismPostFX Summary

**6-effect vocal chain (de-ess, EQ low/high, compression, asymmetric saturation, safety clipper) with per-effect 0.0-1.0 intensity controls using pedalboard + numpy**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-13T21:26:59Z
- **Completed:** 2026-04-13T21:29:15Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files created:** 2

## Accomplishments
- HumanismPostFX class with full 6-stage vocal processing chain matching industry-standard order
- PostFXConfig dataclass with 5 per-effect intensity floats all defaulting to 1.0
- Asymmetric tanh + quadratic saturation producing even-harmonic warmth
- Stateful streaming via pedalboard process(reset=False) for chunk-boundary continuity
- 7 unit tests covering defaults, bypass, shape, bounds, asymmetry, streaming, and per-effect bypass

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Failing tests** - `f6dc400` (test)
2. **Task 1 GREEN: HumanismPostFX implementation** - `15525ed` (feat)

## Files Created/Modified
- `fish_speech/utils/post_fx.py` - HumanismPostFX class and PostFXConfig dataclass (169 lines)
- `tests/test_post_fx.py` - 7 unit tests for FX chain behavior (115 lines)

## Decisions Made
- Used Clipping(threshold_db=-0.1) instead of Limiter per pedalboard GitHub issue #282 -- Limiter normalizes quiet audio to [-1, 1] which destroys dynamic range
- Saturation applied as numpy post-process after pedalboard chain since pedalboard has no asymmetric saturation plugin
- First process() call resets IIR state (reset=True), subsequent calls maintain state (reset=False) for streaming continuity

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

- pytest was not installed in the project venv; installed via `uv pip install pytest` (test infrastructure setup, not a plan deviation)

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- HumanismPostFX is ready for integration into TTSInferenceEngine (Plan 02)
- Per-request instantiation pattern documented for thread-safe streaming
- Compressor state continuity across streaming chunks needs empirical validation during integration (flagged in STATE.md)

## Self-Check: PASSED

- fish_speech/utils/post_fx.py: FOUND
- tests/test_post_fx.py: FOUND
- 02-01-SUMMARY.md: FOUND
- Commit f6dc400 (RED): FOUND
- Commit 15525ed (GREEN): FOUND

---
*Phase: 02-post-fx-chain*
*Completed: 2026-04-13*
