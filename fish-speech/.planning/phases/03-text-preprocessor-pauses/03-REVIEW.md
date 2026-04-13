---
phase: 03-text-preprocessor-pauses
reviewed: 2026-04-13T16:30:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - fish_speech/utils/text_preprocessor.py
  - tests/test_text_preprocessor.py
  - fish_speech/inference_engine/__init__.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-04-13T16:30:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the TextPreprocessor module (clause injection, slow tags, pause hints, breathing cues), its test suite, and the integration point in `TTSInferenceEngine.inference()`. The preprocessor is well-structured with clean separation of concerns, good use of dataclasses, and sensible defaults. Three warnings found: (1) `_ABBREVIATIONS` frozenset is defined but never referenced, meaning abbreviation-period sentence splitting is broken, (2) `char_offset` tracking in `_generate_breathing_cues` assumes single-space sentence boundaries which can drift with multi-space input, and (3) a test asserts behavior that relies on the broken abbreviation handling but passes coincidentally. Three info items for dead code and a minor style note.

## Warnings

### WR-01: _ABBREVIATIONS frozenset defined but never used -- abbreviation splitting is broken

**File:** `fish_speech/utils/text_preprocessor.py:47-53`
**Issue:** `_ABBREVIATIONS` is defined as a frozenset of common abbreviations (Dr, Mr, Mrs, etc.) with the comment "periods after these are NOT sentence ends." However, it is never referenced by any function. The `_SENTENCE_BOUNDARY` regex (`(?<=[.!?])\s+`) blindly splits at every period followed by whitespace, so "Dr. Smith" is split into two sentences: `["He went to Dr.", "Smith and they talked..."]`. This means clause injection and slow-tag insertion operate on incorrect sentence fragments when abbreviations are present.

Verified: `_SENTENCE_BOUNDARY.split("He went to Dr. Smith and they talked for hours and then left")` produces `['He went to Dr.', 'Smith and they talked for hours and then left']`.

**Fix:** Implement abbreviation-aware sentence splitting in `_split_sentences`. For example:

```python
def _split_sentences(self, text: str) -> list[str]:
    """Split text into sentence-like segments, respecting abbreviations."""
    # Use _SENTENCE_BOUNDARY to find candidate splits, then reject
    # splits where the preceding word is a known abbreviation.
    parts = []
    last = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        candidate_end = match.start()
        before = text[last:candidate_end].rstrip()
        # Check if the last word before the period is an abbreviation
        last_word = before.rsplit(None, 1)[-1].rstrip(".") if before else ""
        if last_word in _ABBREVIATIONS:
            continue  # not a real sentence boundary
        parts.append(text[last:candidate_end])
        last = match.end()
    if last < len(text):
        parts.append(text[last:])
    return [p for p in parts if p.strip()]
```

Also update `_insert_slow_tags` and `_generate_breathing_cues` which call `_SENTENCE_BOUNDARY.split()` directly instead of `self._split_sentences()`.

### WR-02: char_offset drift in _generate_breathing_cues with multi-space boundaries

**File:** `fish_speech/utils/text_preprocessor.py:412`
**Issue:** Line 412 (`char_offset += len(sentence) + 1`) assumes exactly one whitespace character was consumed by `_SENTENCE_BOUNDARY.split()`. However, `_SENTENCE_BOUNDARY` matches `\s+` (one or more whitespace characters). When input has double spaces ("A.  B.") or newlines ("A.\nB."), the `+1` underestimates the gap, causing `char_offset` to drift leftward for all subsequent sentences. This produces incorrect `BreathingCue.char_offset` values.

The same pattern appears to be safe in `_inject_clause_commas` (line 209) because it uses `" ".join()` to rejoin, normalizing whitespace. But `_generate_breathing_cues` operates on the original text, so the drift matters.

**Fix:** Track position using `text.find()` or `text.index()` for each sentence rather than arithmetic:

```python
def _generate_breathing_cues(self, text: str) -> list[BreathingCue]:
    cues: list[BreathingCue] = []
    sentences = _SENTENCE_BOUNDARY.split(text)
    search_from = 0

    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue

        # Find actual position in original text
        pos = text.find(stripped, search_from)
        if pos < 0:
            continue
        search_from = pos + len(stripped)

        clean = re.sub(r"\[[a-zA-Z]{2,12}\]\s*", "", stripped)
        word_count = len(clean.split())

        if word_count >= 15:
            if word_count >= 30:
                prob = 0.9
            elif word_count >= 20:
                prob = 0.6
            else:
                prob = 0.3
            cues.append(BreathingCue(char_offset=pos, probability=prob))

    return cues
```

### WR-03: Test asserts abbreviation behavior but relies on coincidental pass

**File:** `tests/test_text_preprocessor.py:159-166`
**Issue:** `test_abbreviation_period_not_sentence_end` asserts that a comma is injected in "He went to Dr. Smith and they talked for hours and then left." The test passes, but not for the intended reason. The sentence is split at "Dr." into two fragments. The second fragment ("Smith and they talked for hours and then left") happens to be long enough to trigger comma injection on its own. The test docstring says "the Dr. should not break the span" but the span IS broken -- the test just doesn't detect it.

A stronger assertion would verify the Dr-period is not treated as a sentence boundary:

**Fix:**

```python
def test_abbreviation_period_not_sentence_end(self):
    """Abbreviation periods are not treated as sentence ends."""
    tp = TextPreprocessor()
    text, _ = tp.preprocess(
        "He went to Dr. Smith and they talked for hours and then left"
    )
    # "Dr. Smith" must remain in the same span (not split into separate sentences)
    assert "Dr. Smith" in text
    # A comma should be injected based on the full-span word count
    assert "," in text
```

## Info

### IN-01: _ABBREVIATIONS frozenset is dead code

**File:** `fish_speech/utils/text_preprocessor.py:47-53`
**Issue:** The `_ABBREVIATIONS` frozenset is defined at module level but never imported or referenced by any function. It was likely intended to be used in sentence splitting but the implementation was not completed. This is dead code.

**Fix:** Either implement abbreviation-aware splitting (see WR-01) or remove the frozenset to avoid misleading future readers.

### IN-02: humanism_hints computed but not passed downstream

**File:** `fish_speech/inference_engine/__init__.py:68-75`
**Issue:** `humanism_hints` is computed at line 68 and used only in a debug log (lines 72-75). It is a local variable that goes out of scope, never passed to `post_fx.process()` or stored on the request. The comment on line 70 says "stored for Phase 4 consumption" but no storage actually occurs. This is understood to be intentional scaffolding for future work, noted here for tracking.

**Fix:** No action needed now. When Phase 4 work begins, `humanism_hints` should be threaded through to `HumanismPostFX.process()` or stored on `req` / the engine instance.

### IN-03: _insert_slow_tags and _generate_breathing_cues bypass _split_sentences

**File:** `fish_speech/utils/text_preprocessor.py:307, 386`
**Issue:** `_insert_slow_tags` (line 307) and `_generate_breathing_cues` (line 386) call `_SENTENCE_BOUNDARY.split(text)` directly, while `_inject_clause_commas` uses the `_split_sentences()` helper method (line 205). This inconsistency means any future fix to `_split_sentences` (e.g., abbreviation awareness) would need to be applied in three places. All three should use the same splitting method.

**Fix:** Replace direct `_SENTENCE_BOUNDARY.split(text)` calls with `self._split_sentences(text)` in both `_insert_slow_tags` and `_generate_breathing_cues`.

---

_Reviewed: 2026-04-13T16:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
