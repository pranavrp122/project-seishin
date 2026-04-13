# Phase 3: Text Preprocessor & Pauses - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 03-text-preprocessor-pauses
**Areas discussed:** Clause boundary detection, Pause mechanism, Speech rate tags, HumanismHints structure, Preprocessor architecture
**Mode:** --auto (all decisions auto-resolved with recommended defaults)

---

## Clause Boundary Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Rule-based regex/heuristic | No new dependencies, simple pattern matching on clause length and conjunctions | [auto] |
| NLP-based (spaCy) | More accurate clause detection, but adds heavy dependency | |
| Hybrid (regex + simple POS) | Middle ground, but still adds dependency complexity | |

**User's choice:** [auto] Rule-based regex/heuristic
**Notes:** spaCy explicitly deferred to v3+ in REQUIREMENTS.md (PROS-02). No new NLP dependencies in this milestone.

---

## Pause Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Punctuation injection | Inject commas/periods at clause boundaries — model produces natural pauses | [auto] |
| [pause] tag insertion | Insert explicit pause tags in text | |
| Audio silence insertion | Insert silence in post-processing (no text changes) | |

**User's choice:** [auto] Punctuation injection
**Notes:** Phase 1 testing confirmed [pause] tags non-responsive. Punctuation reliably produces model-generated pauses. Audio silence insertion deferred to Phase 4 via HumanismHints.

---

## Speech Rate Tags

| Option | Description | Selected |
|--------|-------------|----------|
| [slow] only | Use confirmed-working [slow] tag at emotional transitions | [auto] |
| Both [slow] and [fast] | Try both despite [fast] testing as non-responsive | |
| No rate tags | Rely entirely on punctuation for rhythm variation | |

**User's choice:** [auto] [slow] only
**Notes:** Phase 1: [slow] PASS (1.068x duration), [fast] FAIL (0.959x — no meaningful effect). Using only the confirmed lever.

---

## HumanismHints Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Dataclass with typed fields | Clean interface: pause hints, rate hints, breathing cues as typed fields | [auto] |
| Dict-based metadata | Flexible but untyped, harder for Phase 4 to consume reliably | |
| Inline text annotations | Embed metadata as special tokens in text (no separate structure) | |

**User's choice:** [auto] Dataclass with typed fields
**Notes:** Follows Phase 2 pattern (PostFXConfig dataclass). Typed fields provide clear interface contract for Phase 4.

---

## Preprocessor Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| New `text_preprocessor.py` module | Separate utility in `fish_speech/utils/`, called before split | [auto] |
| Integrated into `split_text_into_chunks()` | Modify existing function to add preprocessing | |
| Middleware/decorator pattern | Wrap existing split function | |

**User's choice:** [auto] New `text_preprocessor.py` module
**Notes:** Follows Phase 2 pattern (`post_fx.py` as separate utility). Keeps existing text splitting code untouched. Clean separation of concerns.

---

## Claude's Discretion

- Specific regex patterns for clause boundary detection
- Word-count thresholds for punctuation injection
- HumanismHints exact field structure
- Integration point details in inference.py

## Deferred Ideas

None — all discussion stayed within phase scope.
