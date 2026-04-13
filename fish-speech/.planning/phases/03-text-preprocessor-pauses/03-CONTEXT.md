# Phase 3: Text Preprocessor & Pauses - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Text-level preprocessing that injects punctuation at clause boundaries, inserts prosody tags ([slow]), and generates per-chunk metadata (HumanismHints) for downstream audio processing. No audio-level changes — this phase only transforms text before it reaches the model.

</domain>

<decisions>
## Implementation Decisions

### Clause Boundary Detection (PAUS-01)
- **D-01:** Use rule-based regex/heuristic for clause boundary detection — no NLP dependencies. spaCy is explicitly deferred to v3+ (PROS-02 in REQUIREMENTS.md).
- **D-02:** Inject commas at detected clause boundaries in long unpunctuated spans. The model already produces natural pauses at punctuation — Phase 1 confirmed this works.
- **D-03:** Target long clauses (e.g., 8+ words without punctuation) for comma injection. Preserve existing punctuation — only add where missing.

### Pause Mechanism (PAUS-02, PAUS-03)
- **D-04:** Rely on punctuation injection for model-generated pauses, NOT [pause]/[short pause] tags. Phase 1 baseline testing confirmed [pause] tags are non-responsive (2/9 tags worked; [pause] was not among them).
- **D-05:** For explicit pause control beyond what punctuation provides, use silence insertion in audio post-processing (downstream in Phase 4 via HumanismHints), not text tags.
- **D-06:** Gaussian jitter (PAUS-03) applies to any post-processing silence insertion, not to model-generated pauses from punctuation (model controls those durations).

### Speech Rate Variation (PAUS-04)
- **D-07:** Use [slow] tag only at emotional transition points. [fast] tag is non-responsive per Phase 1 testing ([slow] PASS at 1.068x, [fast] FAIL at 0.959x).
- **D-08:** [slow] tags inserted sparingly — at sentence boundaries preceding emotional or dramatic content. Not every sentence gets a rate tag.

### HumanismHints Metadata (PAUS-05)
- **D-09:** New dataclass `HumanismHints` carrying per-chunk metadata: pause hints (positions/durations), rate hints (slow regions), breathing cues (for Phase 4 consumption).
- **D-10:** HumanismHints generated alongside preprocessed text — the preprocessor returns both modified text and hints as a paired result.
- **D-11:** HumanismHints is a clean interface contract between Phase 3 (text preprocessing) and Phase 4 (audio post-processing). Phase 4 reads hints to apply silence insertion, volume dynamics, and breathing.

### Preprocessor Architecture
- **D-12:** New module at `fish_speech/utils/text_preprocessor.py` — follows Phase 2 pattern of separate utility module (`post_fx.py`).
- **D-13:** Preprocessor runs BEFORE `split_text_into_chunks()` in the inference pipeline. It transforms raw input text, then the existing splitter handles chunking with the injected punctuation.
- **D-14:** Preprocessor is stateless (no per-request state needed, unlike post-FX). Each call transforms text independently.

### Performance (PAUS-06)
- **D-15:** Text preprocessing must add < 10ms to TTFA. Rule-based regex on typical input lengths (< 1KB text) should be sub-millisecond.

### Claude's Discretion
- Specific regex patterns and heuristics for clause boundary detection
- Exact word-count threshold for "long clause" triggering comma injection
- HumanismHints field naming and exact structure
- Whether to use `re` module directly or compile patterns at module level
- Integration point specifics in `inference.py` (exact line/function to call preprocessor)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 Baseline Data
- `.planning/phases/01-baseline-measurement/01-03-SUMMARY.md` — F0 and pause analysis results (baseline metrics for comparison)
- `.planning/phases/01-baseline-measurement/01-02-SUMMARY.md` — Inline tag responsiveness results ([slow] PASS, [fast] FAIL, [pause] non-responsive)

### Phase 2 Architecture
- `.planning/phases/02-post-fx-chain/02-CONTEXT.md` — Post-FX architecture decisions, streaming state patterns
- `fish_speech/utils/post_fx.py` — HumanismPostFX class and PostFXConfig dataclass (pattern to follow for new module)

### Inference Pipeline
- `fish_speech/models/text2semantic/inference.py` — Text splitting logic (`split_text_into_chunks`, `_split_at_boundaries`, `_propagate_emotions`), inference entry point
- `fish_speech/inference_engine/__init__.py` — TTSInferenceEngine.inference() where preprocessor call will be integrated

### Requirements
- `.planning/REQUIREMENTS.md` §PAUS-01 through PAUS-06 — Phase 3 requirement definitions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `split_text_into_chunks()` in `inference.py:760` — Existing text splitter with emotion tag extraction/propagation. Preprocessor output feeds into this.
- `_propagate_emotions()` in `inference.py:724` — Emotion tag propagation across chunks. Preprocessor must be compatible with this (injected punctuation shouldn't break tag positions).
- `HumanismPostFX` / `PostFXConfig` in `post_fx.py` — Architectural pattern for the new preprocessor module (dataclass config + processor class).

### Established Patterns
- **Utility module pattern**: Phase 2 created `fish_speech/utils/post_fx.py` as a standalone utility. Phase 3 follows with `text_preprocessor.py`.
- **Per-request instantiation**: Inference engine creates `HumanismPostFX(PostFXConfig())` per request (line 87). Preprocessor is stateless so doesn't need per-request instances, but HumanismHints must be created per-request.
- **Emotion tag handling**: `_EMOTION_TAG` regex in inference.py strips and re-propagates emotion tags across chunks. Preprocessor must handle text that may contain emotion tags.

### Integration Points
- **Before split**: Preprocessor runs before `split_text_into_chunks()` call at inference.py:900-904 (single-speaker path) and potentially before `group_turns_into_batches()` at line 892 (multi-speaker path).
- **HumanismHints flow**: Hints need to flow from preprocessor → through text splitting → to inference engine → to Phase 4's audio post-processing. The existing `InferenceResult` or a parallel data path is needed.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

Key constraint from Phase 1 findings: only punctuation-based pauses and [slow] tags are effective levers. All other inline tags tested ([fast], [pause], [inhale], [short pause], etc.) showed no measurable model response. The preprocessor design must work within these constraints.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-text-preprocessor-pauses*
*Context gathered: 2026-04-13 (auto-resolved, --auto mode)*
