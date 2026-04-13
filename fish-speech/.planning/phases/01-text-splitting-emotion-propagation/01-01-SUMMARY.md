---
phase: 01-text-splitting-emotion-propagation
plan: 01
subsystem: inference
tags: [text-splitting, regex, emotion-tags, utf8, tdd]

# Dependency graph
requires: []
provides:
  - "split_text_into_chunks() function with boundary-priority splitting and emotion propagation"
  - "Comprehensive test suite (24 tests) for splitting and emotion propagation"
affects: [02-per-chunk-audio-generation, streaming-pipeline]

# Tech tracking
tech-stack:
  added: [pytest]
  patterns: [strip-then-split, boundary-priority-splitting, emotion-state-machine, offset-tracking]

key-files:
  created:
    - tests/__init__.py
    - tests/test_text_splitting.py
  modified:
    - fish_speech/models/text2semantic/inference.py

key-decisions:
  - "Used abbreviation set filtering instead of variable-width lookbehind (Python re limitation)"
  - "Track chunk offsets from _split_at_boundaries for accurate emotion tag position mapping"
  - "Emotion tag bytes excluded from budget via strip-then-split pattern (D-10)"

patterns-established:
  - "Strip-then-split: remove metadata (emotion tags) before splitting, reattach after"
  - "Boundary priority: sentence > clause > word > force-split at byte limit"
  - "Offset tracking: _split_at_boundaries returns (chunks, offsets) for position-aware post-processing"

requirements-completed: [SPLIT-01, SPLIT-02, SPLIT-03, SPLIT-04, SPLIT-05, EMOT-01, EMOT-02, EMOT-03]

# Metrics
duration: 6min
completed: 2026-04-12
---

# Phase 01 Plan 01: Text Splitting & Emotion Propagation Summary

**Byte-budgeted text splitting at natural boundaries with emotion tag extraction, tracking, and per-chunk propagation using TDD**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-12T21:10:29Z
- **Completed:** 2026-04-12T21:16:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented `split_text_into_chunks()` with priority-ordered boundary detection (sentence > clause > word > force-split)
- Full emotion tag lifecycle: extraction from input, position tracking through clean text, correct propagation to each output chunk
- UTF-8-safe force-splitting that never breaks mid-codepoint on CJK or multi-byte characters
- Sub-minimum chunk merging prevents prosody degradation on tiny final chunks
- 24 tests covering all 8 Phase 1 requirements pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for split_text_into_chunks** - `685c510` (test)
2. **Task 2: Implement split_text_into_chunks to pass all tests** - `c2832ea` (feat)

_TDD flow: RED (Task 1) then GREEN (Task 2). No refactor commit needed._

## Files Created/Modified
- `tests/__init__.py` - Empty package init for test discovery
- `tests/test_text_splitting.py` - 24 test functions across 8 test classes covering boundary detection, chunk sizing, emotion propagation, and edge cases
- `fish_speech/models/text2semantic/inference.py` - Added constants (_SENTENCE_END, _CLAUSE_BOUNDARY, _EMOTION_TAG, _ABBREVIATIONS) and 7 functions (_char_position_at_byte_limit, _find_last_boundary, _find_best_split, _split_at_boundaries, _propagate_emotions, split_text_into_chunks)

## Decisions Made
- **Abbreviation filtering approach:** Python `re` doesn't support variable-width lookbehinds, so the plan's lookbehind regex `(?<!\b(?:Dr|Mr|Mrs|...))` was replaced with a post-match filtering approach using a frozenset of abbreviations checked in `_find_last_boundary()`
- **Offset tracking for emotion propagation:** Instead of tracking char_offset by summing chunk lengths (which loses whitespace stripped between chunks), `_split_at_boundaries` returns `(chunks, offsets)` where each offset is the chunk's start position in the original clean text
- **Test parameter adjustments:** Three emotion/edge-case tests needed `min_chunk_bytes=10` and longer text to prevent sub-minimum merging from collapsing chunks that were testing other behaviors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Variable-width lookbehind regex crash**
- **Found during:** Task 2 (implementation)
- **Issue:** Plan's `_SENTENCE_END` regex used `(?<!\b(?:Dr|Mr|Mrs|Ms|Prof|Jr|Sr|St|vs|etc|Rev|Gen|Sgt|Cpl))` which crashes with `re.error: look-behind requires fixed-width pattern`
- **Fix:** Moved abbreviation check from regex lookbehind to runtime filtering in `_find_last_boundary()` with a frozenset lookup
- **Files modified:** fish_speech/models/text2semantic/inference.py
- **Verification:** All tests pass including `test_abbreviation_not_false_split`
- **Committed in:** c2832ea

**2. [Rule 1 - Bug] Emotion tag position tracking lost whitespace between chunks**
- **Found during:** Task 2 (implementation)
- **Issue:** `_propagate_emotions` tracked char_offset by summing chunk lengths, but whitespace stripped by `lstrip()` between chunks was not accounted for, causing emotion tags at position N to not match chunks starting at offset N-1
- **Fix:** Changed `_split_at_boundaries` to return `(chunks, offsets)` tuple where offsets track exact start positions in the original text; `_propagate_emotions` uses these offsets directly
- **Files modified:** fish_speech/models/text2semantic/inference.py
- **Verification:** `test_mid_text_emotion_change` and `test_multiple_emotion_transitions` pass
- **Committed in:** c2832ea

**3. [Rule 1 - Bug] Test parameters caused unintended min-chunk merging**
- **Found during:** Task 2 (implementation)
- **Issue:** Three tests had text content short enough that after splitting, the remainder fell below `min_chunk_bytes=50` default, causing merge behavior to collapse what should have been multi-chunk output
- **Fix:** Added `min_chunk_bytes=10` to emotion transition and ellipsis tests; slightly lengthened text content
- **Files modified:** tests/test_text_splitting.py
- **Verification:** All 24 tests pass
- **Committed in:** c2832ea

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. Core algorithm and API exactly match plan specification.

## Issues Encountered
- pytest was not installed in the project venv; bootstrapped pip via ensurepip then installed pytest

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `split_text_into_chunks()` is ready to be wired into `generate_long()` as specified in plan 01-02
- The function signature matches D-01: `split_text_into_chunks(text, first_chunk_bytes=80, subsequent_chunk_bytes=200, min_chunk_bytes=50)`
- Existing `split_text_by_speaker()` and `group_turns_into_batches()` are untouched
- Integration point: `generate_long()` line 625 `batches = [text]` fallback to be replaced with `split_text_into_chunks()` call

## Self-Check: PASSED

- All 3 files exist on disk
- Both commit hashes (685c510, c2832ea) found in git log
- `split_text_into_chunks` function exists in inference.py
- All 24 tests pass

---
*Phase: 01-text-splitting-emotion-propagation*
*Completed: 2026-04-12*
