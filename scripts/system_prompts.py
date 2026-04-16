from pathlib import Path

_PROMPT_FILE = Path(__file__).parent / "miyako_system_prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")

SEED_HISTORY = [
    ('User', 'Hey Miyako.'),
    ('Miyako', "[happy] Hey you! [playful] What're we getting into today?"),
]

DODGE_PHRASES = [
    'not sure', "don't know", 'no idea',
    'database', 'glitch', 'cannot', "can't help",
]
