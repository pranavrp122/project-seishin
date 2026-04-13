"""TextPreprocessor: Text-level preprocessing for TTS humanism.

Injects clause boundary commas, [slow] tags before emotional sentences,
generates pause hints with Gaussian jitter, and marks breathing cue positions.

Returns preprocessed text paired with HumanismHints metadata for downstream
audio processing (Phase 4).

Usage:
    from fish_speech.utils.text_preprocessor import TextPreprocessor, PreprocessorConfig

    tp = TextPreprocessor(PreprocessorConfig())
    text, hints = tp.preprocess("She walked to the store and bought some milk.")
"""

import random
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level for performance)
# ---------------------------------------------------------------------------

# Coordinating conjunctions (FANBOYS)
_COORD_CONJ = re.compile(r"(?<=\s)(and|but|or|nor|yet|so|for)\s", re.IGNORECASE)

# Subordinating conjunctions
_SUBORD_CONJ = re.compile(
    r"(?<=\s)(which|because|although|while|whereas|since|unless|until|"
    r"though|where|when|if|after|before)\s",
    re.IGNORECASE,
)

# Emotion tag: [word] optionally followed by whitespace (same as inference.py)
_EMOTION_TAG = re.compile(r"\[([a-zA-Z]{2,12})\]\s*")

# Double-punctuation cleanup after injection
_DOUBLE_PUNCT = re.compile(r",\s*([,;:.!?])")

# Punctuation positions for pause hints
_PUNCT_POSITIONS = re.compile(r"[,;:.!?\u2014]|(?:--)")

# Sentence boundary for splitting (lookbehind after .!?)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# Common abbreviations -- periods after these are NOT sentence ends
_ABBREVIATIONS = frozenset(
    {
        "Dr", "Mr", "Mrs", "Ms", "Prof", "Jr", "Sr", "St", "vs", "etc",
        "Rev", "Gen", "Sgt", "Cpl", "Inc", "Ltd", "Corp", "Ave", "Blvd",
        "Dept", "Fig", "Vol", "No", "Capt", "Lt", "Col", "Maj",
    }
)

# ---------------------------------------------------------------------------
# Pause duration constants
# ---------------------------------------------------------------------------

_PAUSE_DURATIONS: dict[str, float] = {
    ",": 150, ";": 250, ".": 350, ":": 200,
    "!": 350, "?": 350, "\u2014": 200, "--": 200,
}

_PAUSE_SOURCE: dict[str, str] = {
    ",": "comma", ";": "semicolon", ".": "period", ":": "colon",
    "!": "period", "?": "period", "\u2014": "em_dash", "--": "em_dash",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PreprocessorConfig:
    """Configuration for TextPreprocessor feature toggles and thresholds."""

    enable_clause_injection: bool = True
    clause_word_threshold: int = 8
    enable_slow_tags: bool = True
    enable_pause_hints: bool = True
    pause_jitter_pct: float = 0.175
    enable_breathing_cues: bool = True


@dataclass
class PauseHint:
    """Metadata for a pause at a specific text position."""

    char_offset: int
    duration_ms: float
    source: str


@dataclass
class RateHint:
    """Metadata for a speech rate change at a specific text position."""

    char_offset: int
    scope: str


@dataclass
class BreathingCue:
    """Metadata for a breathing cue before a long phrase."""

    char_offset: int
    probability: float


@dataclass
class HumanismHints:
    """Paired metadata returned alongside preprocessed text.

    Carries pause hints, rate hints, and breathing cues for downstream
    audio post-processing (Phase 4).
    """

    original_text: str = ""
    pause_hints: list[PauseHint] = field(default_factory=list)
    rate_hints: list[RateHint] = field(default_factory=list)
    breathing_cues: list[BreathingCue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TextPreprocessor
# ---------------------------------------------------------------------------


class TextPreprocessor:
    """Text-level preprocessing engine for TTS humanism.

    Transforms raw input text by injecting clause-boundary commas,
    inserting [slow] tags before emotional sentences, and generating
    HumanismHints metadata (pause hints, breathing cues) for downstream
    audio processing.

    Stateless: each preprocess() call is independent.
    """

    def __init__(self, config: PreprocessorConfig | None = None) -> None:
        self._config = config or PreprocessorConfig()

    def preprocess(self, text: str) -> tuple[str, HumanismHints]:
        """Preprocess text and generate humanism metadata.

        Steps:
            1. Strip whitespace, early return on empty
            2. Inject clause-boundary commas (if enabled)
            3. Insert [slow] tags before emotion-tagged sentences (if enabled)
            4. Generate pause hints at punctuation positions (if enabled)
            5. Generate breathing cues for long phrases (if enabled)

        Returns:
            Tuple of (preprocessed_text, HumanismHints).
        """
        text = text.strip()
        if not text:
            return ("", HumanismHints())

        original_text = text

        # Step 1: Clause boundary comma injection
        if self._config.enable_clause_injection:
            text = self._inject_clause_commas(text)

        # Step 2: [slow] tag insertion
        if self._config.enable_slow_tags:
            text = self._insert_slow_tags(text)

        # Step 3: Pause hints
        pause_hints: list[PauseHint] = []
        if self._config.enable_pause_hints:
            pause_hints = self._generate_pause_hints(text)

        # Step 4: Breathing cues
        breathing_cues: list[BreathingCue] = []
        if self._config.enable_breathing_cues:
            breathing_cues = self._generate_breathing_cues(text)

        hints = HumanismHints(
            original_text=original_text,
            pause_hints=pause_hints,
            rate_hints=[],
            breathing_cues=breathing_cues,
        )

        return (text, hints)

    # -------------------------------------------------------------------
    # Clause boundary comma injection
    # -------------------------------------------------------------------

    def _inject_clause_commas(self, text: str) -> str:
        """Inject commas at clause boundaries in long unpunctuated spans.

        Finds spans of text without punctuation that are >= clause_word_threshold
        words long, then inserts a comma before the first coordinating or
        subordinating conjunction that has enough words on each side.

        Only one comma is injected per long span. Existing punctuation and
        emotion tags are preserved.
        """
        sentences = self._split_sentences(text)
        result_parts = []

        for sentence in sentences:
            result_parts.append(self._inject_commas_in_sentence(sentence))

        result = " ".join(result_parts)

        # Clean up double punctuation
        result = _DOUBLE_PUNCT.sub(r"\1", result)

        return result

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentence-like segments, preserving boundaries."""
        parts = _SENTENCE_BOUNDARY.split(text)
        return [p for p in parts if p.strip()]

    def _inject_commas_in_sentence(self, sentence: str) -> str:
        """Inject a comma in a single sentence if it has a long unpunctuated span."""
        # Strip any leading tags (emotion, slow) for analysis
        stripped = sentence
        prefix_tags = ""
        while True:
            m = re.match(r"^\s*\[[a-zA-Z]{2,12}\]\s*", stripped)
            if m:
                prefix_tags += m.group()
                stripped = stripped[m.end():]
            else:
                break

        # Check if the stripped sentence has punctuation already
        # (commas, semicolons, colons, em-dashes)
        if re.search(r"[,;:\u2014]|(?:--)", stripped):
            return sentence

        # Count words in the stripped sentence
        words = stripped.split()
        if len(words) < self._config.clause_word_threshold:
            return sentence

        # Try coordinating conjunctions first
        best_pos = self._find_conjunction_position(stripped, words, _COORD_CONJ, 3, 3)
        if best_pos is None:
            # Try subordinating conjunctions
            best_pos = self._find_conjunction_position(stripped, words, _SUBORD_CONJ, 4, 3)

        if best_pos is not None:
            # Insert comma before the conjunction in the original sentence
            # We need to map best_pos (in stripped) back to the sentence
            offset = len(prefix_tags)
            insert_pos = offset + best_pos
            sentence = sentence[:insert_pos] + "," + sentence[insert_pos:]

        return sentence

    def _find_conjunction_position(
        self,
        text: str,
        words: list[str],
        pattern: re.Pattern,
        min_before: int,
        min_after: int,
    ) -> int | None:
        """Find the best conjunction position for comma injection.

        Returns the char offset in `text` where a comma should be inserted
        (right before the conjunction), or None if no suitable position found.
        """
        for match in pattern.finditer(text):
            conj_start = match.start()
            # The match includes a leading space (from lookbehind), but start()
            # points after the space. We want to insert comma before the space+conjunction.
            # Count words before and after
            before_text = text[:conj_start].strip()
            after_text = text[match.end():].strip()
            words_before = len(before_text.split()) if before_text else 0
            words_after = len(after_text.split()) if after_text else 0

            if words_before >= min_before and words_after >= min_after:
                # Insert position: right before the space preceding the conjunction
                # The lookbehind consumed a space, so conj_start is right after a space.
                # We want to insert before that space.
                # Find the space before the conjunction
                insert_at = conj_start
                # Back up to the space
                while insert_at > 0 and text[insert_at - 1] == " ":
                    insert_at -= 1
                return insert_at

        return None

    # -------------------------------------------------------------------
    # [slow] tag insertion
    # -------------------------------------------------------------------

    def _insert_slow_tags(self, text: str) -> str:
        """Insert [slow] tags before sentences that contain emotion tags.

        Only inserts [slow] if the sentence starts with an emotion tag
        (like [angry]) and does not already have [slow].
        """
        sentences = _SENTENCE_BOUNDARY.split(text)
        result_parts = []

        for sentence in sentences:
            stripped = sentence.strip()
            if not stripped:
                continue

            # Check if this sentence starts with an emotion tag
            # (possibly after whitespace)
            clean = stripped.lstrip()

            # Check if already has [slow]
            if clean.startswith("[slow]"):
                result_parts.append(stripped)
                continue

            # Check for emotion tag at start
            if _EMOTION_TAG.match(clean):
                result_parts.append("[slow] " + stripped)
            else:
                result_parts.append(stripped)

        return " ".join(result_parts)

    # -------------------------------------------------------------------
    # Pause hint generation
    # -------------------------------------------------------------------

    def _generate_pause_hints(self, text: str) -> list[PauseHint]:
        """Generate pause hints at punctuation positions in text.

        Each hint has a base duration with Gaussian jitter applied.
        """
        hints: list[PauseHint] = []

        for match in _PUNCT_POSITIONS.finditer(text):
            punct = match.group()
            if punct not in _PAUSE_DURATIONS:
                continue

            base_ms = _PAUSE_DURATIONS[punct]
            source = _PAUSE_SOURCE[punct]
            duration = self._jittered_duration(base_ms)

            hints.append(
                PauseHint(
                    char_offset=match.start(),
                    duration_ms=duration,
                    source=source,
                )
            )

        return hints

    def _jittered_duration(self, base_ms: float) -> float:
        """Apply Gaussian jitter to a base duration, clamped to [0.5x, 1.5x].

        Uses random.gauss with sigma = base_ms * pause_jitter_pct.
        """
        sigma = base_ms * self._config.pause_jitter_pct
        jittered = random.gauss(base_ms, sigma)
        lo = 0.5 * base_ms
        hi = 1.5 * base_ms
        return max(lo, min(hi, jittered))

    # -------------------------------------------------------------------
    # Breathing cue generation
    # -------------------------------------------------------------------

    def _generate_breathing_cues(self, text: str) -> list[BreathingCue]:
        """Generate breathing cues before long phrases (15+ words).

        Probability is based on phrase length:
            - 15-20 words: 0.3
            - 20-30 words: 0.6
            - 30+ words:   0.9
        """
        cues: list[BreathingCue] = []
        sentences = _SENTENCE_BOUNDARY.split(text)
        char_offset = 0

        for sentence in sentences:
            stripped = sentence.strip()
            if not stripped:
                char_offset += len(sentence) + 1  # +1 for the split boundary
                continue

            # Count words (strip tags for counting)
            clean = re.sub(r"\[[a-zA-Z]{2,12}\]\s*", "", stripped)
            word_count = len(clean.split())

            if word_count >= 15:
                # Determine probability based on word count
                if word_count >= 30:
                    prob = 0.9
                elif word_count >= 20:
                    prob = 0.6
                else:
                    prob = 0.3

                # Find actual offset in original text
                pos = text.find(stripped, char_offset)
                if pos >= 0:
                    cues.append(BreathingCue(char_offset=pos, probability=prob))

            char_offset += len(sentence) + 1

        return cues
