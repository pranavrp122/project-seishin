# Phase 3: Text Preprocessor & Pauses - Research

**Researched:** 2026-04-13
**Domain:** Text preprocessing for TTS prosody control (punctuation injection, pause metadata, speech rate tags)
**Confidence:** HIGH

## Summary

Phase 3 is a text-only transformation layer that runs before `split_text_into_chunks()` in the Fish Speech inference pipeline. It injects punctuation at clause boundaries in long unpunctuated spans, inserts [slow] tags at emotional transition points, and generates per-chunk HumanismHints metadata for downstream audio post-processing in Phase 4.

The research confirms that rule-based regex clause boundary detection is the standard approach in production TTS text preprocessing. Open-source projects (Tortoise-TTS, Bark, ChatTTS, Coqui TTS) all use text-level manipulation -- punctuation insertion, special tokens, sentence splitting -- rather than model-level changes for prosody control. The key insight from Phase 1 testing is that Fish Speech S2-Pro responds reliably to punctuation-induced pauses (commas, periods) and the [slow] tag (1.068x duration), while most other inline tags are non-responsive. This constrains the preprocessor to exactly these two levers plus metadata generation.

The HumanismHints dataclass pattern has precedent in Hume AI's per-chunk metadata streaming and the ToBI prosodic annotation framework, but our implementation is much simpler: a lightweight dataclass carrying pause positions, rate hints, and breathing cues that Phase 4 consumes for silence insertion and volume automation.

**Primary recommendation:** Build a stateless `TextPreprocessor` class in `fish_speech/utils/text_preprocessor.py` with compiled regex patterns at module level. Use coordinating conjunction + word-count heuristics for clause boundary detection. Return a `(preprocessed_text, HumanismHints)` tuple from the main `preprocess()` method.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Rule-based regex/heuristic for clause boundary detection -- no NLP dependencies. spaCy deferred to v3+.
- **D-02:** Inject commas at detected clause boundaries in long unpunctuated spans. Model already produces natural pauses at punctuation.
- **D-03:** Target long clauses (8+ words without punctuation) for comma injection. Preserve existing punctuation.
- **D-04:** Rely on punctuation injection for model-generated pauses, NOT [pause]/[short pause] tags. Phase 1 confirmed these are non-responsive.
- **D-05:** Explicit pause control beyond punctuation uses silence insertion in audio post-processing (Phase 4 via HumanismHints).
- **D-06:** Gaussian jitter (PAUS-03) applies to post-processing silence insertion, not model-generated pauses.
- **D-07:** Use [slow] tag only at emotional transition points. [fast] is non-responsive.
- **D-08:** [slow] tags inserted sparingly -- at sentence boundaries preceding emotional/dramatic content.
- **D-09:** New `HumanismHints` dataclass with per-chunk metadata: pause hints, rate hints, breathing cues.
- **D-10:** HumanismHints generated alongside preprocessed text as a paired result.
- **D-11:** HumanismHints is the interface contract between Phase 3 (text) and Phase 4 (audio).
- **D-12:** New module at `fish_speech/utils/text_preprocessor.py`.
- **D-13:** Preprocessor runs BEFORE `split_text_into_chunks()` in the inference pipeline.
- **D-14:** Preprocessor is stateless. Each call transforms text independently.
- **D-15:** Text preprocessing must add < 10ms to TTFA.

### Claude's Discretion
- Specific regex patterns and heuristics for clause boundary detection
- Exact word-count threshold for "long clause" triggering comma injection
- HumanismHints field naming and exact structure
- Whether to use `re` module directly or compile patterns at module level
- Integration point specifics in `inference.py` (exact line/function to call preprocessor)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAUS-01 | Text preprocessor injects punctuation at clause boundaries for natural model-generated pauses | Clause boundary regex patterns using coordinating conjunctions (FANBOYS) + word-count threshold; Tortoise-TTS and bagrounds.org semicolon injection patterns confirm approach |
| PAUS-02 | [pause]/[short pause] tag insertion at strategic points | Redirected per D-04/D-05: Phase 1 confirmed these tags non-responsive. HumanismHints carries pause position hints for Phase 4 audio-level silence insertion instead |
| PAUS-03 | Pause duration varies with Gaussian jitter (+/-15-20%) | Gaussian jitter applied in HumanismHints metadata (duration_ms field with jitter); Phase 4 consumes hints for audio silence insertion. Academic research (arXiv 2406.05401) confirms Gaussian duration variation is standard for natural TTS |
| PAUS-04 | [slow]/[fast] tag injection for speech rate variation | [slow] only (PASS at 1.068x). [fast] non-responsive. Insert at sentence boundaries before emotional content per D-07/D-08 |
| PAUS-05 | Text preprocessor produces per-chunk metadata (HumanismHints) | HumanismHints dataclass design informed by Hume AI per-chunk metadata pattern and ToBI annotation framework. Lightweight dataclass with pause_hints, rate_hints, breathing_cues fields |
| PAUS-06 | Text preprocessing adds < 10ms overhead to TTFA | Compiled regex on <1KB text is sub-millisecond. No external dependencies, no I/O, pure string manipulation. Performance is trivially achievable |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `re` | stdlib | Regex clause boundary detection, pattern matching | Already used extensively in inference.py for _SENTENCE_END, _CLAUSE_BOUNDARY, _EMOTION_TAG. Zero dependency cost. |
| Python `dataclasses` | stdlib | HumanismHints and PreprocessorConfig dataclasses | Follows Phase 2 pattern (PostFXConfig is a dataclass). Zero dependency cost. |
| Python `random` | stdlib | Gaussian jitter for pause duration hints | `random.gauss()` for jitter. No numpy needed for simple scalar sampling. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `time` | stdlib | Performance timing (< 10ms verification) | Wrap preprocess() call with perf_counter for PAUS-06 verification during development |
| `loguru` | (installed) | Debug logging of preprocessing decisions | Log comma injections and [slow] tag insertions at DEBUG level |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python `re` | spaCy NLP | Much better clause detection but adds 200MB+ dependency, 100ms+ load time. Deferred to v3+ per PROS-02 |
| `random.gauss()` | `numpy.random.normal()` | numpy is heavier import; stdlib random is sufficient for scalar jitter values |
| Compiled regex | Inline re.search() | Module-level compiled patterns are ~3x faster for repeated calls. Use compiled. |

**Installation:**
```bash
# No installation needed -- all stdlib + already-installed dependencies
```

## Architecture Patterns

### Recommended Project Structure
```
fish_speech/
  utils/
    post_fx.py            # Phase 2: audio post-processing (existing)
    text_preprocessor.py  # Phase 3: text preprocessing (new)
  inference_engine/
    __init__.py           # Integration point: call preprocessor before generate_long
    utils.py              # InferenceResult dataclass (existing)
  models/
    text2semantic/
      inference.py        # split_text_into_chunks, generate_long (existing)
```

### Pattern 1: Stateless Preprocessor with Paired Output
**What:** A `TextPreprocessor` class that takes raw text and returns `(modified_text, HumanismHints)`. Stateless -- no per-request state needed. Config controls behavior.
**When to use:** Every inference request, before text splitting.
**Example:**
```python
# Source: follows Phase 2 PostFXConfig/HumanismPostFX pattern
from dataclasses import dataclass, field

@dataclass
class PreprocessorConfig:
    """Controls text preprocessing behavior. All features independently toggleable."""
    enable_clause_injection: bool = True       # PAUS-01: inject commas at clause boundaries
    clause_word_threshold: int = 8             # Words without punctuation before injection
    enable_slow_tags: bool = True              # PAUS-04: [slow] at emotional transitions
    enable_pause_hints: bool = True            # PAUS-02/03: pause position hints for Phase 4
    pause_jitter_pct: float = 0.175            # PAUS-03: +/-17.5% Gaussian jitter on hint durations
    enable_breathing_cues: bool = True         # Breathing position cues for Phase 4

@dataclass
class PauseHint:
    """A suggested pause position for Phase 4 audio post-processing."""
    char_offset: int          # Position in preprocessed text
    duration_ms: float        # Suggested duration with jitter applied
    source: str               # "punctuation" | "clause_boundary" | "sentence_boundary"

@dataclass
class RateHint:
    """A [slow] tag region for Phase 4 reference."""
    char_offset: int          # Position of [slow] tag in preprocessed text
    scope: str                # "sentence" -- applies to following sentence

@dataclass
class BreathingCue:
    """Suggested breathing point for Phase 4 inhale synthesis."""
    char_offset: int          # Position in preprocessed text
    probability: float        # 0.0-1.0 suggestion strength

@dataclass
class HumanismHints:
    """Per-request metadata contract between Phase 3 (text) and Phase 4 (audio)."""
    pause_hints: list[PauseHint] = field(default_factory=list)
    rate_hints: list[RateHint] = field(default_factory=list)
    breathing_cues: list[BreathingCue] = field(default_factory=list)
    original_text: str = ""   # Unmodified input for debugging


class TextPreprocessor:
    """Stateless text preprocessor for TTS humanism."""

    def __init__(self, config: PreprocessorConfig | None = None):
        self._config = config or PreprocessorConfig()

    def preprocess(self, text: str) -> tuple[str, HumanismHints]:
        """Transform text and generate humanism hints.

        Returns:
            Tuple of (preprocessed_text, hints) where preprocessed_text
            feeds into split_text_into_chunks() and hints flow to Phase 4.
        """
        hints = HumanismHints(original_text=text)
        text = text.strip()
        if not text:
            return text, hints

        # 1. Inject commas at clause boundaries (PAUS-01)
        if self._config.enable_clause_injection:
            text = self._inject_clause_commas(text)

        # 2. Insert [slow] tags at emotional transitions (PAUS-04)
        if self._config.enable_slow_tags:
            text = self._insert_slow_tags(text)

        # 3. Generate pause hints (PAUS-02, PAUS-03)
        if self._config.enable_pause_hints:
            hints.pause_hints = self._generate_pause_hints(text)

        # 4. Generate breathing cues (for Phase 4)
        if self._config.enable_breathing_cues:
            hints.breathing_cues = self._generate_breathing_cues(text)

        return text, hints
```

### Pattern 2: Clause Boundary Detection via Coordinating Conjunctions
**What:** Regex-based detection of long unpunctuated spans using conjunction signals (FANBOYS: for, and, nor, but, or, yet, so) and subordinating conjunctions (which, because, although, while, if, when, since, after, before, unless, until, though, whereas).
**When to use:** When a span of 8+ words has no punctuation, check for conjunction boundaries to inject commas.
**Example:**
```python
import re

# Compile at module level for performance (PAUS-06)
# Coordinating conjunctions (FANBOYS) preceded by word boundary
_COORD_CONJ = re.compile(
    r'(?<=\s)(and|but|or|nor|yet|so|for)\s',
    re.IGNORECASE
)

# Subordinating conjunctions that commonly start dependent clauses
_SUBORD_CONJ = re.compile(
    r'(?<=\s)(which|because|although|while|whereas|since|'
    r'unless|until|though|where|when|if|after|before)\s',
    re.IGNORECASE
)

# Long span without punctuation: 8+ words between punctuation marks
_LONG_UNPUNCTUATED = re.compile(
    r'(?<=[.!?,;:\s]|^)([^.!?,;:]{40,}?)(?=[.!?,;:]|$)'
)

def _inject_clause_commas(self, text: str) -> str:
    """Inject commas at conjunction boundaries in long unpunctuated spans.

    Only modifies spans of 8+ words without existing punctuation.
    Preserves existing punctuation -- never adds where it already exists.
    """
    def _maybe_insert_comma(match: re.Match) -> str:
        span = match.group(0)
        words = span.split()
        if len(words) < self._config.clause_word_threshold:
            return span

        # Try coordinating conjunctions first (higher confidence boundary)
        for conj_match in reversed(list(_COORD_CONJ.finditer(span))):
            pos = conj_match.start()
            # Only insert if enough words on both sides (at least 3 each)
            before = span[:pos].split()
            after = span[pos:].split()
            if len(before) >= 3 and len(after) >= 3:
                return span[:pos].rstrip() + ', ' + span[pos:].lstrip()

        # Try subordinating conjunctions (lower confidence, still useful)
        for conj_match in reversed(list(_SUBORD_CONJ.finditer(span))):
            pos = conj_match.start()
            before = span[:pos].split()
            after = span[pos:].split()
            if len(before) >= 4 and len(after) >= 3:
                return span[:pos].rstrip() + ', ' + span[pos:].lstrip()

        return span

    return _LONG_UNPUNCTUATED.sub(_maybe_insert_comma, text)
```

### Pattern 3: HumanismHints Flow Through Pipeline
**What:** HumanismHints must flow from preprocessor -> through text splitting -> to inference engine -> to Phase 4.
**When to use:** Every request that has preprocessing enabled.
**Integration approach:**
```python
# In inference_engine/__init__.py, before send_Llama_request:
from fish_speech.utils.text_preprocessor import TextPreprocessor, PreprocessorConfig

# In inference() method, before response_queue = self.send_Llama_request():
preprocessor = TextPreprocessor(PreprocessorConfig())
preprocessed_text, humanism_hints = preprocessor.preprocess(req.text)
req.text = preprocessed_text  # Modified text flows to generate_long -> split_text_into_chunks

# Store hints for Phase 4 consumption (exact mechanism TBD in Phase 4)
# For now, hints are generated and available. Phase 4 will add the consumption path.
```

### Pattern 4: Gaussian Jitter on Pause Hint Durations
**What:** Apply +/-15-20% Gaussian jitter to each pause hint duration to avoid metronomic regularity.
**When to use:** When generating PauseHint objects during preprocessing.
**Example:**
```python
import random

# Base durations by punctuation type (milliseconds)
_PAUSE_DURATIONS = {
    'comma': 150,       # Short clause pause
    'semicolon': 250,   # Medium clause pause
    'period': 350,      # Full sentence boundary
    'colon': 200,       # Anticipatory pause
    'em_dash': 200,     # Dramatic pause
}

def _jittered_duration(self, base_ms: float) -> float:
    """Apply Gaussian jitter to a base pause duration.

    PAUS-03: +/-17.5% jitter to avoid robotic regularity.
    Clamps to [0.5x, 1.5x] base to prevent extreme values.
    """
    jitter_pct = self._config.pause_jitter_pct
    jittered = random.gauss(base_ms, base_ms * jitter_pct)
    return max(base_ms * 0.5, min(base_ms * 1.5, jittered))
```

### Anti-Patterns to Avoid
- **Over-injecting commas:** Never inject more than one comma per long span. Multiple injections create choppy, unnatural speech. One comma per long clause is the maximum.
- **Injecting inside emotion tags:** The _EMOTION_TAG regex `\[([a-zA-Z]{2,12})\]` captures tags like [slow], [angry], etc. Never inject punctuation inside tag brackets.
- **Modifying already-punctuated text:** If a span already has commas/semicolons, skip it entirely. The preprocessor only adds where punctuation is missing.
- **Using [pause] or [fast] tags:** Phase 1 confirmed these are non-responsive. Using them wastes tokens and may confuse the model.
- **Stateful preprocessing:** Each preprocess() call must be independent. No request-scoped state. HumanismHints carries all metadata.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence boundary detection | Custom sentence splitter | Existing `_SENTENCE_END` regex in inference.py | Already handles abbreviations, CJK, tested in production |
| Emotion tag handling | New tag parser | Existing `_EMOTION_TAG` regex in inference.py | Already compatible with split_text_into_chunks() pipeline |
| Clause boundary splitting | Dependency parser | Regex conjunction matching + word-count threshold | spaCy deferred to v3+; regex sufficient for 80%+ of cases |
| Text normalization (numbers, dates) | Custom normalizer | Skip entirely | Out of scope for this phase; model handles text natively |

**Key insight:** The preprocessor is intentionally simple -- regex-only, no NLP dependencies, sub-millisecond. The TTS model's DualAR transformer already has strong prosody from 10M+ hours of training data. The preprocessor's job is to add missing punctuation cues, not to replace the model's prosody.

## Common Pitfalls

### Pitfall 1: Breaking Emotion Tag Propagation
**What goes wrong:** Injected commas or [slow] tags shift character offsets, breaking `_propagate_emotions()` which uses character positions to map tags to chunks.
**Why it happens:** The emotion tag system in inference.py strips tags and records positions, then re-adds them after splitting. If preprocessing changes text length, positions are stale.
**How to avoid:** Preprocessing runs on raw text BEFORE emotion tag stripping. The existing `split_text_into_chunks()` strips tags from the already-preprocessed text. Order is: preprocess -> split_text_into_chunks (which internally strips and re-propagates tags). This means preprocessing must handle text that MAY contain emotion tags.
**Warning signs:** Chunks with wrong emotion tags or tags appearing mid-sentence instead of at start.

### Pitfall 2: Double Punctuation
**What goes wrong:** Preprocessor inserts a comma right before existing punctuation, producing patterns like ",." or ",," or adding comma before em-dash.
**Why it happens:** Regex doesn't check what follows the injection point.
**How to avoid:** After injection, run a cleanup pass: `re.sub(r',\s*([,;:.!?])', r'\1', text)` to remove redundant commas before other punctuation.
**Warning signs:** Model produces stuttery speech with unnatural micro-pauses.

### Pitfall 3: Injecting Inside Quoted Speech or Parentheses
**What goes wrong:** Comma injection inside quoted dialogue or parenthetical remarks changes meaning.
**Why it happens:** Regex doesn't track nesting depth.
**How to avoid:** Keep the implementation simple -- the 8+ word threshold with conjunction matching is conservative enough that false positives inside quotes are rare. If needed, add a simple exclusion for text between matching quotes/parentheses.
**Warning signs:** Quoted speech sounds broken with unnatural pauses.

### Pitfall 4: [slow] Tag Conflicts with Emotion Tags
**What goes wrong:** Inserting [slow] at a position where an emotion tag like [angry] already exists, producing [slow] [angry] which may confuse the model.
**Why it happens:** Both [slow] and emotion tags use the same bracket syntax.
**How to avoid:** Before inserting [slow], check if the position already has a bracket tag. If an emotion tag exists at a sentence boundary, skip the [slow] insertion. The _EMOTION_TAG regex can be reused for detection.
**Warning signs:** Model ignoring or misinterpreting combined tags.

### Pitfall 5: Performance Regression from Regex Backtracking
**What goes wrong:** A pathological regex pattern causes exponential backtracking on adversarial input (e.g., 50+ word sentences with no spaces).
**Why it happens:** Nested quantifiers in regex patterns.
**How to avoid:** Use possessive quantifiers or atomic groups where possible. Test with adversarial inputs (50+ word sentences, no punctuation, repeated conjunctions). All patterns should complete in under 1ms for 1KB input.
**Warning signs:** TTFA spikes on certain input texts.

## Code Examples

Verified patterns from the codebase and TTS community:

### Existing Regex Patterns in inference.py (Reuse These)
```python
# Source: fish_speech/models/text2semantic/inference.py lines 43-59
# These are already defined and battle-tested:

_SENTENCE_END = re.compile(r"[.!?\u3002\uff01\uff1f]+(?:\s|$)")
_CLAUSE_BOUNDARY = re.compile(r"[,;:]\s+|(?:--|—)\s*")
_EMOTION_TAG = re.compile(r"\[([a-zA-Z]{2,12})\]\s*")
_ABBREVIATIONS = frozenset(
    {"Dr", "Mr", "Mrs", "Ms", "Prof", "Jr", "Sr", "St", "vs", "etc",
     "Rev", "Gen", "Sgt", "Cpl", "Inc", "Ltd", "Corp", "Ave", "Blvd",
     "Dept", "Fig", "Vol", "No", "Capt", "Lt", "Col", "Maj"}
)
```

### Tortoise-TTS Text Splitting Pattern (Community Reference)
```python
# Source: neonbjb/tortoise-tts/tortoise/utils/text.py
# Tortoise uses a state-machine approach:
# 1. Normalize whitespace and quotes
# 2. Walk through text tracking quote state
# 3. Split at sentence boundaries (.!?) when beyond half desired length
# 4. Force-split at word boundaries when exceeding max length
# 5. Filter empty/whitespace-only results
#
# Key takeaway: "at least one sentence and over half the desired length"
# is the heuristic trigger -- not a fixed character count.
```

### Bark Special Token Pattern (Community Reference)
```python
# Source: suno-ai/bark (HuggingFace)
# Bark uses inline tokens for nonverbal sounds:
#   [laughter], [laughs], [sighs], [gasps], [clears throat]
#   ... (ellipsis for hesitations/pauses)
#   -- (em-dash for natural speech breaks)
#
# Key takeaway for Fish Speech: the bracket syntax [tag] is standard
# across TTS models. Fish Speech uses the same pattern but with its
# own tag vocabulary. Preprocessing should respect this convention.
```

### ChatTTS Break Control Pattern (Community Reference)
```python
# Source: 2noise/ChatTTS (GitHub)
# ChatTTS uses parameterized break tokens:
#   [uv_break] -- inline pause token
#   [break_X] where X=0-7 -- break intensity levels in refine_text prompt
#   [oral_X] where X=0-9 -- conversational filler intensity
#   [laugh_X] where X=0-2 -- laughter intensity
#
# Key takeaway: intensity-parameterized tokens are effective for models
# trained to recognize them. Fish Speech [slow] works (PASS), so we use it.
# The gradient approach (0-7 levels) is interesting for future work.
```

### Semicolon Injection Pattern (Community Reference)
```javascript
// Source: bagrounds.org/ai-blog/2026-03-10-tts-semicolon-injection
// Simple, idempotent approach for block-level pause injection:
//
// function injectBlockPauses(text) {
//   if (!text) return text
//   if (/[.!?;:]$/.test(text)) return text
//   return text + ";"
// }
//
// Key design: non-destructive (already-punctuated text unchanged),
// idempotent (applying twice = same result), minimal (one character).
// Our approach extends this to mid-sentence clause boundaries.
```

### Integration Point in inference_engine/__init__.py
```python
# Source: fish_speech/inference_engine/__init__.py lines 41-66
# Current flow:
#   1. inference(req) called
#   2. Load references
#   3. send_Llama_request(req, ...) -- req.text goes to generate_long()
#   4. generate_long() calls split_text_into_chunks() at line 900
#
# New flow with preprocessor:
#   1. inference(req) called
#   2. Load references
#   3. preprocessor.preprocess(req.text) -> (modified_text, hints)
#   4. req.text = modified_text (or pass modified_text directly)
#   5. send_Llama_request(req, ...) -- modified text flows to generate_long()
#   6. hints stored for Phase 4 consumption
#
# Integration point: between lines 66-67 in __init__.py (after send_Llama_request
# is too late -- text is already sent). Must intercept BEFORE the request is sent.
# Actually: modify req.text before line 66 (before send_Llama_request).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSML `<break>` tags | Model-native punctuation response | 2024+ (end-to-end models) | End-to-end models like Fish Speech, ChatTTS respond to punctuation directly; SSML layer unnecessary |
| Fixed pause durations | Gaussian/probabilistic duration variation | 2024 (arXiv 2406.05401) | Regression-based duration predictors underestimate variance; Gaussian sampling produces more natural speech |
| Phonemizer-based text frontend | Direct text-to-token (no G2P) | 2024 (Fish Speech, Bark) | LLM-based models process text directly without grapheme-to-phoneme conversion |
| Per-model prosody control | Free-form inline tags | 2025 (Fish Speech S2) | Open-ended natural language descriptions replace fixed tag vocabularies |
| Post-processing speed changes | Text-level rate tags | 2024+ | [slow] tag at text level produces more natural rate variation than audio-domain time-stretching |

**Deprecated/outdated:**
- **SSML for end-to-end models:** Fish Speech S2-Pro has no SSML parser. Inline bracket tags and punctuation are the prosody control mechanism.
- **[pause] and [fast] tags in Fish Speech:** Phase 1 confirmed non-responsive. Do not use.
- **spaCy for lightweight clause detection:** Overkill for this use case; deferred to v3+.

## Open Questions

1. **Exact word-count threshold for clause injection**
   - What we know: D-03 says "8+ words" as the starting point. Tortoise-TTS uses "half the desired length" as a heuristic.
   - What's unclear: Whether 8 is optimal or if 10-12 would avoid false positives on naturally long but fluent phrases.
   - Recommendation: Start with 8, expose as `clause_word_threshold` in PreprocessorConfig for tuning. Phase 5 validation will determine optimal value.

2. **[slow] tag placement precision**
   - What we know: D-07/D-08 say "at emotional transition points" and "preceding emotional/dramatic content." Phase 1 showed 1.068x duration effect.
   - What's unclear: How to detect "emotional transition points" without NLP. Heuristic options: before sentences starting with emotion tags, before exclamatory sentences, before long dramatic sentences.
   - Recommendation: Insert [slow] before sentences that already have emotion tags (e.g., [angry], [sad]) as these are explicitly marked emotional transitions. This is the highest-confidence heuristic without NLP.

3. **HumanismHints survival through text splitting**
   - What we know: Preprocessing runs before split_text_into_chunks(). The hints reference char_offsets in the preprocessed text.
   - What's unclear: After splitting, char_offsets need remapping to per-chunk positions. The existing chunk_offsets from _split_at_boundaries() could enable this.
   - Recommendation: Store hints relative to original preprocessed text. Phase 4 can remap using chunk boundaries when consuming hints. Don't over-engineer remapping in Phase 3.

4. **Multi-speaker text handling**
   - What we know: generate_long() has two paths: multi-speaker (split_text_by_speaker -> group_turns_into_batches) and single-speaker (split_text_into_chunks).
   - What's unclear: Should preprocessor run on the full text before speaker splitting, or per-speaker-turn?
   - Recommendation: Run on full req.text before any splitting. Both paths consume the same text. Preprocessing is speaker-agnostic (punctuation and [slow] tags work regardless of speaker).

## Sources

### Primary (HIGH confidence)
- Fish Speech codebase: `fish_speech/models/text2semantic/inference.py` -- existing regex patterns, split_text_into_chunks(), emotion tag handling
- Fish Speech codebase: `fish_speech/utils/post_fx.py` -- PostFXConfig/HumanismPostFX dataclass pattern to follow
- Fish Speech codebase: `fish_speech/inference_engine/__init__.py` -- integration point, InferenceResult dataclass, inference() flow
- Phase 1 tag testing results: `.planning/phases/01-baseline-measurement/01-02-SUMMARY.md` -- [slow] PASS, [pause] FAIL, [fast] FAIL

### Secondary (MEDIUM confidence)
- [Tortoise-TTS text.py](https://github.com/neonbjb/tortoise-tts/blob/main/tortoise/utils/text.py) -- split_and_recombine_text sentence splitting approach
- [Bark TTS special tokens](https://huggingface.co/suno/bark) -- bracket token convention, nonverbal sounds
- [ChatTTS prosody control](https://github.com/2noise/ChatTTS) -- [uv_break], [break_X], parameterized tokens
- [Semicolon injection for TTS pauses](https://bagrounds.org/ai-blog/2026-03-10-tts-semicolon-injection) -- idempotent punctuation injection pattern
- [Coqui TTS XTTS discussions](https://huggingface.co/coqui/XTTS-v2/discussions/23) -- community patterns for adding pauses via text manipulation
- [arXiv 2406.05401](https://arxiv.org/html/2406.05401v1) -- probabilistic duration models, Gaussian noise for natural speech variation
- [arXiv 2302.13652](https://arxiv.org/abs/2302.13652) -- duration-aware pause insertion for multi-speaker TTS
- [Interspeech 2025: Prosodic patterns from open-source TTS](https://www.isca-archive.org/interspeech_2025/shim25_interspeech.pdf) -- punctuation-induced prosodic contrasts evaluation
- [Purdue OWL comma rules](https://owl.purdue.edu/owl/general_writing/punctuation/commas/extended_rules_for_commas.html) -- FANBOYS comma insertion rules
- [Fish Audio S2 blog](https://fish.audio/blog/fish-audio-open-sources-s2/) -- inline tag architecture, DualAR design

### Tertiary (LOW confidence)
- [ACL W14-5514](https://aclanthology.org/W14-5514.pdf) -- rule-based automatic clause boundary detection (could not fetch full paper)
- [Hume AI TTS API](https://dev.hume.ai/docs/text-to-speech-tts/overview) -- per-chunk metadata streaming pattern (different architecture but similar concept)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, zero dependencies, follows existing codebase patterns
- Architecture: HIGH -- integration points clearly identified in codebase, follows Phase 2 patterns
- Pitfalls: HIGH -- derived from codebase analysis (emotion tag propagation, existing regex patterns)
- Clause detection heuristics: MEDIUM -- regex + conjunction matching is well-established but threshold tuning needs empirical validation
- HumanismHints design: MEDIUM -- no direct precedent in codebase; design informed by community patterns and Phase 4 requirements

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (stable domain -- text preprocessing patterns don't change rapidly)

---
*Phase: 03-text-preprocessor-pauses*
*Researched: 2026-04-13*
