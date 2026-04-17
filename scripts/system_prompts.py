from pathlib import Path

_PROMPT_PATH = Path(__file__).parent / "miyako_system_prompt.md"

SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

SEED_HISTORY = [
    ('User', 'Hey Miyako.'),
    ('Miyako', "[happy] Hey you! [playful] What're we getting into today?"),
]
