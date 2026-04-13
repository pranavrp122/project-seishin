---
phase: 03-sub-chunk-audio-streaming
plan: 02
subsystem: inference-engine
tags: [streaming, grow-and-redecode, sub-chunk, crossfade, dac, audio-delta]
dependency_graph:
  requires:
    - phase: 03-sub-chunk-audio-streaming/01
      provides: [generator-decode-n-tokens, generator-generate, generator-generate-long, sub-chunk-tokens-param, is-partial-flag]
  provides:
    - grow-and-redecode consumer logic in inference()
    - sub-chunk delta audio emission
    - text-chunk boundary crossfade via prev_batch_tail
    - backward-compatible crossfader path for non-sub-chunk mode
  affects: [tts-api, streaming-endpoint]
tech_stack:
  added: []
  patterns: [grow-and-redecode, delta-audio-extraction, manual-sin2-cos2-crossfade, mode-switching-consumer]
key_files:
  created: []
  modified:
    - fish_speech/inference_engine/__init__.py
key_decisions:
  - "Bypass StreamingCrossfader entirely in sub-chunk mode; manage text-chunk crossfade manually via prev_batch_tail buffer"
  - "Manual crossfade uses same sin2/cos2 algorithm and 1764-sample overlap as StreamingCrossfader"
  - "is_sub_chunk_mode flag auto-detected from first is_partial=True; no explicit config needed"
patterns-established:
  - "Grow-and-redecode: decode full cumulative codes, emit segment[prev_audio_samples:] delta"
  - "Two-path consumer: sub-chunk mode (manual crossfade) vs non-sub-chunk mode (StreamingCrossfader)"
  - "Text-chunk tail buffering: withhold last 1764 samples of final sub-chunk for crossfade with next batch"
requirements-completed: [SUBCHK-02, SUBCHK-03, SUBCHK-05, SUBCHK-06]
duration: 1min
completed: 2026-04-13
---

# Phase 3 Plan 2: Grow-and-Redecode Consumer Summary

**Grow-and-redecode consumer in inference() that decodes cumulative VQ codes via DAC, emits only delta audio samples, skips crossfade at sub-chunk boundaries, and applies sin2/cos2 crossfade at text-chunk boundaries**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-13T01:24:31Z
- **Completed:** 2026-04-13T01:25:44Z
- **Tasks:** 2 (1 code change + 1 auto-approved checkpoint)
- **Files modified:** 1

## Accomplishments

- Implemented grow-and-redecode consumer that accumulates VQ codes from sub-chunk partials, decodes the full sequence via DAC, and emits only new audio samples (delta extraction via `segment[prev_audio_samples:]`)
- Added text-chunk boundary crossfading using prev_batch_tail buffer with sin2/cos2 equal-power blending (1764 samples = 40ms at 44.1kHz)
- Preserved backward compatibility: when sub_chunk_tokens=0 (no is_partial=True arrives), the existing StreamingCrossfader path is used unchanged
- Sub-chunk boundaries produce no crossfade (audio contiguous by causal DAC property)

## Task Commits

No commits made per user instruction (code changes only, no git commits).

1. **Task 1: Implement grow-and-redecode consumer with crossfader integration** - code complete, verified
2. **Task 2: Verify sub-chunk streaming end-to-end** - auto-approved checkpoint

## Files Created/Modified

- `fish_speech/inference_engine/__init__.py` - Added grow-and-redecode consumer logic to inference() while loop with three state variables (prev_audio_samples, prev_batch_tail, is_sub_chunk_mode), sub-chunk partial handling, text-chunk boundary crossfade, and prev_batch_tail flush after loop

## Decisions Made

1. **Bypass StreamingCrossfader in sub-chunk mode** - When sub-chunk streaming is active, we manage text-chunk crossfading manually via prev_batch_tail rather than feeding already-emitted audio through the stateful crossfader. This avoids complexity of partial audio re-processing.

2. **Manual crossfade matches StreamingCrossfader algorithm** - Uses identical sin2/cos2 equal-power curves with 1764-sample overlap (40ms at 44.1kHz) so audio quality at text-chunk boundaries is consistent regardless of mode.

3. **Auto-detect sub-chunk mode from is_partial flag** - is_sub_chunk_mode is set True on first is_partial=True response rather than checking a config flag. This means the consumer naturally handles mixed scenarios.

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Sub-chunk streaming pipeline is complete end-to-end: token generation (Plan 01) yields partial VQ codes every N tokens, consumer (this plan) decodes incrementally and streams audio deltas
- Ready for integration testing with real TTS server
- TTFA target of ~127ms (10 tokens x 12.2ms/token + ~5ms decode) achievable with sub_chunk_tokens=10

## Known Stubs

None -- all code paths are fully wired.

## Self-Check: PASSED

---
*Phase: 03-sub-chunk-audio-streaming*
*Completed: 2026-04-13*
