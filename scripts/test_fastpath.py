"""Unit tests for fast-path pattern matching (D-20-01)."""

import pytest
from fastpath_patterns import is_fastpath_chat, _FASTPATH_PATTERNS


class TestFastpathPatterns:
    """Verify the frozen pattern set."""

    def test_pattern_count(self):
        """Pattern set has exactly 40 entries (per SCOPE.md D-20-01)."""
        assert len(_FASTPATH_PATTERNS) == 40

    def test_patterns_are_frozenset(self):
        assert isinstance(_FASTPATH_PATTERNS, frozenset)

    def test_all_patterns_lowercase(self):
        for p in _FASTPATH_PATTERNS:
            assert p == p.lower(), f"Pattern {p!r} is not lowercase"


class TestIsFastpathChat:
    """Verify matching behavior: case, punctuation, whitespace."""

    # --- Greetings ---
    def test_hi(self):
        assert is_fastpath_chat("hi") is True

    def test_hi_uppercase(self):
        assert is_fastpath_chat("HI") is True

    def test_hello_trailing_bang(self):
        assert is_fastpath_chat("hello!") is True

    def test_hello_trailing_ellipsis(self):
        assert is_fastpath_chat("hello...") is True

    def test_good_morning(self):
        assert is_fastpath_chat("good morning") is True

    # --- Addressed ---
    def test_hey_miyako(self):
        assert is_fastpath_chat("hey miyako") is True

    def test_hi_miyako(self):
        assert is_fastpath_chat("hi miyako") is True

    # --- Thanks ---
    def test_appreciated(self):
        assert is_fastpath_chat("appreciated") is True

    def test_thank_you(self):
        assert is_fastpath_chat("thank you") is True

    def test_thx(self):
        assert is_fastpath_chat("thx") is True

    # --- Farewells ---
    def test_good_night_with_punct(self):
        assert is_fastpath_chat("good night!") is True

    def test_bye(self):
        assert is_fastpath_chat("bye") is True

    def test_cya(self):
        assert is_fastpath_chat("cya") is True

    # --- Wellbeing ---
    def test_how_are_you_trailing_question(self):
        assert is_fastpath_chat("how are you?") is True

    def test_wyd(self):
        assert is_fastpath_chat("wyd") is True

    def test_hows_it_going(self):
        assert is_fastpath_chat("hows it going") is True

    # --- Reactions ---
    def test_lol(self):
        assert is_fastpath_chat("lol") is True

    def test_awesome(self):
        assert is_fastpath_chat("awesome") is True

    # --- Normalization ---
    def test_whitespace_trimmed(self):
        assert is_fastpath_chat("  hey  ") is True

    def test_mixed_case_and_punct(self):
        assert is_fastpath_chat("HELLO!!!") is True

    def test_trailing_dots_and_question(self):
        assert is_fastpath_chat("how are you?..") is True

    # --- Negative cases ---
    def test_empty_string(self):
        assert is_fastpath_chat("") is False

    def test_data_request(self):
        assert is_fastpath_chat("show me sales data") is False

    def test_hi_there_not_in_set(self):
        assert is_fastpath_chat("hi there") is False

    def test_show_me_revenue(self):
        assert is_fastpath_chat("show me revenue") is False

    def test_partial_match_not_accepted(self):
        assert is_fastpath_chat("hello world") is False

    def test_only_punctuation(self):
        assert is_fastpath_chat("!!!") is False

    def test_whitespace_only(self):
        assert is_fastpath_chat("   ") is False
