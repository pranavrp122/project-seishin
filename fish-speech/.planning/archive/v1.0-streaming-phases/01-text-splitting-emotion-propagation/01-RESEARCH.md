# Phase 1: Text Splitting & Emotion Propagation - Research

**Researched:** 2026-04-12
**Domain:** Text chunking, regex-based boundary detection, emotion tag propagation
**Confidence:** HIGH

## Summary

This phase implements a new `split_text_into_chunks()` function that splits single-speaker text into byte-budgeted chunks at natural clause/sentence boundaries, with emotion tag extraction and propagation across all chunks. The function integrates into the existing `generate_long()` pipeline as the single-speaker fallback path (replacing the current `batches = [text]` no-op).

The implementation is pure Python string manipulation with `re` -- no new dependencies, no model changes, no GPU involvement. All decisions are locked in CONTEXT.md with clear regex patterns, boundary priorities, and byte targets. The primary risk is edge cases: abbreviation false-splits (Dr., Mr.), mid-codepoint force-splits on UTF-8 text, and emotion tags that look like content (e.g., `[angry]` embedded in quoted dialogue).

**Primary recommendation:** Implement as a single pure-Python module with comprehensive unit tests covering boundary detection, emotion propagation, byte budget enforcement, and UTF-8 safety. Wire into `generate_long()` with a 3-line integration.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Create a new function `split_text_into_chunks(text, first_chunk_bytes=80, subsequent_chunk_bytes=200, min_chunk_bytes=50)` -- does NOT replace `split_text_by_speaker()`, which continues to handle multi-speaker text
- **D-02:** In `generate_long()`, when `split_text_by_speaker()` returns empty (single-speaker), call `split_text_into_chunks()` instead of falling through to `batches = [text]`
- **D-03:** The existing `chunk_length` parameter maps to `subsequent_chunk_bytes` -- first chunk uses a smaller target for fast TTFA
- **D-04:** Priority-ordered split: sentence-ending (`.!?`) > clause boundaries (`,;:` and em-dash `--`/`--`) > force-split at max bytes with word-boundary backtrack
- **D-05:** When remaining text after a split is below `min_chunk_bytes` (50), merge it into the previous chunk rather than emitting a sub-minimum final chunk
- **D-06:** Force-split at max byte limit when no natural boundary exists -- backtrack to last space to avoid mid-word breaks
- **D-07:** Leading emotion tag detected via regex `^\[(\w+)\]` at text start (e.g., `[angry] You betrayed me`)
- **D-08:** Mid-text emotion transitions detected by scanning for `\[(\w+)\]` patterns -- each occurrence updates the "active" emotion tag
- **D-09:** Active emotion tag prepended to every chunk that doesn't already start with one -- ensures Fish Speech receives the emotion instruction per-chunk
- **D-10:** Emotion tags are NOT counted toward chunk byte limits -- they're metadata, not content

### Claude's Discretion
- Exact regex pattern details and edge case handling (e.g., abbreviations like "Dr." not triggering sentence splits)
- Whether to strip and re-add emotion tags or preserve them inline during splitting
- Internal function naming and parameter defaults

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPLIT-01 | System splits single-speaker text at clause/sentence boundaries (`.!?,;:--`) | D-04 defines priority order; regex boundary detection patterns documented in Architecture Patterns |
| SPLIT-02 | First chunk targets 30-80 bytes for fast TTFA | D-01 `first_chunk_bytes=80` parameter; first chunk uses smaller target per D-03 |
| SPLIT-03 | Subsequent chunks target 100-200 bytes for quality | D-01 `subsequent_chunk_bytes=200` parameter; maps to existing `chunk_length` per D-03 |
| SPLIT-04 | Minimum chunk size of 50 bytes enforced (below this, prosody degrades) | D-05 merge-back strategy for sub-minimum final chunks |
| SPLIT-05 | Force-split at max byte limit when no natural boundary exists | D-06 word-boundary backtrack; UTF-8 safety patterns documented in Common Pitfalls |
| EMOT-01 | Leading emotion tag (e.g., `[angry]`) extracted from input text | D-07 regex `^\[(\w+)\]`; extraction patterns documented |
| EMOT-02 | Active emotion tag prepended to every chunk before generation | D-09 prepend logic; D-10 tag bytes excluded from budget |
| EMOT-03 | Mid-text emotion transitions tracked and applied to correct chunks | D-08 scanning for `\[(\w+)\]` patterns; state machine approach documented |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `re` | stdlib (3.10+) | Regex-based boundary and emotion tag detection | Already used in `split_text_by_speaker()` at line 483; zero new dependencies |
| Python builtins | stdlib | `str.encode('utf-8')`, `bytes.rfind()`, `bytes.decode()` | Byte-counting and UTF-8-safe force-splitting |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `loguru` | (installed) | Debug logging for split decisions | Already used throughout `inference.py` |

### What NOT to Install
| Library | Why NOT |
|---------|---------|
| spaCy / nltk | NLP sentence detection adds 50-100ms latency per split; regex is sufficient for pre-formed text (per REQUIREMENTS.md Out of Scope) |
| textwrap | Python's `textwrap.wrap()` splits on character count, not byte count, and has no boundary priority system |

**Installation:** None required. All dependencies are stdlib or already installed.

## Architecture Patterns

### Recommended Project Structure
```
fish_speech/models/text2semantic/
    inference.py          # Existing - add split_text_into_chunks() here, near split_text_by_speaker()
                          # Modify generate_long() lines 618-625 for integration
```

No new files needed. The function lives alongside `split_text_by_speaker()` in `inference.py` since it serves the same pipeline stage (text -> batches).

### Pattern 1: Two-Pass Splitting (Strip-Then-Split)

**What:** First pass strips emotion tags and records their positions. Second pass splits the clean text at boundaries. Third pass re-attaches the correct emotion tag to each chunk.

**When to use:** Always -- this is the recommended approach per Claude's Discretion.

**Why strip-then-split:** Emotion tags embedded in text interfere with byte counting and boundary detection. Stripping them first makes the splitting algorithm simpler and ensures D-10 (tags don't count toward byte limits) is naturally satisfied.

**Example:**
```python
import re
from typing import Optional

def split_text_into_chunks(
    text: str,
    first_chunk_bytes: int = 80,
    subsequent_chunk_bytes: int = 200,
    min_chunk_bytes: int = 50,
) -> list[str]:
    """
    Split single-speaker text into byte-budgeted chunks with emotion tag propagation.
    
    Boundary priority: sentence (.!?) > clause (,;:--) > force-split at word boundary.
    Emotion tags are stripped, tracked, and prepended to each output chunk.
    """
    # Phase 1: Extract and strip emotion tags, recording positions
    emotion_pattern = re.compile(r'\[(\w+)\]\s*')
    tag_positions = []  # list of (char_position_in_clean_text, tag_name)
    
    active_tag: Optional[str] = None
    clean_text = ""
    last_end = 0
    
    for match in emotion_pattern.finditer(text):
        clean_text += text[last_end:match.start()]
        tag_name = match.group(1)
        tag_positions.append((len(clean_text), tag_name))
        last_end = match.end()
    clean_text += text[last_end:]
    clean_text = clean_text.strip()
    
    if not clean_text:
        return []
    
    # Phase 2: Split clean text at boundaries
    chunks = _split_at_boundaries(clean_text, first_chunk_bytes, subsequent_chunk_bytes, min_chunk_bytes)
    
    # Phase 3: Propagate emotion tags to chunks
    return _propagate_emotions(chunks, tag_positions)
```

### Pattern 2: Boundary-Priority Splitting Algorithm

**What:** Find the best split point within a byte budget using priority-ordered boundary types.

**When to use:** Core of `_split_at_boundaries()`.

**Algorithm:**
1. Encode remaining text as UTF-8 bytes
2. If remaining bytes <= current target, emit as final chunk
3. Within the byte window [0, target_bytes], find ALL boundary positions
4. Select the highest-priority boundary closest to the target (prefer later positions to maximize chunk size)
5. If no boundary found, backtrack from target to last space (force-split)
6. If no space found (single massive word), force-split at target with UTF-8 codepoint safety
7. After splitting, check if remainder < min_chunk_bytes; if so, merge with current chunk

**Boundary regex patterns:**
```python
# Sentence boundaries: period/exclamation/question followed by space
# Negative lookbehind for common abbreviations to reduce false splits
SENTENCE_END = re.compile(
    r'(?<![A-Z][a-z])'     # Not after Title-case abbreviation like "Dr"
    r'[.!?]+'              # One or more sentence-ending punctuation
    r'(?=\s|$)'            # Followed by whitespace or end of string
)

# Clause boundaries: comma, semicolon, colon, em-dash followed by space
CLAUSE_BOUNDARY = re.compile(r'[,;:]\s+|(?:--|—)\s*')
```

**Example:**
```python
def _find_best_split(text: str, max_bytes: int) -> int:
    """Find the best character position to split text within max_bytes budget.
    
    Returns character index (not byte index) for the split point.
    """
    text_bytes = text.encode('utf-8')
    if len(text_bytes) <= max_bytes:
        return len(text)
    
    # Convert byte limit to approximate char position
    # Walk forward to find exact char position at byte boundary
    char_pos = 0
    byte_count = 0
    char_to_byte = []
    for ch in text:
        ch_bytes = len(ch.encode('utf-8'))
        char_to_byte.append(byte_count)
        byte_count += ch_bytes
        if byte_count > max_bytes:
            break
        char_pos += 1
    
    search_region = text[:char_pos]
    
    # Priority 1: Sentence boundaries
    best = _find_last_boundary(search_region, SENTENCE_END)
    if best is not None:
        return best
    
    # Priority 2: Clause boundaries
    best = _find_last_boundary(search_region, CLAUSE_BOUNDARY)
    if best is not None:
        return best
    
    # Priority 3: Last space (word boundary)
    last_space = search_region.rfind(' ')
    if last_space > 0:
        return last_space + 1  # Split after the space
    
    # Priority 4: Force-split at byte limit (no word boundary found)
    return char_pos

def _find_last_boundary(text: str, pattern: re.Pattern) -> Optional[int]:
    """Find the last match of pattern in text, return split position after the match."""
    matches = list(pattern.finditer(text))
    if matches:
        last = matches[-1]
        return last.end()  # Split after the boundary (including trailing space)
    return None
```

### Pattern 3: Emotion Tag State Machine

**What:** Track which emotion tag is "active" at each character position, then assign the correct tag to each chunk based on where the chunk starts in the original text.

**When to use:** In `_propagate_emotions()`.

**Example:**
```python
def _propagate_emotions(
    chunks: list[str],
    tag_positions: list[tuple[int, str]],
) -> list[str]:
    """Prepend the active emotion tag to each chunk."""
    if not tag_positions:
        return chunks  # No emotion tags in input
    
    result = []
    char_offset = 0
    tag_idx = 0
    active_tag = None
    
    for chunk in chunks:
        # Advance tag state to this chunk's position
        while tag_idx < len(tag_positions) and tag_positions[tag_idx][0] <= char_offset:
            active_tag = tag_positions[tag_idx][1]
            tag_idx += 1
        
        # Prepend tag if chunk doesn't already start with one
        if active_tag and not re.match(r'^\[(\w+)\]', chunk):
            result.append(f'[{active_tag}] {chunk}')
        else:
            result.append(chunk)
        
        char_offset += len(chunk)
    
    return result
```

### Anti-Patterns to Avoid

- **Splitting on bytes directly:** Never slice `text.encode('utf-8')[:N]` and decode -- this can split mid-codepoint. Always track character positions and convert to byte counts.
- **Using `re.split()` for boundary detection:** `re.split()` consumes the delimiter and makes it hard to control which side gets the boundary punctuation. Use `re.finditer()` to find positions instead.
- **Counting emotion tag bytes in the budget:** Per D-10, emotion tags are metadata. If `[angry]` (7 bytes) is counted, a 50-byte minimum becomes effectively 43 bytes of content, causing prosody degradation.
- **Recursive splitting:** A simple while-loop consuming text from the front is clearer and avoids stack depth issues on very long texts.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NLP sentence detection | Custom ML-based sentence detector | Regex with abbreviation lookbehind | Pre-formed text has explicit punctuation; NLP adds 50-100ms per split for negligible accuracy gain |
| Unicode-aware text wrapping | Custom byte-counting wrapper | `str.encode('utf-8')` + character-position tracking | Python's built-in encoding handles all Unicode correctly |

**Key insight:** This is a text-manipulation problem, not an NLP problem. The input is pre-formed text with explicit punctuation -- regex boundary detection is sufficient and faster than any NLP-based approach.

## Common Pitfalls

### Pitfall 1: Abbreviation False-Splits
**What goes wrong:** "Dr. Smith said hello." splits into ["Dr.", " Smith said hello."] treating "Dr." as a sentence boundary.
**Why it happens:** Naive `[.!?]\s+` pattern matches any period followed by space.
**How to avoid:** Use negative lookbehind for common abbreviations. A pragmatic approach: require the period to be followed by an uppercase letter AND not preceded by a 2-4 letter capitalized word (common abbreviation pattern). Alternatively, maintain a small abbreviation set: `Dr|Mr|Mrs|Ms|Prof|Jr|Sr|St|vs|etc|Rev|Gen|Sgt|Cpl`.
**Warning signs:** Chunks that are suspiciously short (5-15 bytes) containing just an abbreviation.

### Pitfall 2: Mid-Codepoint Force-Split on UTF-8
**What goes wrong:** Force-splitting at byte position N can land in the middle of a multi-byte UTF-8 character (e.g., CJK characters are 3 bytes each), producing `UnicodeDecodeError` or garbled text.
**Why it happens:** Byte count != character count for non-ASCII text.
**How to avoid:** Always work in character positions and convert to byte counts for comparison. When force-splitting, iterate characters and accumulate byte counts rather than slicing bytes directly. Verified experimentally: `"你好世界".encode('utf-8')[:7]` fails to decode because byte 7 is mid-character.
**Warning signs:** `UnicodeDecodeError` in tests with CJK, emoji, or accented characters.

### Pitfall 3: Emotion Tag Inside Quoted Dialogue
**What goes wrong:** Text like `She said "[angry] stop that" quietly.` has `[angry]` inside quoted dialogue -- it's content, not an emotion instruction.
**Why it happens:** The emotion tag regex `\[(\w+)\]` matches any `[word]` pattern regardless of context.
**How to avoid:** This is an acceptable limitation for v1 -- the Fish Speech model treats `[angry]` as an inline instruction regardless of quoting, so propagating it is harmless and even desired. Document the behavior but don't over-engineer detection of "quoted context."
**Warning signs:** None -- this is a known acceptable behavior.

### Pitfall 4: Empty Chunks After Tag Stripping
**What goes wrong:** Input like `[angry] [sad]` (two tags, no content) produces empty chunks after stripping.
**Why it happens:** Emotion tags are stripped, leaving nothing between or after them.
**How to avoid:** After stripping, check if `clean_text.strip()` is empty. If so, return an empty list. Also ensure the splitting loop doesn't emit zero-length chunks.
**Warning signs:** Empty strings in the output list.

### Pitfall 5: Off-by-One at Chunk Boundaries
**What goes wrong:** Sentence boundary "Hello. World" -- the split should be after the space following the period, not between the period and space. Getting this wrong puts a leading space on the next chunk or a trailing space on the current chunk.
**Why it happens:** Ambiguity about whether boundary position is "after punctuation" or "after punctuation + whitespace."
**How to avoid:** Use `re.finditer()` match end position (which includes the trailing whitespace in the match) as the split point. The next chunk starts at clean text. Strip each chunk after splitting.
**Warning signs:** Chunks with leading/trailing whitespace; boundary punctuation appearing at the start of the wrong chunk.

### Pitfall 6: Minimum Chunk Merge Creates Over-Sized Chunk
**What goes wrong:** After merging a sub-minimum remainder into the previous chunk, the combined chunk exceeds the max byte target significantly.
**Why it happens:** D-05 says merge remainders below 50 bytes, but doesn't bound the resulting chunk size.
**How to avoid:** Accept this as intended behavior -- a chunk of 200 + 49 = 249 bytes is fine. The max_bytes targets are soft targets, not hard limits. The only hard constraint is the force-split which prevents any single chunk from being unbounded.
**Warning signs:** None -- this is expected behavior per D-05.

## Code Examples

### Integration Point in generate_long()
```python
# Current code (inference.py lines 618-625):
turns = split_text_by_speaker(text)
if turns:
    batches = group_turns_into_batches(
        turns, max_speakers=5, max_bytes=chunk_length
    )
else:
    batches = [text]

# New code:
turns = split_text_by_speaker(text)
if turns:
    batches = group_turns_into_batches(
        turns, max_speakers=5, max_bytes=chunk_length
    )
else:
    batches = split_text_into_chunks(
        text,
        first_chunk_bytes=80,
        subsequent_chunk_bytes=chunk_length,
        min_chunk_bytes=50,
    )
    if not batches:
        batches = [text]  # Fallback for empty/whitespace input

logger.info(f"Split into {len(turns)} turns, grouped into {len(batches)} batches")
```

### Byte-Safe Character Position Mapping
```python
def _char_position_at_byte_limit(text: str, max_bytes: int) -> int:
    """Return the character index where cumulative UTF-8 bytes exceed max_bytes.
    
    This is the safe alternative to slicing bytes directly.
    """
    byte_count = 0
    for i, ch in enumerate(text):
        byte_count += len(ch.encode('utf-8'))
        if byte_count > max_bytes:
            return i
    return len(text)
```

### Complete Emotion Extraction Example
```python
# Input: "[angry] You betrayed me. [sad] I'm sorry."
# After stripping:
#   clean_text = "You betrayed me. I'm sorry."
#   tag_positions = [(0, "angry"), (17, "sad")]
# After splitting at sentence boundary (byte budget permitting):
#   chunks = ["You betrayed me.", "I'm sorry."]
# After emotion propagation:
#   result = ["[angry] You betrayed me.", "[sad] I'm sorry."]

# Input: "[angry] You betrayed me. I trusted you. And now you're gone."
# After stripping:
#   clean_text = "You betrayed me. I trusted you. And now you're gone."
#   tag_positions = [(0, "angry")]
# After splitting (first chunk ~80 bytes, subsequent ~200 bytes):
#   chunks = ["You betrayed me.", "I trusted you. And now you're gone."]
# After emotion propagation:
#   result = ["[angry] You betrayed me.", "[angry] I trusted you. And now you're gone."]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No splitting (single batch) | `batches = [text]` in current code | Current state | High TTFA, no streaming benefit |
| NLP-based splitting (spaCy) | Regex boundary detection | Decision in REQUIREMENTS.md Out of Scope | 50-100ms saved per split |
| Emotion tag as model state | Inline text instruction per chunk | Fish Speech S2-Pro design | Must repeat tag per chunk (93.3% activation) |

**Deprecated/outdated:**
- Nothing deprecated -- this is a new feature being added to the codebase

## Open Questions

1. **CJK/non-Latin sentence boundaries**
   - What we know: CJK languages use different sentence-ending punctuation (e.g., Chinese uses `。！？`). The current regex `[.!?]` only handles Latin punctuation.
   - What's unclear: Whether Fish Speech S2-Pro is used with CJK text in this project.
   - Recommendation: Add CJK sentence-ending punctuation to the regex (`[.!?。！？]`) -- it's 3 extra characters and prevents future breakage. LOW cost, HIGH defensive value.

2. **Ellipsis handling**
   - What we know: `...` matches `[.!?]+` and would be treated as a sentence boundary.
   - What's unclear: Whether splitting on ellipsis is desired (e.g., "Well..." is a natural pause) or harmful (splits mid-thought).
   - Recommendation: Treat ellipsis as a valid sentence boundary -- in TTS, the pause is natural and the model handles trailing `...` well. The chunk after the ellipsis gets the emotion tag propagated.

3. **Abbreviation set completeness**
   - What we know: Common abbreviations (Dr., Mr., Mrs.) cause false sentence splits. A lookbehind can filter them.
   - What's unclear: How comprehensive the abbreviation set needs to be.
   - Recommendation: Start with the top 10 (Dr, Mr, Mrs, Ms, Prof, Jr, Sr, St, vs, etc). This covers 95%+ of real-world TTS inputs. Exotic abbreviations that split incorrectly just produce slightly smaller chunks -- not a correctness issue, just a quality optimization.

## Project Constraints (from CLAUDE.md)

- **Working directory:** Always use `/home/prana/project-seishin/fish-speech`, never standalone `/home/prana/fish-speech/`
- **No local models:** GPU dedicated to training, never start LLM servers during implementation
- **No co-author tags:** Don't add Co-Authored-By in git commits
- **Minimal blast radius:** Small, focused changes over sweeping rewrites -- new function added, 3-line integration in generate_long()
- **Read before writing:** Must understand existing `split_text_by_speaker()` and `group_turns_into_batches()` patterns before implementing
- **No unnecessary abstraction:** Three similar lines beat a premature helper function
- **No laziness:** No `TODO: implement later` -- complete implementation required

## Sources

### Primary (HIGH confidence)
- Fish Speech codebase: `fish_speech/models/text2semantic/inference.py` lines 472-625 -- `split_text_by_speaker()`, `group_turns_into_batches()`, `generate_long()` examined directly
- Fish Speech codebase: `fish_speech/inference_engine/__init__.py` lines 44-201 -- `TTSInferenceEngine.inference()` and `send_Llama_request()` showing `chunk_length` flow
- Fish Speech codebase: `fish_speech/utils/schema.py` line 83 -- `ServeTTSRequest.chunk_length` default 200, range [100, 1000]
- Python `re` module documentation -- stdlib, verified regex patterns experimentally
- UTF-8 byte-splitting behavior -- verified experimentally (CJK mid-codepoint failure confirmed)

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` -- synthesized from 7 research agents, cross-referenced with codebase
- `.planning/phases/01-text-splitting-emotion-propagation/01-CONTEXT.md` -- user decisions D-01 through D-10

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, no new dependencies, verified against installed codebase
- Architecture: HIGH -- single function, clear integration point at lines 618-625, pattern follows existing `split_text_by_speaker()`
- Pitfalls: HIGH -- experimentally verified (UTF-8 splitting, abbreviation regex, boundary positions)
- Emotion propagation: HIGH -- straightforward string manipulation, regex patterns verified

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable -- stdlib-only, no moving dependencies)
