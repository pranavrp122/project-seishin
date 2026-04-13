---
phase: 01-baseline-measurement
plan: 03
subsystem: testing
tags: [tts, pyworld, f0-pitch, pause-detection, audio-analysis, baseline]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Baseline corpus WAVs (12 clips at 44100Hz) and corpus_metadata.json"
provides:
  - "F0 pitch statistics per-clip and corpus-wide (mean, std, CV, contour shape)"
  - "Pause distribution per-clip and corpus-wide (count, duration histogram, location)"
  - "Combined baseline_report.md with all measurements for human review"
  - "Reusable analysis scripts (analyze_f0.py, analyze_pauses.py) with --input-dir CLI"
  - "Machine-readable JSON baselines (f0_analysis.json, pause_analysis.json) for A/B comparison"
affects: [02-post-fx, 03-text-preprocessor, 04-breathing-volume, 05-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [pyworld-dio-stonemask-f0, rms-energy-pause-detection, contour-shape-classification]

key-files:
  created:
    - tools/tts_baseline/analyze_f0.py
    - tools/tts_baseline/analyze_pauses.py
  modified: []

key-decisions:
  - "F0 contour thresholds: flat (CV<0.10), moderate (0.10-0.25), expressive (>0.25) -- 11/12 clips are moderate, baseline lacks expressiveness"
  - "Pause minimum 100ms to filter consonant closures; RMS 10th percentile threshold with 0.01 floor"
  - "56% of pauses are 100-200ms (short), 23% trailing at end of clips -- baseline has natural inter-clause pausing but heavy trailing silence"

patterns-established:
  - "F0 analysis pattern: pyworld DIO + StoneMask refinement at 5ms frame period, compute voiced-only statistics"
  - "Pause detection pattern: 10ms non-overlapping RMS frames, percentile-based threshold, 100ms minimum duration"
  - "Baseline report pattern: combined Markdown with F0 and pause tables, histogram, per-clip breakdowns, key observations"

requirements-completed: [BASE-02, BASE-03]

# Metrics
duration: 3min
completed: 2026-04-13
---

# Phase 1 Plan 3: Acoustic Analysis Summary

**F0 pitch (mean 236Hz, CV 0.155 moderate) and pause distribution (48 pauses, 56% short 100-200ms) measured across 12 baseline clips with reusable analysis tooling**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-13T20:40:54Z
- **Completed:** 2026-04-13T20:43:53Z
- **Tasks:** 2/2
- **Files created:** 2 (analyze_f0.py, analyze_pauses.py)

## Accomplishments
- Per-clip and corpus-wide F0 statistics using pyworld DIO+StoneMask: mean F0 236.4Hz, mean CV 0.155, 11/12 clips moderate contour (0 expressive)
- Per-clip and corpus-wide pause distribution via RMS thresholding: 48 pauses across 12 clips, mean 274ms, 56% in 100-200ms range
- Combined baseline_report.md with F0 tables, pause histogram, location distribution, and key observations
- Both scripts reusable with --input-dir for re-running on modified pipeline output in Phase 2-5

## Key Baseline Numbers

| Metric | Value | Implication |
|--------|-------|-------------|
| Mean F0 | 236.4 Hz (+/- 27.5) | Reference voice pitch center |
| Mean F0 Std | 37.6 Hz (+/- 13.9) | Intra-clip pitch variation |
| Mean CV | 0.155 | Moderate -- room for expressiveness improvement |
| Contour shapes | 1 flat, 11 moderate, 0 expressive | No highly expressive output at baseline |
| Mean pauses/clip | 4.0 (+/- 2.6) | Inter-clause pausing present |
| Mean pause duration | 274ms (+/- 97ms) | Reasonable natural pausing |
| Pause histogram | 56% short (100-200ms) | Dominated by brief pauses |
| Trailing pauses | 23% at end of clips | TTS adds trailing silence |

## Task Commits

Each task was committed atomically:

1. **Task 1: F0 pitch analysis with pyworld** - `633ad88` (feat)
2. **Task 2: Pause analysis and combined baseline report** - `654e641` (feat)

## Files Created/Modified
- `tools/tts_baseline/analyze_f0.py` - 196-line F0 analysis script using pyworld DIO+StoneMask, per-clip and corpus-wide statistics, contour shape classification
- `tools/tts_baseline/analyze_pauses.py` - 453-line pause analysis script with RMS thresholding, duration histogram, location distribution, and combined report generation
- `/home/prana/tts-test/outputs/baseline_corpus/f0_analysis.json` - Per-clip (12 entries) and corpus-wide F0 statistics
- `/home/prana/tts-test/outputs/baseline_corpus/pause_analysis.json` - Per-clip (12 entries) and corpus-wide pause distribution
- `/home/prana/tts-test/outputs/baseline_corpus/baseline_report.md` - 88-line combined human-readable report

## Decisions Made
- F0 contour shape thresholds chosen to match speech analysis conventions: CV<0.10 flat, 0.10-0.25 moderate, >0.25 expressive. These thresholds will be used consistently for A/B comparisons.
- Pause minimum duration set to 100ms to ignore consonant closures while catching natural inter-clause pauses. Below 100ms is typically plosive silence, not a perceptual pause.
- RMS threshold at 10th percentile of non-zero energy with 0.01 floor, balancing sensitivity (catching quiet pauses) with robustness (not flagging voiced but quiet segments).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data is real, computed from actual baseline corpus WAV files.

## Next Phase Readiness
- **Phase 2 (Post-FX):** Baseline F0 and pause metrics available for A/B comparison after applying EQ/compression. Re-run scripts with --input-dir pointing to post-FX output.
- **Phase 3 (Text Preprocessor):** CV=0.155 (moderate) confirms room for prosody improvement. Pause data provides baseline for evaluating punctuation-based pause injection.
- **Phase 4 (Breathing/Volume):** Pause location data (23% trailing, 71% middle) gives baseline for breathing sound placement.
- **Phase 5 (Validation):** All JSON baselines ready for automated regression comparison.

## Self-Check: PASSED

- [x] tools/tts_baseline/analyze_f0.py exists (196 lines)
- [x] tools/tts_baseline/analyze_pauses.py exists (453 lines)
- [x] /home/prana/tts-test/outputs/baseline_corpus/f0_analysis.json exists (12 per_clip entries)
- [x] /home/prana/tts-test/outputs/baseline_corpus/pause_analysis.json exists (12 per_clip entries)
- [x] /home/prana/tts-test/outputs/baseline_corpus/baseline_report.md exists (88 lines)
- [x] Commit 633ad88 exists (Task 1)
- [x] Commit 654e641 exists (Task 2)

---
*Phase: 01-baseline-measurement*
*Completed: 2026-04-13*
