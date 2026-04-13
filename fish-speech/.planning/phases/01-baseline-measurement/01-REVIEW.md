---
phase: 01-baseline-measurement
reviewed: 2026-04-13T18:20:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - tools/tts_baseline/generate_corpus.py
  - tools/tts_baseline/test_tags.py
  - tools/tts_baseline/analyze_f0.py
  - tools/tts_baseline/analyze_pauses.py
  - tools/tts_baseline/upload_to_hf.py
  - tools/tts_baseline/prompts.json
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-04-13T18:20:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Six files comprising the TTS baseline measurement tooling were reviewed: a corpus generator, an inline tag test harness, F0 pitch analysis, pause distribution analysis, a HuggingFace uploader, and a prompt definition JSON file. The code is well-structured with clear separation of concerns and good use of argparse for CLI interfaces. No security vulnerabilities were found. Five warnings relate to missing error handling that could cause silent data corruption or unexpected crashes during long-running generation/upload jobs. Four informational items note code duplication and minor robustness gaps.

## Warnings

### WR-01: Hardcoded 44-byte WAV header skip can corrupt audio data

**File:** `tools/tts_baseline/generate_corpus.py:89`
**Issue:** The code assumes the WAV response always has exactly a 44-byte header (`pcm_data = raw_bytes[44:]`). WAV files can have additional metadata chunks (LIST, INFO, etc.) before the data chunk, making the header longer than 44 bytes. If the Fish Speech API ever adds metadata to its WAV output, this silently produces corrupt audio samples -- the first few bytes of the data chunk get interpreted as PCM, and the actual PCM data starts at the wrong offset. The same pattern appears in `test_tags.py:148`.
**Fix:** Parse the WAV header to find the actual data chunk offset, or use soundfile to read from the byte stream:
```python
import io
samples, sr = sf.read(io.BytesIO(raw_bytes), dtype='float32')
```
This handles any WAV header variant correctly and eliminates the manual int16-to-float32 conversion.

### WR-02: Odd-length PCM data causes silent truncation via numpy

**File:** `tools/tts_baseline/generate_corpus.py:95`
**Issue:** `np.frombuffer(pcm_data, dtype=np.int16)` will raise a ValueError if `len(pcm_data)` is odd, since int16 requires 2-byte alignment. A truncated HTTP response (network issue, timeout) could produce an odd byte count. There is no length validation before the frombuffer call.
**Fix:** Validate alignment before conversion:
```python
if len(pcm_data) % 2 != 0:
    pcm_data = pcm_data[:-1]  # Drop trailing byte
    print(f"    WARNING: Odd PCM byte count for {clip_id}, truncated 1 byte")
samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
```

### WR-03: Unhandled exceptions in test_tags.py main loop abort entire test run

**File:** `tools/tts_baseline/test_tags.py:516-517`
**Issue:** The `generate_audio()` function (line 130) raises `RuntimeError` on non-200 status but the main loop (lines 516-517) has no try/except around individual tag test iterations. If the TTS API returns an error for any single tag pair, the entire test run aborts and no results are saved for previously-completed tags. Given this runs 9 tags x 3 runs x 2 variants = 54 API calls (potentially 30+ minutes), losing all results to a single API hiccup is problematic.
**Fix:** Wrap the per-tag loop body in try/except and record failures:
```python
for test in TAG_TESTS:
    tag = test["tag"]
    try:
        # ... existing generation and evaluation logic ...
    except Exception as e:
        print(f"  ERROR: {tag} failed: {e}")
        all_results.append({"tag": tag, "result": "ERROR", "error": str(e)})
        continue
```

### WR-04: Division by zero in pause analysis when audio file has zero duration

**File:** `tools/tts_baseline/analyze_pauses.py:76`
**Issue:** `position_ratio = (start_s + end_s) / 2.0 / audio_duration_s` will raise ZeroDivisionError if `audio_duration_s` is 0.0. While unlikely for valid WAV files, a corrupted or empty file passed through the glob would trigger this. The same pattern appears on line 98.
**Fix:** Guard the division:
```python
if audio_duration_s > 0:
    position_ratio = (start_s + end_s) / 2.0 / audio_duration_s
else:
    position_ratio = 0.0
```

### WR-05: upload_to_hf.py has no error handling around upload_folder calls

**File:** `tools/tts_baseline/upload_to_hf.py:33-38`
**Issue:** `api.upload_folder()` can raise various exceptions (network errors, auth failures, rate limits). If the first upload succeeds but the second fails, the script crashes without any indication of partial success. For a tool that uploads potentially large corpora, partial-failure handling matters.
**Fix:** Wrap each upload in try/except and report per-corpus status:
```python
for local_name, remote_path in UPLOADS:
    local_path = BASE_DIR / local_name
    if not local_path.exists():
        print(f"SKIP: {local_path} does not exist")
        continue
    try:
        print(f"Uploading {local_path} -> {REPO_ID}/{remote_path} ...")
        result = api.upload_folder(
            folder_path=str(local_path),
            path_in_repo=remote_path,
            repo_id=REPO_ID,
            repo_type="dataset",
        )
        print(f"  Done: {result}")
    except Exception as e:
        print(f"  FAILED: {local_name}: {e}")
```

## Info

### IN-01: Duplicated pause detection logic for trailing pauses

**File:** `tools/tts_baseline/analyze_pauses.py:92-111`
**Issue:** The trailing-pause block (lines 92-111) duplicates the logic from the inner-loop block (lines 69-89) nearly verbatim -- same position_ratio calculation, same location classification, same dict construction. This is a maintenance risk; a change to one must be mirrored in the other.
**Fix:** Extract the pause-recording logic into a small helper:
```python
def _record_pause(pause_start_frame, pause_end_frame, frame_ms, audio_duration_s):
    start_s = pause_start_frame * frame_ms / 1000.0
    end_s = pause_end_frame * frame_ms / 1000.0
    duration_ms = (end_s - start_s) * 1000.0
    position_ratio = (start_s + end_s) / 2.0 / audio_duration_s if audio_duration_s > 0 else 0.0
    if position_ratio < 0.10:
        location = "beginning"
    elif position_ratio > 0.90:
        location = "end"
    else:
        location = "middle"
    return {"start_s": round(start_s, 3), "end_s": round(end_s, 3),
            "duration_ms": round(duration_ms, 1), "location": location}
```

### IN-02: Byte concatenation in streaming loop is quadratic

**File:** `tools/tts_baseline/generate_corpus.py:83-84`
**Issue:** `raw_bytes += chunk` in a loop performs repeated byte string concatenation, which is O(n^2) in total data size. For typical TTS clips (a few seconds of audio), this is negligible in practice, but using a bytearray or list of chunks would be cleaner.
**Fix:**
```python
chunks = []
for chunk in response.iter_content(chunk_size=None):
    chunks.append(chunk)
    if t_first is None and sum(len(c) for c in chunks) > 44:
        t_first = time.time()
raw_bytes = b"".join(chunks)
```

### IN-03: No mono-channel validation in analyze_f0.py

**File:** `tools/tts_baseline/analyze_f0.py:40`
**Issue:** `sf.read(wav_path)` returns a 2D array for stereo files but pyworld's `dio()` expects a 1D array. If a stereo WAV is accidentally placed in the input directory, the analysis would fail with an unhelpful numpy shape error.
**Fix:** Add a mono check or force mono:
```python
data, sr = sf.read(wav_path)
if data.ndim > 1:
    data = data[:, 0]  # Take first channel
data = data.astype(np.float64)
```

### IN-04: Hardcoded absolute paths in output directories

**File:** `tools/tts_baseline/generate_corpus.py:28`, `tools/tts_baseline/test_tags.py:28`, `tools/tts_baseline/analyze_f0.py:129`, `tools/tts_baseline/analyze_pauses.py:379`
**Issue:** Multiple files use hardcoded absolute paths like `/home/prana/tts-test/outputs` as defaults. While these are CLI defaults overridable via `--output-dir`/`--input-dir` flags (which is fine for personal tooling), `test_tags.py` has no CLI override -- `OUT_DIR` is a module-level constant with no argparse option.
**Fix:** Add an `--output-dir` argument to `test_tags.py`:
```python
parser = argparse.ArgumentParser(description="Test inline tag responsiveness")
parser.add_argument("--output-dir", type=str, default=str(OUT_DIR))
args = parser.parse_args()
out_dir = Path(args.output_dir)
```

---

_Reviewed: 2026-04-13T18:20:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
