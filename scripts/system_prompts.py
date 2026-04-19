from pathlib import Path

_PROMPT_PATH = Path(__file__).parent / "miyako_system_prompt.md"

SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

SEED_HISTORY = [
    ('User', 'Hey Miyako.'),
    ('Miyako', "[happy] Hey you! [playful] What're we getting into today?"),
]


def build_cache_summary_block(cache_summary: list[dict]) -> str:
    """Build compact one-line-per-report cache summary for Gemma context (D-08)."""
    if not cache_summary:
        return ""
    lines = ["## Active Session Cache\n"]
    for r in cache_summary:
        kind = r.get("kind", "base")
        topic = r.get("topic", "")
        age = r.get("age_seconds", 0)
        deriv = r.get("derivation_summary", "")
        line = f"- [{r['report_id']}] {kind} | {r['row_count']} rows | {topic or r.get('query', '')[:40]}"
        if age:
            line += f" | {age:.0f}s ago"
        if deriv:
            line += f" | {deriv[:80]}"
        lines.append(line)
    return "\n".join(lines)
