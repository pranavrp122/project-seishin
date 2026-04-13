---
phase: 01-baseline-measurement
verified: 2026-04-13T21:10:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 1: Baseline Measurement Verification Report

**Phase Goal:** Quantitative and qualitative baseline of current model output exists, enabling data-driven decisions for all subsequent phases
**Verified:** 2026-04-13T21:10:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Baseline recordings exist for 10+ diverse prompts covering dialogue, narration, questions, exclamations, and long passages | VERIFIED | 12 baseline WAV files at 44100Hz in /home/prana/tts-test/outputs/baseline_corpus/. Categories: dialogue(2), narration(2), question(2), exclamation(2), long_passage(2), mixed_emotion(2). All readable by soundfile. |
| 2 | F0 pitch statistics (voiced F0 std dev, contour shapes) are computed and saved for baseline corpus | VERIFIED | f0_analysis.json has 12 per_clip entries with f0_mean_hz, f0_std_hz, f0_cv, f0_contour_shape. Corpus summary: mean F0=236.4Hz, CV=0.155, contour shapes: 1 flat, 11 moderate, 0 expressive. |
| 3 | Pause distribution (location, duration, frequency) is measured and documented across baseline corpus | VERIFIED | pause_analysis.json has 12 per_clip entries with pause_count, mean_pause_ms, max_pause_ms, pause_locations. Corpus summary: mean 4.0 pauses/clip, mean 274ms duration, histogram across 5 buckets, location distribution (6% beginning, 71% middle, 23% end). |
| 4 | Inline tag responsiveness is tested and documented with clear pass/fail per tag | VERIFIED | tag_results.json has 9 entries (all required tags). tag_report.md has per-tag measurements with 3 runs each (median), pass/fail verdicts, and implications for Phase 3/4. Results: 2/9 pass ([slow], [low volume]). 60 WAV A/B pair files in tag_tests/. |
| 5 | Adversarial test corpus exists with fragments, 50+ word sentences, numbers, questions, and mixed-emotion inputs | VERIFIED | 12 adversarial WAV files at 44100Hz in /home/prana/tts-test/outputs/adversarial_corpus/. Categories: fragment(2), long_sentence(2), numbers(2), question(2), mixed_emotion(2), edge_case(2). All readable by soundfile. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/tts_baseline/generate_corpus.py` | Reusable corpus generation script (min 80 lines) | VERIFIED | 199 lines. Uses ormsgpack for API calls, argparse for --corpus/--output-dir, streams WAV response, saves metadata JSON. |
| `tools/tts_baseline/prompts.json` | Structured prompt definitions with "adversarial" section | VERIFIED | 150 lines. 12 baseline prompts (6 categories), 12 adversarial prompts (6 categories). All entries have id, category, text, emotion_tag. |
| `tools/tts_baseline/test_tags.py` | Tag testing script (min 100 lines) | VERIFIED | 610 lines. Tests 9 tags with 3 runs each, measures duration diff and RMS ratios, generates tag_report.md. |
| `tools/tts_baseline/analyze_f0.py` | F0 analysis script using pyworld (min 60 lines) | VERIFIED | 196 lines. Uses pyworld DIO + StoneMask, computes per-clip and corpus-wide F0 stats, --input-dir CLI arg. |
| `tools/tts_baseline/analyze_pauses.py` | Pause detection and distribution analysis (min 60 lines) | VERIFIED | 453 lines. RMS energy thresholding, 100ms minimum, --input-dir and --report CLI args, generates combined report. |
| `tools/tts_baseline/upload_to_hf.py` | HuggingFace upload utility | VERIFIED | 1261 bytes. Auto-repo creation, XET workaround. |
| `/home/prana/tts-test/outputs/baseline_corpus/` | 10+ WAV files | VERIFIED | 12 WAV files, all 44100Hz mono, 0.70s-21.37s range. |
| `/home/prana/tts-test/outputs/adversarial_corpus/` | 10+ WAV files | VERIFIED | 12 WAV files, all 44100Hz mono. |
| `/home/prana/tts-test/outputs/tag_tests/` | WAV pairs for each tag | VERIFIED | 60 WAV files (9 tags x 2 versions x 3 runs + combination tests). |
| `/home/prana/tts-test/outputs/baseline_corpus/f0_analysis.json` | Per-clip and corpus-wide F0 statistics | VERIFIED | 4526 bytes. 12 per_clip entries, corpus_summary with all required fields. |
| `/home/prana/tts-test/outputs/baseline_corpus/pause_analysis.json` | Per-clip and corpus-wide pause distribution | VERIFIED | 12093 bytes. 12 per_clip entries, corpus_summary with histogram and locations. |
| `/home/prana/tts-test/outputs/baseline_corpus/baseline_report.md` | Combined human-readable report | VERIFIED | 3306 bytes. Contains F0 Statistics, Pause Distribution, Duration Histogram, Pause Locations, Per-Clip tables, Key Observations. |
| `/home/prana/tts-test/outputs/tag_tests/tag_report.md` | Tag pass/fail results with implications | VERIFIED | 5688 bytes. Summary table, 9 detailed sections with per-run data, combination test, Phase 3/4 implications. |
| `/home/prana/tts-test/outputs/tag_tests/tag_results.json` | Machine-readable tag results | VERIFIED | 4617 bytes. 9 entries with tag, result, measurements. |
| `/home/prana/tts-test/outputs/baseline_corpus/corpus_metadata.json` | Per-clip timing stats | VERIFIED | 5127 bytes. |
| `/home/prana/tts-test/outputs/adversarial_corpus/corpus_metadata.json` | Per-clip timing stats | VERIFIED | 4986 bytes. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| generate_corpus.py | TTS API (127.0.0.1:8080/v1/tts) | POST with ormsgpack body | WIRED | Line 21: `import ormsgpack`; Line 61: `ormsgpack.packb(payload, ...)` |
| generate_corpus.py | prompts.json | JSON load | WIRED | Line 46: `json.load(f)` loading prompts file |
| test_tags.py | TTS API (127.0.0.1:8080/v1/tts) | POST with ormsgpack body | WIRED | Line 20: `import ormsgpack`; Line 132: `ormsgpack.packb(payload, ...)` |
| analyze_f0.py | baseline WAVs | soundfile read + pyworld DIO/StoneMask | WIRED | Line 16: `import pyworld as pw`; Line 44: `pw.dio(data, sr, ...)` + Line 45: `pw.stonemask(...)` |
| analyze_pauses.py | baseline WAVs | soundfile read + RMS thresholding | WIRED | Line 121: `sf.read(wav_path)` |
| analyze_pauses.py | f0_analysis.json + pause_analysis.json | Report generation combining both | WIRED | Line 217-372: `generate_report()` reads F0 JSON, merges with pause data, writes baseline_report.md |

### Data-Flow Trace (Level 4)

Not applicable -- these are analysis tools and data files, not rendering components. All artifacts are measurement outputs from real TTS API calls, not UI components with data bindings.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| pyworld importable | `python3 -c "import pyworld; print(pyworld.__version__)"` | `0.3.5` | PASS |
| Baseline WAVs readable at 44100Hz | `sf.read(path)` on 3 sample files | All 44100Hz, valid audio data | PASS |
| Adversarial WAVs readable | `sf.read(path)` on 3 sample files | All 44100Hz, valid audio data | PASS |
| Tag test WAVs readable | `sf.read(path)` on 3 sample files | All 44100Hz, valid audio data | PASS |
| f0_analysis.json valid structure | Python JSON parse + key validation | 12 clips, all required keys present | PASS |
| pause_analysis.json valid structure | Python JSON parse + key validation | 12 clips, all required keys present | PASS |
| tag_results.json has all 9 tags | Python JSON parse + tag name check | All 9 tags present with PASS/FAIL | PASS |
| Scripts have CLI args | grep argparse + add_argument | All 3 analysis scripts have --input-dir or --corpus args | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| BASE-01 | 01-01 | Generate baseline recordings (10+ diverse prompts) | SATISFIED | 12 baseline WAVs covering 6 categories (dialogue, narration, question, exclamation, long_passage, mixed_emotion) |
| BASE-02 | 01-03 | Measure F0 pitch variation using pyworld | SATISFIED | f0_analysis.json with per-clip voiced F0 std dev, CV, contour shape. pyworld DIO+StoneMask confirmed. |
| BASE-03 | 01-03 | Measure pause distribution (location, duration, frequency) | SATISFIED | pause_analysis.json with pause_count, duration histogram (5 buckets), location distribution (beginning/middle/end) per clip and corpus-wide. |
| BASE-04 | 01-02 | Test model response to inline tags and document effectiveness | SATISFIED | All 9 tags tested with 3 runs each. Clear PASS/FAIL per tag. Report documents implications for Phase 3 and Phase 4. 60 WAV A/B pairs for manual verification. |
| BASE-05 | 01-01 | Establish adversarial test corpus | SATISFIED | 12 adversarial WAVs covering fragments, long sentences (60+ words), numbers, questions, mixed emotion, edge cases. corpus_metadata.json with timing stats. |

All 5 phase requirements accounted for. No orphaned requirements (REQUIREMENTS.md maps exactly BASE-01 through BASE-05 to Phase 1, and all 5 are claimed by plans).

**Note:** REQUIREMENTS.md has stale checkbox/traceability status -- BASE-01, BASE-04, BASE-05 still marked "Pending" in checkboxes and traceability table, though implementation is complete. This is a documentation lag, not an implementation gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | - |

No TODO, FIXME, placeholder comments, empty implementations, or stub patterns found in any of the 6 tool scripts.

### Human Verification Required

### 1. Audio Quality Spot-Check

**Test:** Listen to 3-4 baseline WAV files (e.g., baseline_01_dialogue.wav, baseline_07_exclamation.wav, baseline_09_long_passage.wav) and verify they sound like natural speech from the Archie reference voice.
**Expected:** Clear speech without obvious artifacts, consistent voice identity, appropriate for baseline comparison.
**Why human:** Audio perceptual quality cannot be verified programmatically -- files could be valid WAVs with garbled content.

### 2. Tag A/B Listening Validation

**Test:** Listen to the [slow] and [low volume] PASS pairs (e.g., slow_with_run1.wav vs slow_without_run1.wav) and confirm audible differences match the measured results.
**Expected:** [slow] version sounds noticeably slower in the tagged section. [low volume] version sounds quieter in the second half.
**Why human:** RMS and duration metrics may not reflect perceptual salience -- a measured 6.8% duration increase might not be perceptible.

### 3. Near-Threshold Tags Worth Listening

**Test:** Listen to [whisper] A/B pair (0.565x RMS, threshold was 0.5x) and [fast] pair (0.959 ratio, threshold 0.95). Assess if perceptual effect exists despite metric threshold miss.
**Expected:** [whisper] may sound somewhat quieter/breathier; [fast] may sound slightly faster. Both failed by narrow margins.
**Why human:** Threshold-based pass/fail is crude; human ear may detect effects that narrowly miss numeric thresholds.

### Gaps Summary

No gaps found. All 5 observable truths are verified with concrete evidence. All 16 artifacts exist, are substantive (not stubs), and are properly wired. All 5 requirements (BASE-01 through BASE-05) are satisfied by implementation evidence. No anti-patterns detected. Scripts are reusable with CLI arguments for re-running in subsequent phases.

The phase goal -- "Quantitative and qualitative baseline of current model output exists, enabling data-driven decisions for all subsequent phases" -- is achieved. The baseline data (F0 statistics, pause distribution, tag responsiveness) provides concrete numbers and decision-making data for Phase 2-5 planning.

---

_Verified: 2026-04-13T21:10:00Z_
_Verifier: Claude (gsd-verifier)_
