# Phase 1: Text Splitting & Emotion Propagation - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Split single-speaker input text into correctly-sized chunks at natural clause/sentence boundaries, extract and propagate emotion tags across all chunks. Output: a list of text chunks ready for per-chunk audio generation in Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Splitting Integration
- **D-01:** Create a new function `split_text_into_chunks(text, first_chunk_bytes=80, subsequent_chunk_bytes=200, min_chunk_bytes=50)` — does NOT replace `split_text_by_speaker()`, which continues to handle multi-speaker text
- **D-02:** In `generate_long()`, when `split_text_by_speaker()` returns empty (single-speaker), call `split_text_into_chunks()` instead of falling through to `batches = [text]`
- **D-03:** The existing `chunk_length` parameter maps to `subsequent_chunk_bytes` — first chunk uses a smaller target for fast TTFA

### Chunk Boundary Detection
- **D-04:** Priority-ordered split: sentence-ending (`.!?`) > clause boundaries (`,;:` and em-dash `—`/`--`) > force-split at max bytes with word-boundary backtrack
- **D-05:** When remaining text after a split is below `min_chunk_bytes` (50), merge it into the previous chunk rather than emitting a sub-minimum final chunk
- **D-06:** Force-split at max byte limit when no natural boundary exists — backtrack to last space to avoid mid-word breaks

### Emotion Tag Format & Propagation
- **D-07:** Leading emotion tag detected via regex `^\[(\w+)\]` at text start (e.g., `[angry] You betrayed me`)
- **D-08:** Mid-text emotion transitions detected by scanning for `\[(\w+)\]` patterns — each occurrence updates the "active" emotion tag
- **D-09:** Active emotion tag prepended to every chunk that doesn't already start with one — ensures Fish Speech receives the emotion instruction per-chunk
- **D-10:** Emotion tags are NOT counted toward chunk byte limits — they're metadata, not content

### Claude's Discretion
- Exact regex pattern details and edge case handling (e.g., abbreviations like "Dr." not triggering sentence splits)
- Whether to strip and re-add emotion tags or preserve them inline during splitting
- Internal function naming and parameter defaults

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Pipeline
- `fish_speech/models/text2semantic/inference.py` — `split_text_by_speaker()` (line 472), `group_turns_into_batches()` (line 503), `generate_long()` (line 541) — the three functions that control text-to-batch flow
- `fish_speech/inference_engine/__init__.py` — `TTSInferenceEngine.inference()` — orchestrates generation, passes `chunk_length` to `generate_long()`
- `fish_speech/utils/schema.py` — `ServeTTSRequest` schema with `chunk_length` field (line 83)

### Research
- `.planning/research/SUMMARY.md` — synthesized findings on splitting, emotion propagation, crossfade
- `.planning/REQUIREMENTS.md` — SPLIT-01..05, EMOT-01..03 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `split_text_by_speaker()` — regex-based speaker tag splitter; pattern can be adapted for emotion tag detection
- `group_turns_into_batches()` — byte-counting batch grouper; logic for `max_bytes` enforcement is reusable
- `chunk_length` parameter — already threaded from API schema through engine to `generate_long()`

### Established Patterns
- Text processing happens in `inference.py` before the generation loop
- Batches are simple `list[str]` — no special data structures needed
- `generate_long()` is a generator that yields `GenerateResponse` per batch — new splitting feeds directly into existing batch loop

### Integration Points
- `generate_long()` line 618-625: the `turns = split_text_by_speaker(text)` / `batches = [text]` branch — new splitter replaces the fallback path
- `ServeTTSRequest.chunk_length` — existing API parameter, repurposed for subsequent chunk target size
- No new API parameters needed — first chunk size can be a sensible default (not user-configurable)

</code_context>

<specifics>
## Specific Ideas

- Fish Speech treats emotion tags as inline text instructions with 93.3% activation rate in S2-Pro — repeating tags produces consistent prosody, not escalating emotion
- First chunk target 30-80 bytes for <500ms TTFA at 80 tok/s generation speed
- DAC hop_length = 512 samples (~11.6ms) — natural alignment for downstream crossfade, not relevant to splitting but informs chunk size choices
- Minimum viable chunk ~50 bytes / ~10 words — below this, prosody degrades

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-text-splitting-emotion-propagation*
*Context gathered: 2026-04-12*
