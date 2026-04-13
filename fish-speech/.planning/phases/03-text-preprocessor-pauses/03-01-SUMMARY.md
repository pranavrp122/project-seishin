---
phase: 03-text-preprocessor-pauses
plan: 01
subsystem: text-processing
tags: [regex, tdd, dataclasses, text-preprocessing, pause-injection, tts-humanism]

requires:
  - phase: 02-post-fx-chain
    provides: "HumanismPostFX pattern (dataclass config + processor class)"
provides:
  - "TextPreprocessor class for text-level preprocessing"
  - "PreprocessorConfig with 6 feature toggles"
  - "HumanismHints dataclass for Phase 4 consumption"
  - "PauseHint, RateHint, BreathingCue metadata types"
  - "Clause boundary comma injection at conjunctions"
  - "[slow] tag insertion before emotion-tagged sentences"
  - "Pause hint generation with Gaussian jitter"
  - "Breathing cue generation for 15+ word phrases"
affects: [04-breathing-volume, pipeline-integration]

tech-stack:
  added: []
  patterns: ["Stateless text preprocessor returning (text, metadata) tuple", "Feature toggle dataclass config", "TDD with 36 unit tests"]

key-files:
  created:
    - fish_speech/utils/text_preprocessor.py
    - tests/test_text_preprocessor.py
  modified: []

key-decisions:
  - "Stdlib only (re, random, dataclasses) -- zero new dependencies"
  - "Local _EMOTION_TAG regex copy to avoid circular import with inference.py"
  - "Breathing cue probability tiers: 0.3 (15-20 words), 0.6 (20-30), 0.9 (30+)"
  - "Single comma injection per long span -- no multi-injection to avoid over-punctuation"

patterns-established:
  - "Stateless preprocessor: preprocess(text) -> (modified_text, HumanismHints)"
  - "HumanismHints as interface contract between Phase 3 (text) and Phase 4 (audio)"
  - "Feature toggles via bool fields on config dataclass"

requirements-completed: [PAUS-01, PAUS-02, PAUS-03, PAUS-04, PAUS-05]

duration: 3min
completed: 2026-04-13
---

# Phase 3 Plan 01: TextPreprocessor Summary

**Rule-based text preprocessor with clause comma injection, [slow] tags, Gaussian-jittered pause hints, and breathing cues -- TDD with 36 passing tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-13T23:07:44Z
- **Completed:** 2026-04-13T23:10:40Z
- **Tasks:** 1 (TDD feature with RED/GREEN phases)
- **Files created:** 2

## Accomplishments
- TextPreprocessor injects commas at clause boundaries (coordinating/subordinating conjunctions) in 8+ word unpunctuated spans
- [slow] tags automatically prepended before emotion-tagged sentences (no double [slow])
- Pause hints generated at all punctuation with Gaussian jitter clamped to [0.5x, 1.5x] base durations
- Breathing cues mark phrases of 15+ words with tiered probability (0.3/0.6/0.9)
- All 6 features independently toggleable via PreprocessorConfig booleans
- HumanismHints dataclass ready as Phase 4 interface contract

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **RED: Failing tests** - `3fc7747` (test) -- 36 test cases for all preprocessor behaviors
2. **GREEN: Implementation** - `800a87b` (feat) -- TextPreprocessor module passing all tests

## Files Created/Modified
- `fish_speech/utils/text_preprocessor.py` - TextPreprocessor class with PreprocessorConfig, HumanismHints, PauseHint, RateHint, BreathingCue dataclasses
- `tests/test_text_preprocessor.py` - 36 unit tests covering dataclasses, clause injection, [slow] tags, pause hints, breathing cues, feature toggles, integration

## Decisions Made
- Stdlib only (re, random, dataclasses) -- no numpy, no spacy, no external deps
- Local _EMOTION_TAG regex copy (identical to inference.py) to avoid circular import
- Breathing cue probability tiers based on word count rather than fixed 1.0
- Single comma injection per span to avoid over-punctuation (coordinating conjunctions tried first, then subordinating)
- Double-punctuation cleanup regex runs after every injection pass

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Known Stubs

None -- all data flows are wired and functional.

## Next Phase Readiness
- TextPreprocessor ready for pipeline integration (will be called before split_text_into_chunks)
- HumanismHints ready for Phase 4 consumption (breathing cues, pause hints)
- All feature toggles defaulting to enabled -- can be disabled per-request via config

## Self-Check: PASSED

- fish_speech/utils/text_preprocessor.py: FOUND
- tests/test_text_preprocessor.py: FOUND
- .planning/phases/03-text-preprocessor-pauses/03-01-SUMMARY.md: FOUND
- Commit 3fc7747 (RED): FOUND
- Commit 800a87b (GREEN): FOUND

---
*Phase: 03-text-preprocessor-pauses*
*Completed: 2026-04-13*
