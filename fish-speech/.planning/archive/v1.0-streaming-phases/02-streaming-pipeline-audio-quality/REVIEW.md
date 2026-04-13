---
phase: 02-streaming-pipeline-audio-quality
reviewed: 2026-04-12T23:45:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - fish_speech/inference_engine/crossfader.py
  - fish_speech/inference_engine/utils.py
  - fish_speech/inference_engine/__init__.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-04-12T23:45:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 2 introduces three well-scoped changes: a new `StreamingCrossfader` class with equal-power sin^2 blending, a corrected WAV streaming header using `struct.pack` with `0xFFFFFFFF` sizes, and the wiring of the crossfader into the `TTSInferenceEngine.inference()` streaming path.

The crossfader implementation is clean and mathematically correct. The sin^2/cos^2 energy conservation identity holds, edge cases for short segments are handled, and the fade curves are precomputed at construction time. The WAV header produces a valid 44-byte structure with correct field layout.

Two warnings were identified: (1) the WAV header is silently dropped by the downstream `inference_async` transport layer due to a pre-existing `isinstance(chunk, bytes)` filter combined with the header being wrapped in `np.array()`, and (2) the crossfader does not apply blending when a short segment resets the state, creating an unblended boundary. Two info-level items were also noted.

The non-streaming path is confirmed unchanged -- the crossfader is gated behind `if req.streaming` and raw segments are always appended for the final concatenation.

## Warnings

### WR-01: WAV streaming header silently dropped by downstream transport

**File:** `fish_speech/inference_engine/__init__.py:81-88` (pre-existing pattern) + `tools/server/api_utils.py:73-76` (pre-existing filter)
**Issue:** The WAV header at line 85 is wrapped in `np.array(wav_chunk_header(...))`, producing a 0-dimensional numpy array of dtype `|S44`. The downstream `inference_wrapper` (tools/server/inference.py:22) yields this numpy array for the "header" case. Then `inference_async` (tools/server/api_utils.py:75) filters with `isinstance(chunk, bytes)`, which is `False` for numpy arrays. The WAV header is silently dropped and never sent to the streaming client.

While this is a pre-existing bug (not introduced in Phase 2), Phase 2 depends on the WAV header reaching the client for streaming playback. The new `0xFFFFFFFF` sizes in `wav_chunk_header()` are correct, but the header never arrives at the client.

**Fix:** In `fish_speech/inference_engine/__init__.py` line 85, yield the raw bytes instead of wrapping in numpy:
```python
yield InferenceResult(
    code="header",
    audio=(
        sample_rate,
        wav_chunk_header(sample_rate=sample_rate),  # bytes, not np.array
    ),
    error=None,
)
```
Alternatively, update `inference_wrapper` to call `.tobytes()` on the header, or update `inference_async` to also accept numpy arrays. The simplest fix is removing the `np.array()` wrapper since `InferenceResult.audio` already accepts any type in the tuple.

### WR-02: Short segment path resets crossfader state without blending

**File:** `fish_speech/inference_engine/crossfader.py:52-58`
**Issue:** When a segment shorter than `overlap_samples` (882 samples, ~20ms) arrives while `_tail_buffer` is not None, the code concatenates `tail_buffer + segment` with no crossfade and sets `_tail_buffer = None`. The next segment will then be treated as the "first segment" (line 60-63), meaning it emits its body without blending against a tail. This creates an unblended boundary between the concatenated short-segment output and the next full segment.

In practice, this edge case is unlikely because each DAC codec token produces ~2048 audio samples (~46ms), so even the smallest chunk produces far more than 882 samples. However, if a short segment does occur, there will be an audible click at two consecutive boundaries (before and after the short segment).

**Fix:** Buffer the short segment into the tail instead of emitting immediately, preserving the crossfade chain:
```python
if len(segment) < self._overlap:
    if self._tail_buffer is not None:
        # Extend the existing tail with the short segment, keeping
        # the last overlap_samples for the next crossfade
        combined = np.concatenate([self._tail_buffer, segment])
        if len(combined) > self._overlap:
            emittable = combined[:-self._overlap]
            self._tail_buffer = combined[-self._overlap:].copy()
            return emittable
        else:
            # Combined still shorter than overlap -- just update tail
            self._tail_buffer = combined
            return None
    # No tail buffer -- segment is too short to start crossfading
    return segment if len(segment) > 0 else None
```
This is a low-priority improvement given the practical minimum segment size from DAC.

## Info

### IN-01: Unused `gc` import

**File:** `fish_speech/inference_engine/__init__.py:1`
**Issue:** `import gc` is present but `gc` is only referenced in a comment at line 142. The actual gc cleanup was intentionally removed per the comment at line 141-143, but the import was left behind.
**Fix:** Remove `import gc` from line 1.

### IN-02: Debug `print` statement in downstream transport

**File:** `tools/server/api_utils.py:74`
**Issue:** `print("Got chunk")` is a debug artifact in the production streaming path. This will print to stdout for every streaming chunk, adding noise to server logs. This is pre-existing code not modified in Phase 2, but it is on the critical streaming path that Phase 2 activates.
**Fix:** Remove the print statement or replace with `logger.debug("Got chunk")`.

---

_Reviewed: 2026-04-12T23:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
