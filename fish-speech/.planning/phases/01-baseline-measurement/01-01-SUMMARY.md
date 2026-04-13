---
phase: 01-baseline-measurement
plan: 01
subsystem: testing
tags: [tts, audio-corpus, pyworld, huggingface, baseline]

# Dependency graph
requires: []
provides:
  - "Baseline audio corpus (12 WAVs) covering dialogue, narration, questions, exclamations, long passages, mixed emotion"
  - "Adversarial audio corpus (12 WAVs) covering fragments, long sentences, numbers, rapid questions, mixed emotion, edge cases"
  - "Reusable corpus generation script (generate_corpus.py) with CLI args"
  - "Structured prompt definitions (prompts.json) for reproducible generation"
  - "pyworld installed for offline F0 analysis"
affects: [01-02, 01-03, 02-post-fx, 05-validation]

# Tech tracking
tech-stack:
  added: [pyworld-0.3.5]
  patterns: [msgpack-tts-api-call, streaming-wav-extraction, corpus-metadata-json]

key-files:
  created:
    - tools/tts_baseline/generate_corpus.py
    - tools/tts_baseline/prompts.json
    - tools/tts_baseline/upload_to_hf.py
  modified: []

key-decisions:
  - "Used user namespace EternalFlame549/project-seishin-data for HuggingFace (org prana-seishin does not exist)"
  - "Disabled XET storage to work around root-owned cache permissions, using standard LFS upload"

patterns-established:
  - "Corpus generation pattern: prompts.json defines structured prompts, generate_corpus.py calls TTS API and saves WAVs with metadata"
  - "API call pattern: ormsgpack payload with streaming=True, extract PCM at byte offset 44, convert int16 to float32"

requirements-completed: [BASE-01, BASE-05]

# Metrics
duration: 6min
completed: 2026-04-13
---

# Phase 1 Plan 1: Corpus Generation Summary

**Generated 24 baseline+adversarial WAV files via Fish Speech API with reusable generation tooling and HuggingFace backup**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-13T20:27:30Z
- **Completed:** 2026-04-13T20:33:50Z
- **Tasks:** 3/3
- **Files created:** 3 (generate_corpus.py, prompts.json, upload_to_hf.py)

## Accomplishments
- 12 baseline WAVs covering all 6 required categories (dialogue, narration, question, exclamation, long_passage, mixed_emotion) at 44100Hz
- 12 adversarial WAVs covering all required edge cases (fragment, long_sentence, numbers, question, mixed_emotion, edge_case)
- Reusable generation script with --corpus and --output-dir CLI arguments for re-running after pipeline changes
- Both corpora uploaded to HuggingFace dataset repo EternalFlame549/project-seishin-data under humanism_baseline/
- pyworld 0.3.5 installed for offline F0 pitch analysis in subsequent plans
- Baseline TTFA measurements: avg 947ms (baseline corpus), avg 1204ms (adversarial corpus)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install pyworld and create prompt definitions** - `39821fb` (feat)
2. **Task 2: Create generation script and produce both corpora** - `862fb10` (feat)
3. **Task 3: Upload baseline corpora to HuggingFace** - `c2ed440` (feat)

## Files Created/Modified
- `tools/tts_baseline/prompts.json` - 24 structured prompt definitions (12 baseline + 12 adversarial) with id, category, text, emotion_tag
- `tools/tts_baseline/generate_corpus.py` - 209-line reusable script calling Fish Speech API with streaming WAV extraction and metadata output
- `tools/tts_baseline/upload_to_hf.py` - HuggingFace upload utility with auto-repo-creation and XET workaround
- `/home/prana/tts-test/outputs/baseline_corpus/` - 12 WAV files + corpus_metadata.json
- `/home/prana/tts-test/outputs/adversarial_corpus/` - 12 WAV files + corpus_metadata.json

## Decisions Made
- Used EternalFlame549/project-seishin-data instead of prana-seishin/project-seishin-data for HuggingFace (the org namespace does not exist and token lacks org creation rights)
- Disabled HuggingFace XET storage backend via HF_HUB_DISABLE_XET=1 to work around root-owned cache directory permissions; falls back to standard LFS upload which works correctly

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing Python packages (soundfile, ormsgpack, numpy)**
- **Found during:** Task 2 (generation script execution)
- **Issue:** System Python lacked soundfile, ormsgpack, numpy packages needed by generate_corpus.py
- **Fix:** Installed via pip with --break-system-packages flag
- **Files modified:** None (system packages)
- **Verification:** Script ran successfully, all 24 WAVs generated

**2. [Rule 3 - Blocking] Fixed HuggingFace org namespace not found**
- **Found during:** Task 3 (HuggingFace upload)
- **Issue:** prana-seishin org does not exist on HuggingFace; token lacks org creation rights
- **Fix:** Changed repo_id to EternalFlame549/project-seishin-data (user's personal namespace)
- **Files modified:** tools/tts_baseline/upload_to_hf.py
- **Verification:** Repo created and both corpora uploaded successfully

**3. [Rule 3 - Blocking] Fixed HuggingFace XET cache permission error**
- **Found during:** Task 3 (HuggingFace upload)
- **Issue:** ~/.cache/huggingface/xet/ owned by root, causing RuntimeError in XET upload backend
- **Fix:** Set HF_HUB_DISABLE_XET=1 to fall back to standard LFS upload
- **Files modified:** tools/tts_baseline/upload_to_hf.py
- **Verification:** Upload completed successfully via LFS

---

**Total deviations:** 3 auto-fixed (3 blocking issues)
**Impact on plan:** All fixes necessary to complete tasks. No scope creep.

## Issues Encountered
None beyond the auto-fixed blocking issues above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data is real, generated from live TTS API calls.

## Next Phase Readiness
- Baseline and adversarial corpora are ready for F0 pitch analysis (Plan 01-02) and pause/timing distribution analysis (Plan 01-03)
- pyworld is installed and ready for F0 extraction
- Generation script can be re-run after pipeline modifications in later phases for A/B comparison

## Self-Check: PASSED

- [x] tools/tts_baseline/prompts.json exists
- [x] tools/tts_baseline/generate_corpus.py exists
- [x] tools/tts_baseline/upload_to_hf.py exists
- [x] /home/prana/tts-test/outputs/baseline_corpus/corpus_metadata.json exists
- [x] /home/prana/tts-test/outputs/adversarial_corpus/corpus_metadata.json exists
- [x] Commit 39821fb exists (Task 1)
- [x] Commit 862fb10 exists (Task 2)
- [x] Commit c2ed440 exists (Task 3)

---
*Phase: 01-baseline-measurement*
*Completed: 2026-04-13*
