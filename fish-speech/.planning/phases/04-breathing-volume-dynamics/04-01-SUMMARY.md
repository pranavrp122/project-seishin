---
phase: 04-breathing-volume-dynamics
plan: 01
subsystem: audio
tags: [numpy, audio-processing, breathing, volume-dynamics, cosine-ramp, tts]

# Dependency graph
requires:
  - phase: 03-text-preprocessor-pauses
    provides: TextPreprocessor with HumanismHints, BreathingCue, PauseHint dataclasses
provides:
  - VolumeHint dataclass and detection in TextPreprocessor.preprocess()
  - HumanismAudioProcessor class with breathing silence insertion and volume gain scaling
  - AudioProcessorConfig with per-feature toggles
affects: [04-02, 05-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [stateless-position-based-audio-processing, cosine-ramp-transitions, linear-char-to-sample-mapping]

key-files:
  created: [fish_speech/utils/audio_processor.py]
  modified: [fish_speech/utils/text_preprocessor.py]

key-decisions:
  - "Omitted ALL CAPS volume detection to avoid false positives on common 3-letter words like THE"
  - "Linear char-to-sample mapping for position estimation (D-14); sufficient for volume regions and breathing"
  - "Breathing cue probability rolled once at init (not per-segment) to prevent inconsistent behavior across streaming chunks"
  - "process_breathing() operates on final concatenated audio only; process_volume() is streaming-safe"

patterns-established:
  - "Cosine ramp transitions: sin^2/cos^2 fade-in/fade-out for all audio gain changes and silence insertions"
  - "Stateless audio processor: instantiated per-request with HumanismHints, no IIR filter state"
  - "Reverse-order insertion: process breathing cues in reverse to avoid position shifting"

requirements-completed: [BRVL-01, BRVL-02, BRVL-03, BRVL-04]

# Metrics
duration: 3min
completed: 2026-04-14
---

# Phase 4 Plan 1: Breathing & Volume Core Modules Summary

**VolumeHint detection in TextPreprocessor plus HumanismAudioProcessor for breathing silence insertion and volume gain scaling with cosine ramps**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T00:19:25Z
- **Completed:** 2026-04-14T00:22:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- VolumeHint dataclass and detection logic added to TextPreprocessor (parenthetical asides 0.85x, em-dash asides 0.85x, exclamation emphasis 1.1x)
- HumanismAudioProcessor created with streaming-safe process_volume() and final-audio process_breathing()
- Breathing cue probability rolled once at init with cap of 1 per 4 sentences to prevent over-insertion
- Cosine ramp transitions on all gain changes and silence insertions to prevent click artifacts

## Task Commits

Each task was committed atomically:

1. **Task 1: Add VolumeHint dataclass and detection to TextPreprocessor** - `964ddbd` (feat)
2. **Task 2: Create HumanismAudioProcessor with breathing silence and volume gain** - `3376ecf` (feat)

## Files Created/Modified
- `fish_speech/utils/text_preprocessor.py` - Added VolumeHint dataclass, volume_hints field to HumanismHints, regex patterns for aside/emphasis detection, _generate_volume_hints method, enable_volume_hints config toggle
- `fish_speech/utils/audio_processor.py` - New file: AudioProcessorConfig dataclass, HumanismAudioProcessor class with process_volume(), process_breathing(), cosine ramp helpers, breathing cue probability rolling

## Decisions Made
- Omitted ALL CAPS detection (plan note: too aggressive, 3-letter caps words like "THE" would false-positive)
- Used linear char-to-sample mapping rather than phoneme-level alignment (sufficient accuracy for volume regions)
- Breathing cue probability rolled once at init, not per-segment, to prevent inconsistent behavior in streaming
- process_breathing() restricted to final audio only (changes array length, unsafe for streaming)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- VolumeHint and HumanismAudioProcessor ready for integration into inference pipeline (Plan 04-02)
- Both modules importable and unit-testable without inference engine running
- No new dependencies added (numpy only, already in environment)

---
*Phase: 04-breathing-volume-dynamics*
*Completed: 2026-04-14*
