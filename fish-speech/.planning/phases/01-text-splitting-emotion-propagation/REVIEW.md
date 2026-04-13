---
phase: 01-text-splitting-emotion-propagation
reviewed: 2026-04-12T14:30:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - fish_speech/models/text2semantic/inference.py
  - tests/test_text_splitting.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-04-12T14:30:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the Phase 1 text splitting and emotion propagation implementation: 6 new helper functions, 4 module-level regex constants, the main `split_text_into_chunks()` entry point, the `generate_long()` integration, and 28 tests covering 9 test classes.

The implementation is well-structured with clear separation of concerns (strip tags, split text, reattach tags). The boundary-priority splitting logic is sound, UTF-8 safety is handled correctly, and the abbreviation filtering approach is a good workaround for Python's lack of variable-width lookbehinds.

Four warnings identified: one logic bug where leading whitespace can break emotion tag propagation, one overly broad regex that could strip non-emotion bracketed content, one fallback that passes degenerate input to the model, and a misleading log message. Three info items covering minor quality improvements.

No security issues found -- all functions are pure string processing with no I/O, no eval, no injection surfaces.

## Warnings

### WR-01: Leading whitespace before emotion tag breaks propagation

**File:** `fish_speech/models/text2semantic/inference.py:749-760`
**Issue:** Tag positions in `split_text_into_chunks` are recorded against the pre-stripped `clean_text`, but `_split_at_boundaries` operates on the post-`strip()` text. When there is leading whitespace before the first emotion tag (e.g., `"  [angry] Hello world"`), the tag position references an offset in the pre-stripped text that no longer corresponds to the correct position in the stripped text. This causes `_propagate_emotions` to fail the `tag_positions[idx][0] <= offset` check, silently dropping the emotion tag.

Trace: `"  [angry] Hello"` -> clean_text before strip: `"  Hello"` -> tag at position 2 -> after strip: `"Hello"` -> chunk offset 0 -> `2 <= 0` is False -> tag not applied.

**Fix:** Recalculate tag positions after stripping, or strip the input text before tag extraction. The simplest fix is to strip the input before processing:

```python
# Phase 1: Extract and strip emotion tags, recording positions
text = text.strip()  # Add this line
tag_positions: list[tuple[int, str]] = []
clean_text = ""
last_end = 0
```

Alternatively, compute the strip offset and adjust all tag positions:

```python
clean_text = clean_text.strip()
strip_offset = len(clean_text_before_strip) - len(clean_text_before_strip.lstrip())
tag_positions = [(max(0, pos - strip_offset), tag) for pos, tag in tag_positions]
```

### WR-02: `_EMOTION_TAG` regex matches all bracketed words, not just emotion tags

**File:** `fish_speech/models/text2semantic/inference.py:57`
**Issue:** The regex `\[(\w+)\]\s*` matches any `[word]` pattern including `[citation]`, `[1]`, `[emphasis]`, `[pause]`, or even `[123]`. If input text contains bracketed content that is not an emotion tag, it will be silently stripped from the output, causing data loss. Since `\w` includes digits and underscores, numeric references like `[1]` are also captured.

For a TTS system, input text like `"Read section [3] of the document"` would become `"Read section of the document"`.

**Fix:** Constrain the regex to match only known emotion tags, or at minimum restrict to alphabetic-only content of reasonable length:

```python
# Option A: Allowlist of known emotions (most robust)
_KNOWN_EMOTIONS = frozenset({"angry", "sad", "happy", "surprised", "neutral", "fearful", "disgusted"})
_EMOTION_TAG = re.compile(r"\[(\w+)\]\s*")
# Then filter in the extraction loop:
# if tag_name.lower() not in _KNOWN_EMOTIONS: continue

# Option B: Restrict to alpha-only, 2-12 chars (quick fix)
_EMOTION_TAG = re.compile(r"\[([a-zA-Z]{2,12})\]\s*")
```

### WR-03: Empty text fallback in `generate_long` passes degenerate input to model

**File:** `fish_speech/models/text2semantic/inference.py:867-868`
**Issue:** When `split_text_into_chunks` returns `[]` (empty or whitespace-only input), the fallback `batches = [text]` passes the original text directly to the model. If `text` is `""` or `"   "`, this sends an empty/whitespace string as input to the conversation, which could cause the model to generate garbage audio or trigger errors downstream in the encoding step. The assertion guards at the top of `generate_long` check `top_p` and `temperature` but do not validate that `text` is non-empty.

**Fix:** Validate text at the function entry and raise early:

```python
def generate_long(*, model, device, decode_one_token, text, ...):
    assert 0 < top_p <= 1, "top_p must be in (0, 1]"
    assert 0 < temperature < 2, "temperature must be in (0, 2)"
    
    text = text.strip()
    if not text:
        raise ValueError("text must be non-empty after stripping whitespace")
```

### WR-04: Log message is misleading for single-speaker text path

**File:** `fish_speech/models/text2semantic/inference.py:870`
**Issue:** `logger.info(f"Split into {len(turns)} turns, grouped into {len(batches)} batches")` always references `turns` even when the else branch was taken (single-speaker text, `turns = []`). The message "Split into 0 turns, grouped into 3 batches" is confusing because the batches came from `split_text_into_chunks`, not from turn grouping.

**Fix:** Differentiate the log message:

```python
if turns:
    batches = group_turns_into_batches(turns, max_speakers=5, max_bytes=chunk_length)
    logger.info(f"Split into {len(turns)} turns, grouped into {len(batches)} batches")
else:
    batches = split_text_into_chunks(text, first_chunk_bytes=80, subsequent_chunk_bytes=chunk_length, min_chunk_bytes=50)
    if not batches:
        batches = [text]
    logger.info(f"Single-speaker: split text into {len(batches)} chunks")
```

## Info

### IN-01: Abbreviation list is incomplete for common English abbreviations

**File:** `fish_speech/models/text2semantic/inference.py:49-51`
**Issue:** `_ABBREVIATIONS` is missing common abbreviations that contain periods: `"Inc"`, `"Ltd"`, `"Corp"`, `"Ave"`, `"Blvd"`, `"Dept"`, `"Fig"`, `"Vol"`, `"No"`. Also missing Latin abbreviations commonly used in English: `"e.g"` and `"i.e"` (though these have internal periods, so the current single-period check would not catch them anyway). For a TTS system, false sentence splits at abbreviations cause unnatural pauses.

**Fix:** Expand the frozenset with additional common abbreviations:

```python
_ABBREVIATIONS = frozenset(
    {"Dr", "Mr", "Mrs", "Ms", "Prof", "Jr", "Sr", "St", "vs", "etc",
     "Rev", "Gen", "Sgt", "Cpl", "Inc", "Ltd", "Corp", "Ave", "Blvd",
     "Dept", "Fig", "Vol", "No", "Capt", "Lt", "Col", "Maj"}
)
```

### IN-02: Comment references wrong function name

**File:** `fish_speech/models/text2semantic/inference.py:44`
**Issue:** The comment says "Abbreviation filtering is done in `_find_last_sentence_boundary()`" but the actual function is named `_find_last_boundary()`. This stale reference could confuse future maintainers.

**Fix:**

```python
# Abbreviation filtering is done in _find_last_boundary() instead of lookbehind
```

### IN-03: Test assertions use soft bounds that may not catch regressions

**File:** `tests/test_text_splitting.py:62-63`
**Issue:** Several tests use generous upper bounds for chunk size assertions (e.g., `<= 250` for a 200-byte target, `<= 200` for a 150-byte target). While this accounts for merge tolerance, it means a regression that doubles chunk sizes to 249 bytes would not be caught. This is a trade-off -- tighter bounds would be more brittle to implementation changes but would catch more regressions.

**Fix:** Consider adding a comment explaining why the bound is 250 (not 200), so future maintainers understand the tolerance:

```python
# Content bytes should be <= subsequent_chunk_bytes (200) + merge tolerance (50)
# since sub-minimum remainders can be merged into the previous chunk
assert len(content.encode("utf-8")) <= 250
```

---

_Reviewed: 2026-04-12T14:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
