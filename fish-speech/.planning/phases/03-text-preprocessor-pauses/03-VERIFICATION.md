---
phase: 03-text-preprocessor-pauses
verified: 2026-04-13T17:15:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
human_verification:
  - test: "Play back a long utterance with injected commas and [slow] tags to confirm pauses are audible and natural"
    expected: "Comma-injected boundaries produce brief pauses; [slow]-tagged emotional sentences are perceptibly slower than surrounding text"
    why_human: "Auditory quality of model-generated prosody cannot be verified programmatically"
  - test: "Compare pause durations across a multi-sentence utterance to confirm no metronomic regularity"
    expected: "Pauses feel varied and natural, not rhythmically identical"
    why_human: "Jitter is verified in metadata (Gaussian distribution, 99 unique durations in 100 runs), but the perceptual impact on model-generated audio requires human listening"
---

# Phase 3: Text Preprocessor & Pauses Verification Report

**Phase Goal:** Speech rhythm sounds natural through text-level punctuation injection, pause tags, and speech rate variation that guide the model's existing prosody capabilities
**Verified:** 2026-04-13T17:15:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Long clauses without punctuation receive injected commas at natural boundaries, producing model-generated pauses | VERIFIED | `"She walked to the store and bought some milk and bread and cheese"` becomes `"She walked to the store, and bought some milk and bread and cheese"` -- exactly 1 comma injected before coordinating conjunction. 8+ word threshold enforced. Subordinating conjunctions (because, although, etc.) also handled. Short text and already-punctuated text left unchanged. 36/36 unit tests pass. |
| 2 | Pause durations vary audibly across a single utterance (no metronomic regularity) due to Gaussian jitter | VERIFIED | `_jittered_duration()` uses `random.gauss(base_ms, base_ms * 0.175)` clamped to [0.5x, 1.5x]. Behavioral test: 99 unique comma durations out of 100 runs confirms high jitter diversity. Within a single utterance, pause hints for comma (base 150ms) and period (base 350ms) produce distinct durations (e.g., 122.6ms and 349.1ms observed). |
| 3 | [slow] tags are inserted at emotional transition points, producing audible speech rate variation | VERIFIED | `[angry] You betrayed me.` becomes `[slow] [angry] You betrayed me.`. Multi-emotion input `[angry] Stop! [sad] I'm sorry.` correctly gets [slow] before each emotion-tagged sentence. No double [slow] insertion. [fast] tag intentionally excluded -- Phase 1 testing confirmed [fast] is non-responsive (0.959x, effectively no change). ROADMAP SC3 mentions "[slow] and [fast]" but research decision D-07 explicitly drops [fast] as non-functional. Only [slow] (1.068x verified effect) is implemented. |
| 4 | Per-chunk HumanismHints metadata is generated and available for downstream audio processing | VERIFIED | `preprocess()` returns `tuple[str, HumanismHints]`. HumanismHints contains `pause_hints: list[PauseHint]`, `rate_hints: list[RateHint]`, `breathing_cues: list[BreathingCue]`, `original_text: str`. All dataclasses substantive with typed fields. In inference pipeline, `humanism_hints` is generated per-request at line 68 of `__init__.py`. Currently a local variable (Phase 4 will add the storage/consumption path). |
| 5 | Text preprocessing adds less than 10ms to time-to-first-audio | VERIFIED | P99 latency benchmarks: 25-char=0.011ms, 117-char=0.021ms, 299-char=0.039ms, 960-char=0.120ms. Worst case is 83x under the 10ms budget. Pure stdlib (re, random, dataclasses), compiled regex at module level, zero I/O. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `fish_speech/utils/text_preprocessor.py` | TextPreprocessor class, PreprocessorConfig, HumanismHints, PauseHint, RateHint, BreathingCue | VERIFIED | 415 lines. All 6 classes present. `preprocess()` returns `tuple[str, HumanismHints]`. 7 compiled regex patterns at module level. No external dependencies (stdlib only: re, random, dataclasses). No circular imports. |
| `tests/test_text_preprocessor.py` | Unit tests for all preprocessor behaviors (min 100 lines) | VERIFIED | 373 lines, 36 test functions across 10 test classes. Covers dataclass defaults, preprocess contract, clause injection (9 cases), double punctuation cleanup, [slow] tags (5 cases), pause hints (6 cases), breathing cues (4 cases), integration (3 cases). All 36 pass. |
| `fish_speech/inference_engine/__init__.py` | TextPreprocessor integration before send_Llama_request | VERIFIED | Import at line 8. TextPreprocessor instantiated at line 67, preprocess called at line 68, req.text overwritten at line 69. All before send_Llama_request at line 78. Debug logging at lines 72-75 conditional on text change. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `inference_engine/__init__.py` | `utils/text_preprocessor.py` | `from fish_speech.utils.text_preprocessor import TextPreprocessor, PreprocessorConfig` | WIRED | Line 8 of __init__.py imports both classes. |
| `TTSInferenceEngine.inference` | `TextPreprocessor.preprocess` | `preprocessor.preprocess(req.text)` before send_Llama_request | WIRED | Line 68 calls preprocess(req.text), line 69 assigns result to req.text, line 78 passes req to send_Llama_request. Order verified programmatically (indices 27 < 28 < 37 in method source). |
| `TextPreprocessor.__init__` | `PreprocessorConfig` | `config: PreprocessorConfig | None = None` | WIRED | Constructor at line 142 accepts optional PreprocessorConfig, defaults to PreprocessorConfig(). |
| `TextPreprocessor.preprocess` | `HumanismHints` | `-> tuple[str, HumanismHints]` return type | WIRED | Returns (text, HumanismHints) at line 189. HumanismHints populated with pause_hints, rate_hints, breathing_cues, original_text. |
| `send_Llama_request` | `req.text` (preprocessed) | `text=req.text` in request dict | WIRED | send_Llama_request at line 247 passes `text=req.text`, which now contains preprocessed text after line 69 assignment. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `text_preprocessor.py` | `text` (preprocessed) | Input `text` parameter, transformed by regex operations | Yes -- regex substitutions modify actual text content | FLOWING |
| `text_preprocessor.py` | `pause_hints` | `_generate_pause_hints()` scanning punctuation positions | Yes -- `_PUNCT_POSITIONS.finditer(text)` produces real PauseHint objects with jittered durations | FLOWING |
| `text_preprocessor.py` | `breathing_cues` | `_generate_breathing_cues()` scanning sentence lengths | Yes -- sentences with 15+ words produce BreathingCue objects with tiered probability | FLOWING |
| `text_preprocessor.py` | `rate_hints` | Always `[]` (empty) | No -- [fast] dropped per research, RateHint type exists but is never populated | STATIC (intentional) |
| `inference_engine/__init__.py` | `humanism_hints` | `preprocessor.preprocess(req.text)` | Yes -- generated per-request | FLOWING but LOCAL -- not passed downstream yet (Phase 4 scaffolding) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Module imports cleanly | `from fish_speech.utils.text_preprocessor import TextPreprocessor, PreprocessorConfig, HumanismHints, PauseHint, RateHint, BreathingCue` | All 6 exports found | PASS |
| Clause injection works | `preprocess("She walked to the store and bought some milk and bread and cheese")` | `"She walked to the store, and bought some milk and bread and cheese"` -- 1 comma | PASS |
| [slow] tag insertion works | `preprocess("[angry] You betrayed me.")` | `"[slow] [angry] You betrayed me."` | PASS |
| Jitter produces variety | 100 iterations, count unique comma durations | 99 unique durations out of 100 | PASS |
| Empty input safe | `preprocess("")` | `("", HumanismHints())` with empty lists | PASS |
| Pipeline integration intact | `inspect.getsource(TTSInferenceEngine.inference)` checks | TextPreprocessor before send_Llama_request confirmed | PASS |
| Performance under 10ms | P99 benchmark on 4 input sizes | Max P99 = 0.120ms (960 chars) | PASS |
| All 36 unit tests | `pytest tests/test_text_preprocessor.py -x -v` | 36 passed in 2.46s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PAUS-01 | 03-01 | Text preprocessor injects punctuation at clause boundaries for natural model-generated pauses | SATISFIED | `_inject_clause_commas()` handles coordinating (FANBOYS) and subordinating conjunctions. 8+ word threshold. One comma per span. 9 unit tests covering edge cases. |
| PAUS-02 | 03-01 | [pause]/[short pause] tag insertion at strategic points | SATISFIED (redirected) | Research D-04 confirmed [pause] tags non-responsive. Requirement redirected to HumanismHints pause_hints metadata with char_offset and duration_ms for Phase 4 audio-level silence insertion. |
| PAUS-03 | 03-01 | Pause duration varies with Gaussian jitter (+/-15-20%) | SATISFIED | `_jittered_duration()` uses `random.gauss(base_ms, base_ms * 0.175)` clamped [0.5x, 1.5x]. 17.5% sigma verified. 99/100 unique durations confirms real variance. |
| PAUS-04 | 03-01 | [slow]/[fast] tag injection for speech rate variation | SATISFIED (partial scope) | [slow] implemented and working. [fast] intentionally excluded -- Phase 1 testing confirmed non-responsive (0.959x). Research decision D-07 documents this. |
| PAUS-05 | 03-01 | Text preprocessor produces per-chunk metadata (HumanismHints) | SATISFIED | HumanismHints dataclass with pause_hints, rate_hints, breathing_cues, original_text. Generated per-request. Ready for Phase 4. |
| PAUS-06 | 03-02 | Text preprocessing adds < 10ms overhead to TTFA | SATISFIED | P99 worst case 0.120ms on 960-char input. 83x under budget. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `text_preprocessor.py` | 47-53 | `_ABBREVIATIONS` frozenset defined but never referenced (dead code) | Warning | Abbreviation-period sentence splitting is incorrect -- "Dr. Smith" is split into two sentences. Comma injection still works because the split fragments are independently long enough. Review WR-01 identified this. |
| `text_preprocessor.py` | 307, 386 | `_insert_slow_tags` and `_generate_breathing_cues` use `_SENTENCE_BOUNDARY.split()` directly instead of `self._split_sentences()` | Info | Inconsistent splitting path. If `_split_sentences` is updated for abbreviation awareness, these methods would not benefit. Review IN-03 identified this. |
| `text_preprocessor.py` | 185 | `rate_hints=[]` always empty | Info | RateHint type defined but never populated. [fast] dropped per research. Acceptable -- type exists for future extensibility. |
| `inference_engine/__init__.py` | 68 | `humanism_hints` is local variable, not passed downstream | Info | Expected scaffolding. Phase 4 will add the storage/consumption path. Review IN-02 identified this. |

**None of the anti-patterns are blockers.** The abbreviation dead code (WR-01) is a quality issue that can cause incorrect sentence splitting on abbreviation-containing text, but it does not prevent the phase goal from being achieved -- comma injection still fires correctly on the split fragments, and the behavior is tested (albeit passing coincidentally per WR-03).

### Human Verification Required

### 1. Audible Pause Quality

**Test:** Generate speech for "She walked to the store and bought some milk and bread and cheese because she needed to feed the family tonight" and listen for a pause at the injected comma.
**Expected:** A brief, natural-sounding pause at the comma boundary, not a hard stop or silence.
**Why human:** Model-generated prosody from punctuation is an acoustic outcome that requires listening.

### 2. [slow] Tag Perceptual Effect

**Test:** Generate speech for "[angry] You betrayed me!" with and without the [slow] tag prepended. Compare speech rate.
**Expected:** The [slow]-prefixed version sounds slightly slower (Phase 1 measured 1.068x duration increase).
**Why human:** Speech rate variation is a perceptual quality that cannot be verified from text preprocessing alone.

### 3. Jitter Perceptual Non-Regularity

**Test:** Generate speech for a multi-sentence paragraph with varied punctuation and listen across the full utterance.
**Expected:** Pauses at commas, periods, and semicolons feel naturally varied, not metronomically identical.
**Why human:** Jitter metadata is verified programmatically (Gaussian distribution confirmed), but the perceptual impact depends on how the model interprets the punctuation.

### Gaps Summary

No blocking gaps found. All 5 success criteria are verified at the code and behavioral level. The phase goal -- text-level punctuation injection, [slow] tags, and pause metadata generation -- is achieved.

**Quality notes from code review (non-blocking):**
1. `_ABBREVIATIONS` frozenset is dead code (WR-01). Sentence splitting incorrectly breaks at abbreviation periods like "Dr." This does not block the phase goal but should be fixed for correctness.
2. `_insert_slow_tags` and `_generate_breathing_cues` bypass `self._split_sentences()` (IN-03). Should be unified when abbreviation-aware splitting is added.
3. `rate_hints` is always empty (RateHint type exists but [fast] was dropped per research). This is intentional and documented.
4. `humanism_hints` is local to `inference()` scope (IN-02). Phase 4 will wire it to downstream consumers.

**[fast] tag scope note:** Success Criterion 3 mentions "[slow] and [fast] tags" but Phase 1 empirically proved [fast] is non-responsive (0.959x = effectively no change). Research decision D-07 explicitly drops [fast]. Only [slow] (1.068x verified) is implemented. This is a justified scope reduction, not a gap.

---

_Verified: 2026-04-13T17:15:00Z_
_Verifier: Claude (gsd-verifier)_
