---
phase: 04-breathing-volume-dynamics
plan: 02
subsystem: inference-engine
tags: [audio-processor, breathing, volume-dynamics, inference-integration, ab-testing, tts]

# Dependency graph
requires:
  - phase: 04-breathing-volume-dynamics
    plan: 01
    provides: HumanismAudioProcessor, AudioProcessorConfig, VolumeHint dataclass
provides:
  - Audio processor integrated at all 3 inference streaming paths (volume) and final audio (breathing)
  - A/B test script for independent breathing gap and volume dynamics validation
affects: [05-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-request-audio-processor-instantiation, cumulative-sample-tracking, fractional-region-rms-comparison]

key-files:
  created: [tools/tts_baseline/test_breathing_volume.py]
  modified: [fish_speech/inference_engine/__init__.py]

key-decisions:
  - "Volume dynamics applied during streaming (process_volume at 3 audio paths), breathing applied to final audio only (process_breathing changes array length)"
  - "Cumulative audio sample counter tracks position across streaming chunks for accurate char-to-sample mapping"
  - "post_fx import and all references removed entirely, replaced by audio_processor"
  - "A/B test uses fractional region RMS comparison for volume, silence gap counting for breathing"

patterns-established:
  - "Per-request HumanismAudioProcessor instantiation with config, hints, text_length, sample_rate"
  - "Cumulative sample offset tracking for streaming volume dynamics"
  - "Independent sub-feature A/B testing with conservative pass/fail thresholds"

requirements-completed: [BRVL-01, BRVL-02, BRVL-03, BRVL-04, BRVL-05]

# Metrics
duration: 3min
completed: 2026-04-14
---

# Phase 4 Plan 2: Inference Integration & A/B Testing Summary

**HumanismAudioProcessor wired into inference engine at all 3 streaming audio paths (volume gain) and final concatenation (breathing silences), with independent A/B test script for each sub-feature**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T00:26:04Z
- **Completed:** 2026-04-14T00:29:40Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Replaced dead post_fx import and code with HumanismAudioProcessor import and instantiation
- process_volume() applied at all 3 streaming audio paths (sub-chunk partial, sub-chunk final, non-sub-chunk) with cumulative sample counter
- process_breathing() applied once on final concatenated audio before the code=final yield
- A/B test script with 3 breathing tests (long phrase, short phrase, multi-sentence cap) and 3 volume tests (parenthetical aside, exclamation emphasis, em-dash aside)
- Conservative pass/fail thresholds: silence gap count for breathing, fractional region RMS ratio for volume

## Task Commits

Each task was committed atomically:

1. **Task 1: Integrate HumanismAudioProcessor into inference engine** - `0a396b6` (feat)
2. **Task 2: Create A/B testing script for breathing and volume features** - `ad60b46` (feat)

## Files Created/Modified
- `fish_speech/inference_engine/__init__.py` - Replaced post_fx import/code with audio_processor import, instantiation, 3x process_volume calls with cumulative_audio_samples tracking, 1x process_breathing on final audio
- `tools/tts_baseline/test_breathing_volume.py` - New file: 6 A/B test cases (3 breathing, 3 volume), generate_audio via TTS API, count_silence_gaps and compute_rms measurement functions, markdown report and JSON output

## Decisions Made
- Volume dynamics during streaming, breathing on final only (array length change is unsafe for streaming offset tracking)
- Cumulative sample counter for position mapping accuracy across streaming chunks
- Removed post_fx entirely (import, code, comments) since it was already disabled
- A/B test thresholds kept conservative (any measurable effect counts as pass)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

To run A/B tests: start TTS server at http://127.0.0.1:8080, then run `python tools/tts_baseline/test_breathing_volume.py`. Results output to `/home/prana/tts-test/outputs/breathing_volume_tests/`.

## Next Phase Readiness
- All Phase 4 code complete: audio_processor.py (plan 01) + inference integration (plan 02)
- A/B test script ready for validation in Phase 5
- No new dependencies added

## Self-Check: PASSED

- All created/modified files exist on disk
- All task commits found in git history (0a396b6, ad60b46)
- Inference engine imports and parses correctly
- A/B test script parses correctly (ast.parse succeeds)

---
*Phase: 04-breathing-volume-dynamics*
*Completed: 2026-04-14*
