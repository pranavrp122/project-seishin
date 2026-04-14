---
phase: 04-breathing-volume-dynamics
reviewed: 2026-04-13T20:15:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - fish_speech/inference_engine/__init__.py
  - fish_speech/utils/audio_processor.py
  - fish_speech/utils/text_preprocessor.py
  - tools/tts_baseline/test_breathing_volume.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-04-13T20:15:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the Phase 4 breathing silence and volume dynamics implementation across the inference engine, audio processor, text preprocessor (volume hint additions), and the A/B test script. The architecture is sound: text preprocessing generates `VolumeHint` and `BreathingCue` metadata, the audio processor applies gain regions during streaming and inserts silence gaps on final audio only, and the engine correctly wires them together.

No critical issues found. Three warnings relate to a drifting position mapping during streaming volume processing, overlapping volume hints producing compounded gain, and a missing volume hint count in the debug log. Three info items cover the exclamation regex edge case, test hardcoding, and a minor `random` module interaction with seed setting.

## Warnings

### WR-01: Volume hint position mapping drifts during streaming

**File:** `fish_speech/utils/audio_processor.py:160-164`
**Issue:** `process_volume` passes `seg_end` (cumulative `audio_offset_samples + len(audio)`) as the `audio_length_samples` argument to `_char_to_sample`. Since total audio length is unknown during streaming, each successive segment uses a larger denominator, causing the same `char_offset` to map to a progressively later sample position. For a hint at 50% of text: on the first 44100-sample segment it maps to sample 22050; on the second call (88200 cumulative), it maps to 44100. This means early segments may apply gain to the wrong region or miss the region entirely, and later segments may re-apply gain to an already-processed region.

This is mitigated by the fact that `process_breathing` runs on final audio with the correct total length, and volume differences are subtle (0.85x/1.1x). However, for longer texts with many segments, the drift accumulates.

**Fix:** Use a fixed estimate of total audio length rather than the running cumulative. A reasonable estimate is `text_length * samples_per_char` where `samples_per_char` is derived from the model's typical character-to-duration ratio (e.g., ~3000 samples/char at 44.1kHz for English). Alternatively, defer volume processing to the final audio alongside breathing, at the cost of losing per-segment streaming volume adjustment.

```python
# Option A: fixed estimate at init
self._estimated_total_samples = int(text_length * self._sample_rate * 0.065)
# ~65ms per character is a reasonable English TTS estimate

# Then in process_volume:
hint_start = self._char_to_sample(
    hint.char_offset, self._text_length, self._estimated_total_samples
)
```

### WR-02: Overlapping volume hints produce compounded gain

**File:** `fish_speech/utils/audio_processor.py:159-171`
**Issue:** When two `VolumeHint` regions overlap (e.g., an exclamation sentence that contains a parenthetical aside), both gains are applied multiplicatively since `_apply_gain_region` modifies in-place and the loop iterates all hints. For an overlap of aside (0.85x) and emphasis (1.1x), the overlapping samples receive 0.85 * 1.1 = 0.935x gain instead of one or the other. While the `np.clip` on line 174 prevents overflow, the semantic intent is ambiguous.

The `_generate_volume_hints` in text_preprocessor.py does not deduplicate overlapping regions, and the sort on line 443 only orders them but does not merge or resolve conflicts.

**Fix:** Either skip overlapping hints (first-writer-wins) or document the compounding as intentional. A minimal fix:

```python
# In process_volume, track which sample ranges have been modified
applied_mask = np.zeros(len(audio), dtype=bool)
for hint in self._hints.volume_hints:
    # ... compute region_start, region_end ...
    if region_end > region_start:
        # Only apply to samples not yet modified
        unapplied = ~applied_mask[region_start:region_end]
        if unapplied.any():
            # Apply gain only to unapplied samples in the region
            self._apply_gain_region(audio, region_start, region_end, hint.gain)
            applied_mask[region_start:region_end] = True
            applied_count += 1
```

### WR-03: Debug log omits volume hint count

**File:** `fish_speech/inference_engine/__init__.py:72-75`
**Issue:** The debug log on line 73-75 reports pause_hints, rate_hints, and breathing_cues counts, but does not include the volume_hints count added in Phase 4. This makes it harder to verify volume processing is active during debugging.

**Fix:**
```python
if humanism_hints.original_text != preprocessed_text:
    logger.debug(f"Text preprocessed: {len(humanism_hints.pause_hints)} pause hints, "
                f"{len(humanism_hints.rate_hints)} rate hints, "
                f"{len(humanism_hints.breathing_cues)} breathing cues, "
                f"{len(humanism_hints.volume_hints)} volume hints")
```

## Info

### IN-01: Exclamation regex matches leading whitespace

**File:** `fish_speech/utils/text_preprocessor.py:53`
**Issue:** The `_EXCLAMATION_SENTENCE` pattern `[^.!?]*![^.!?]*` includes leading whitespace in its match. For text like `"First. This is great! Done."`, the match will be `" This is great"` (with leading space), making `char_offset` point at the space rather than the first content character. The `char_length` also includes that space. This causes the volume gain region to start slightly before the actual sentence content.

**Fix:** Add `\s*` stripping or use a tighter pattern:
```python
_EXCLAMATION_SENTENCE = re.compile(r'(?:^|(?<=[.!?]\s))[^.!?]*![^.!?]*')
```
Or strip whitespace from the match in `_generate_volume_hints` before computing offset.

### IN-02: Test script uses hardcoded absolute paths and reference ID

**File:** `tools/tts_baseline/test_breathing_volume.py:30-32`
**Issue:** `OUT_DIR` is hardcoded to `/home/prana/tts-test/outputs/breathing_volume_tests` and `REFERENCE_ID` is hardcoded to `"archie"`. This is acceptable for a developer-local test tool, but makes the script non-portable for other contributors or CI.

**Fix:** Consider environment variable fallbacks or command-line arguments if the script is intended for broader use:
```python
OUT_DIR = Path(os.environ.get("TTS_TEST_OUT", "/home/prana/tts-test/outputs/breathing_volume_tests"))
```

### IN-03: TextPreprocessor and AudioProcessor use `random` module affected by global seed

**File:** `fish_speech/utils/text_preprocessor.py:378,396` and `fish_speech/utils/audio_processor.py:103`
**Issue:** Both modules use `random.gauss()` and `random.random()` which are affected by `set_seed()` called in `__init__.py:63` (which calls `random.seed()`). When a seed is provided in the request, the breathing cue selection and pause jitter become deterministic. This is likely desirable for reproducibility, but worth noting: the preprocessing happens after `set_seed()`, so the random state consumed by `TextPreprocessor` and `HumanismAudioProcessor._roll_breathing_cues()` reduces the remaining entropy for the LLAMA model's token sampling. In practice, PyTorch reseeds its own RNG independently, so this is a non-issue for model quality.

**Fix:** No change needed. Document this interaction if reproducibility is a testing concern.

---

_Reviewed: 2026-04-13T20:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
