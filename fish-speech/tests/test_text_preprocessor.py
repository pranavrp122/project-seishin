"""Unit tests for TextPreprocessor: clause injection, [slow] tags, pause hints, breathing cues."""

import random

import pytest

from fish_speech.utils.text_preprocessor import (
    BreathingCue,
    HumanismHints,
    PauseHint,
    PreprocessorConfig,
    RateHint,
    TextPreprocessor,
)


# ---------------------------------------------------------------------------
# Dataclass defaults
# ---------------------------------------------------------------------------

class TestPreprocessorConfig:
    def test_defaults(self):
        """PreprocessorConfig has correct default values."""
        cfg = PreprocessorConfig()
        assert cfg.enable_clause_injection is True
        assert cfg.clause_word_threshold == 8
        assert cfg.enable_slow_tags is True
        assert cfg.enable_pause_hints is True
        assert cfg.pause_jitter_pct == pytest.approx(0.175)
        assert cfg.enable_breathing_cues is True


class TestHumanismHintsDataclass:
    def test_empty_hints(self):
        """HumanismHints defaults to empty lists."""
        hints = HumanismHints(original_text="test")
        assert hints.pause_hints == []
        assert hints.rate_hints == []
        assert hints.breathing_cues == []
        assert hints.original_text == "test"


class TestPauseHintDataclass:
    def test_fields(self):
        """PauseHint has char_offset, duration_ms, source."""
        ph = PauseHint(char_offset=5, duration_ms=150.0, source="comma")
        assert ph.char_offset == 5
        assert ph.duration_ms == 150.0
        assert ph.source == "comma"


class TestRateHintDataclass:
    def test_fields(self):
        """RateHint has char_offset and scope."""
        rh = RateHint(char_offset=0, scope="sentence")
        assert rh.char_offset == 0
        assert rh.scope == "sentence"


class TestBreathingCueDataclass:
    def test_fields(self):
        """BreathingCue has char_offset and probability."""
        bc = BreathingCue(char_offset=10, probability=0.6)
        assert bc.char_offset == 10
        assert bc.probability == 0.6


# ---------------------------------------------------------------------------
# preprocess() basic contract
# ---------------------------------------------------------------------------

class TestPreprocessBasic:
    def test_empty_string(self):
        """preprocess('') returns ('', HumanismHints with empty lists)."""
        tp = TextPreprocessor()
        text, hints = tp.preprocess("")
        assert text == ""
        assert isinstance(hints, HumanismHints)
        assert hints.pause_hints == []
        assert hints.rate_hints == []
        assert hints.breathing_cues == []

    def test_simple_text_preserved(self):
        """preprocess('Hello.') returns 'Hello.' unchanged with original_text set."""
        tp = TextPreprocessor()
        text, hints = tp.preprocess("Hello.")
        assert text == "Hello."
        assert hints.original_text == "Hello."

    def test_return_type_is_tuple(self):
        """preprocess always returns (str, HumanismHints) tuple."""
        tp = TextPreprocessor()
        result = tp.preprocess("Some text here.")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], HumanismHints)


# ---------------------------------------------------------------------------
# Clause boundary injection
# ---------------------------------------------------------------------------

class TestClauseInjection:
    def test_long_span_with_coordinating_conjunction(self):
        """8+ word span with 'and' gets comma injected before conjunction."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess(
            "She walked to the store and bought some milk and bread and cheese"
        )
        # At least one comma should be injected before an "and"
        assert ", and" in text or ",and" in text

    def test_short_text_unchanged(self):
        """Text shorter than threshold gets no comma injection."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("Hello world.")
        assert text == "Hello world."

    def test_already_punctuated_unchanged(self):
        """Already-punctuated text is not modified."""
        tp = TextPreprocessor()
        original = "She said, hello world."
        text, _ = tp.preprocess(original)
        assert text == original

    def test_fully_punctuated_unchanged(self):
        """Fully punctuated text with commas is not modified."""
        tp = TextPreprocessor()
        original = "I went to the store, bought milk, and came home."
        text, _ = tp.preprocess(original)
        assert text == original

    def test_subordinating_conjunction(self):
        """Long span with subordinating conjunction gets comma injection."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess(
            "The old man walked slowly through the park because he enjoyed the scenery"
        )
        assert ", because" in text or ",because" in text

    def test_only_one_comma_per_long_span(self):
        """Only one comma injected per long unpunctuated span."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess(
            "She walked to the store and bought some milk and bread and cheese"
        )
        # Count commas injected (original has zero)
        comma_count = text.count(",")
        assert comma_count == 1

    def test_emotion_tag_not_broken(self):
        """Comma injection does not break emotion tags in brackets."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("[angry] She ran fast and far")
        # [angry] should remain intact
        assert "[angry]" in text

    def test_abbreviation_period_not_sentence_end(self):
        """Abbreviation periods are not treated as sentence ends."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess(
            "He went to Dr. Smith and they talked for hours and then left"
        )
        # Should inject a comma somewhere; the Dr. should not break the span
        assert "," in text

    def test_disabled_via_config(self):
        """enable_clause_injection=False disables comma injection."""
        cfg = PreprocessorConfig(enable_clause_injection=False)
        tp = TextPreprocessor(cfg)
        text, _ = tp.preprocess(
            "She walked to the store and bought some milk and bread and cheese"
        )
        assert "," not in text


# ---------------------------------------------------------------------------
# Double-punctuation cleanup
# ---------------------------------------------------------------------------

class TestDoublePunctuationCleanup:
    def test_no_comma_period(self):
        """After injection, no ',.' patterns remain in output."""
        tp = TextPreprocessor()
        # Force a scenario that could produce double punctuation
        text, _ = tp.preprocess(
            "She walked to the store and bought some milk and bread and cheese."
        )
        assert ",." not in text
        assert ",," not in text
        assert ", ;" not in text


# ---------------------------------------------------------------------------
# [slow] tag insertion
# ---------------------------------------------------------------------------

class TestSlowTagInsertion:
    def test_emotion_tag_gets_slow(self):
        """Sentence with emotion tag gets [slow] prepended."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("[angry] You betrayed me.")
        assert text.startswith("[slow] [angry]")

    def test_no_emotion_no_slow(self):
        """Sentence without emotion tag does not get [slow]."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("Hello world.")
        assert "[slow]" not in text

    def test_multiple_emotion_tags(self):
        """Each emotion-tagged sentence gets its own [slow]."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("[angry] Stop! [sad] I'm sorry.")
        assert "[slow] [angry] Stop!" in text
        assert "[slow] [sad] I'm sorry." in text

    def test_no_double_slow(self):
        """Already-tagged [slow] sentence does not get doubled."""
        tp = TextPreprocessor()
        text, _ = tp.preprocess("[slow] [angry] Already tagged.")
        # Should have exactly one [slow]
        assert text.count("[slow]") == 1

    def test_disabled_via_config(self):
        """enable_slow_tags=False disables [slow] insertion."""
        cfg = PreprocessorConfig(enable_slow_tags=False)
        tp = TextPreprocessor(cfg)
        text, _ = tp.preprocess("[angry] You betrayed me.")
        assert "[slow]" not in text


# ---------------------------------------------------------------------------
# Pause hint generation
# ---------------------------------------------------------------------------

class TestPauseHints:
    def test_pause_hints_at_punctuation(self):
        """Pause hints generated at comma, period positions."""
        tp = TextPreprocessor()
        _, hints = tp.preprocess("Hello, world. How are you?")
        assert len(hints.pause_hints) >= 2  # comma + period + question mark

    def test_pause_hint_sources(self):
        """PauseHint.source is one of the expected values."""
        tp = TextPreprocessor()
        _, hints = tp.preprocess("Hello, world. Wait; think: go!")
        sources = {h.source for h in hints.pause_hints}
        valid_sources = {"comma", "semicolon", "period", "colon", "em_dash", "sentence_boundary"}
        assert sources.issubset(valid_sources)

    def test_pause_hint_has_positive_duration(self):
        """Each PauseHint has positive duration_ms."""
        random.seed(42)
        tp = TextPreprocessor()
        _, hints = tp.preprocess("Hello, world. How are you?")
        for ph in hints.pause_hints:
            assert ph.duration_ms > 0

    def test_jitter_clamps_to_bounds(self):
        """Jittered durations stay within [0.5x, 1.5x] base."""
        random.seed(42)
        tp = TextPreprocessor()
        # Test many iterations to check clamping
        for _ in range(50):
            _, hints = tp.preprocess("Hello, world.")
            for ph in hints.pause_hints:
                if ph.source == "comma":
                    assert 75 <= ph.duration_ms <= 225  # 0.5*150 to 1.5*150
                elif ph.source == "period":
                    assert 175 <= ph.duration_ms <= 525  # 0.5*350 to 1.5*350

    def test_base_duration_comma(self):
        """Comma base duration is around 150ms (within jitter range)."""
        random.seed(42)
        tp = TextPreprocessor(PreprocessorConfig(pause_jitter_pct=0.0))
        _, hints = tp.preprocess("Hello, world.")
        comma_hints = [h for h in hints.pause_hints if h.source == "comma"]
        assert len(comma_hints) >= 1
        # With zero jitter, duration should be exactly 150
        assert comma_hints[0].duration_ms == pytest.approx(150.0)

    def test_disabled_via_config(self):
        """enable_pause_hints=False results in empty pause_hints list."""
        cfg = PreprocessorConfig(enable_pause_hints=False)
        tp = TextPreprocessor(cfg)
        _, hints = tp.preprocess("Hello, world. How are you?")
        assert hints.pause_hints == []


# ---------------------------------------------------------------------------
# Breathing cue generation
# ---------------------------------------------------------------------------

class TestBreathingCues:
    def test_long_phrase_gets_breathing_cue(self):
        """Sentence with 15+ words gets a breathing cue."""
        tp = TextPreprocessor()
        long_text = (
            "The quick brown fox jumped over the lazy dog and then ran through "
            "the forest to find the river."
        )
        _, hints = tp.preprocess(long_text)
        assert len(hints.breathing_cues) >= 1

    def test_short_text_no_breathing_cue(self):
        """Short text (< 15 words) produces no breathing cues."""
        tp = TextPreprocessor()
        _, hints = tp.preprocess("Hello world.")
        assert hints.breathing_cues == []

    def test_breathing_cue_probability_range(self):
        """BreathingCue.probability is between 0.0 and 1.0."""
        tp = TextPreprocessor()
        long_text = (
            "The quick brown fox jumped over the lazy dog and then ran through "
            "the forest to find the river near the mountain."
        )
        _, hints = tp.preprocess(long_text)
        for bc in hints.breathing_cues:
            assert 0.0 <= bc.probability <= 1.0

    def test_disabled_via_config(self):
        """enable_breathing_cues=False results in empty breathing_cues list."""
        cfg = PreprocessorConfig(enable_breathing_cues=False)
        tp = TextPreprocessor(cfg)
        long_text = (
            "The quick brown fox jumped over the lazy dog and then ran through "
            "the forest to find the river."
        )
        _, hints = tp.preprocess(long_text)
        assert hints.breathing_cues == []


# ---------------------------------------------------------------------------
# Integration / full pipeline tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_all_features_together(self):
        """Full preprocess with all features enabled produces valid output."""
        tp = TextPreprocessor()
        text, hints = tp.preprocess(
            "[angry] She walked to the store and bought some milk and bread "
            "and cheese because she needed to feed the family tonight."
        )
        # [slow] should be prepended
        assert "[slow]" in text
        # Comma should be injected
        assert "," in text
        # Pause hints should be present
        assert len(hints.pause_hints) > 0
        # Original text preserved in hints
        assert hints.original_text.startswith("[angry]")

    def test_no_circular_import(self):
        """Module does not import from fish_speech.models (avoids circular imports)."""
        import inspect
        import fish_speech.utils.text_preprocessor as mod
        source = inspect.getsource(mod)
        assert "from fish_speech.models" not in source
        assert "import fish_speech.models" not in source

    def test_no_external_deps(self):
        """Module only uses stdlib (re, random, dataclasses)."""
        import inspect
        import fish_speech.utils.text_preprocessor as mod
        source = inspect.getsource(mod)
        assert "import spacy" not in source
        assert "from spacy" not in source
        assert "import numpy" not in source
        assert "import torch" not in source
