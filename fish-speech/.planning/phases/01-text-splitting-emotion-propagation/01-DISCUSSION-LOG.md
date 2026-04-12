# Phase 1: Text Splitting & Emotion Propagation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 01-text-splitting-emotion-propagation
**Areas discussed:** Splitting integration point, Chunk boundary regex, Emotion tag format & detection, Minimum chunk handling
**Mode:** --auto (all areas auto-selected, recommended options chosen)

---

## Splitting Integration Point

| Option | Description | Selected |
|--------|-------------|----------|
| New function before batch loop | Create `split_text_into_chunks()`, replace `batches = [text]` fallback | Y |
| Modify `split_text_by_speaker()` | Extend existing function to handle both speakers and clauses | |
| Modify `group_turns_into_batches()` | Add clause splitting inside the existing grouper | |

**User's choice:** [auto] New function — cleanest separation, doesn't break existing speaker path
**Notes:** Existing speaker-based splitting continues unchanged for multi-speaker text

---

## Chunk Boundary Regex

| Option | Description | Selected |
|--------|-------------|----------|
| Priority-ordered sentence > clause > force | `.!?` first, then `,;:—`, then max-bytes with word backtrack | Y |
| Sentence-only | Split only on `.!?`, force-split for everything else | |
| NLP-based (spaCy) | Use NLP tokenizer for boundary detection | |

**User's choice:** [auto] Priority-ordered — matches research findings, avoids mid-word breaks
**Notes:** NLP ruled out in requirements (50-100ms latency per split, out of scope)

---

## Emotion Tag Format & Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Regex `\[(\w+)\]` with tracking | Detect leading tag, scan mid-text transitions, prepend active to each chunk | Y |
| Leading tag only | Only handle text-start tags, ignore mid-text changes | |
| No emotion handling | Defer emotion propagation to Phase 2 | |

**User's choice:** [auto] Full regex with tracking — handles both leading and mid-text transitions
**Notes:** 93.3% tag activation rate in S2-Pro, repeating tags safe (consistent, not escalating)

---

## Minimum Chunk Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Merge into previous | Sub-minimum remainder joins previous chunk | Y |
| Emit as-is | Allow tiny final chunks | |
| Pad with silence tokens | Add padding to reach minimum | |

**User's choice:** [auto] Merge into previous — prevents prosody degradation on tiny chunks
**Notes:** 50-byte minimum from research; below this, prosody quality degrades

---

## Claude's Discretion

- Exact regex patterns and abbreviation handling (e.g., "Dr.", "U.S.")
- Internal function naming and parameter defaults
- Tag stripping vs inline preservation strategy

## Deferred Ideas

None
