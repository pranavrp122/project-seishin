---
phase: 02-streaming-pipeline-audio-quality
plan: 02
subsystem: audio
tags: [wav-header, struct-pack, streaming, crossfader, inference-pipeline, int16-pcm]

requires:
  - phase: 02-streaming-pipeline-audio-quality
    plan: 01
    provides: "StreamingCrossfader class with process() and flush() for equal-power sin^2 blending"
provides:
  - "Streaming-compatible WAV header with 0xFFFFFFFF sizes (44 bytes)"
  - "Crossfader wired into TTSInferenceEngine.inference() streaming path"
  - "Integration test suite verifying WAV header, crossfader-int16 compatibility, and streaming sequence"
affects: [streaming-pipeline, audio-quality, inference-wrapper]

tech-stack:
  added: []
  patterns: [struct-pack-wav-header, conditional-crossfader-instantiation, crossfade-then-yield]

key-files:
  created:
    - tests/test_streaming_integration.py
  modified:
    - fish_speech/inference_engine/utils.py
    - fish_speech/inference_engine/__init__.py

key-decisions:
  - "Crossfader instantiated only when req.streaming is True -- non-streaming path is zero-cost"
  - "Raw (uncrossfaded) segments still appended for final np.concatenate -- backward compatible final audio"
  - "struct.pack replaces wave module for WAV header -- explicit byte control, no io/wave dependency"

patterns-established:
  - "Conditional crossfader: instantiate per-request based on streaming flag, None-check gates all crossfade logic"
  - "WAV streaming header: 0xFFFFFFFF for both RIFF and data chunk sizes signals unknown length to decoders"

requirements-completed: [STRM-01, STRM-02, STRM-04, STRM-05, QUAL-03, QUAL-04]

duration: 2min
completed: 2026-04-12
---

# Phase 02 Plan 02: Streaming Pipeline Wiring Summary

**Streaming WAV header with 0xFFFFFFFF sizes and crossfader wired into inference() for per-chunk emission with crossfaded boundaries**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-12T22:29:07Z
- **Completed:** 2026-04-12T22:31:20Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- WAV header replaced with struct.pack implementation producing correct 44-byte header with 0xFFFFFFFF streaming sizes
- StreamingCrossfader wired into TTSInferenceEngine.inference() -- streaming segments now crossfaded via process()+flush()
- Non-streaming path completely unchanged -- crossfader is None, no yields, raw concatenation preserved
- Integration test suite with 5 tests verifying header correctness, float32-to-int16 compatibility, and full streaming sequence

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace wav_chunk_header with struct.pack streaming implementation** - `fb7bf7c` (feat)
2. **Task 2: Wire StreamingCrossfader into TTSInferenceEngine.inference()** - `0cf04f7` (feat)
3. **Task 3: Integration smoke tests -- streaming and non-streaming paths** - `20c5b65` (test)

## Files Created/Modified
- `fish_speech/inference_engine/utils.py` - WAV header now uses struct.pack with 0xFFFFFFFF sizes; removed io/wave imports
- `fish_speech/inference_engine/__init__.py` - StreamingCrossfader imported and wired into inference() streaming path
- `tests/test_streaming_integration.py` - 5 integration tests: WAV header sizes, format fields, int16 conversion, full sequence, non-streaming path

## Decisions Made
- Crossfader instantiated only when `req.streaming is True` -- zero overhead for non-streaming requests per D-18/D-19
- Raw (uncrossfaded) segments still appended to `segments` list for final `np.concatenate` -- backward compatible final audio output
- struct.pack replaces Python wave module for explicit byte-level control of WAV header fields

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully implemented with no placeholders.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Streaming pipeline complete: WAV header emits first, crossfaded segments stream as they decode, flush emits tail
- Ready for end-to-end testing with actual model inference
- The inference_wrapper in tools/server/inference.py already handles float32-to-int16 conversion via AMPLITUDE=32768

## Self-Check: PASSED

- FOUND: fish_speech/inference_engine/utils.py
- FOUND: fish_speech/inference_engine/__init__.py
- FOUND: tests/test_streaming_integration.py
- FOUND: .planning/phases/02-streaming-pipeline-audio-quality/02-02-SUMMARY.md
- FOUND: commit fb7bf7c (Task 1 feat)
- FOUND: commit 0cf04f7 (Task 2 feat)
- FOUND: commit 20c5b65 (Task 3 test)

---
*Phase: 02-streaming-pipeline-audio-quality*
*Completed: 2026-04-12*
