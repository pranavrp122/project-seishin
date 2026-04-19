"""Fast-path pattern matching for small-talk messages (D-20-01).

Pre-LLM short-circuit: if a message exactly matches a known small-talk
pattern (after lowercasing, trimming whitespace, stripping trailing
punctuation), route straight to normal_chat without calling classify_intent.

Exports:
    is_fastpath_chat  - returns True if the message is small-talk
    _FASTPATH_PATTERNS - frozenset of all recognized patterns
"""

import re

_TRAILING_PUNCT = re.compile(r"[!.?]+$")

_FASTPATH_PATTERNS: frozenset[str] = frozenset({
    # Greetings
    "hi", "hey", "hello", "yo", "hola", "whats up", "sup",
    "good morning", "good afternoon", "good evening",
    # Addressed
    "hi miyako", "hey miyako",
    # Thanks
    "thanks", "thank you", "thankyou", "thx", "ty", "appreciated",
    # Farewells
    "bye", "goodbye", "see you", "cya", "later", "gtg", "gotta go",
    "good night", "night",
    # Wellbeing
    "how are you", "hows it going", "hows it goin", "how are things", "wyd",
    # Reactions
    "lol", "haha", "lmao", "nice", "cool", "awesome", "sweet", "perfect",
})


def is_fastpath_chat(text: str) -> bool:
    """Return True if the message is a small-talk exact match.

    Normalization: strip whitespace, lowercase, strip trailing !.? characters.
    """
    normalized = _TRAILING_PUNCT.sub("", text.strip().lower())
    return normalized in _FASTPATH_PATTERNS
