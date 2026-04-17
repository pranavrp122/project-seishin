from pathlib import Path

_PROMPT_PATH = Path(__file__).parent / "miyako_system_prompt.md"

SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

SEED_HISTORY = [
    ('User', 'Hey Miyako.'),
    ('Miyako', "[happy] Hey you! [playful] What're we getting into today?"),
]


def build_cache_summary_block(cache_summary: list[dict]) -> str:
    """Build compact cache summary text for Gemma context injection. No raw rows."""
    lines = ["## Active Session Cache\n"]
    lines.append("The following reports are available for follow-up operations:\n")
    for r in cache_summary:
        lines.append(f"### Report `{r['report_id']}`")
        lines.append(f"- Original query: \"{r['query']}\"")
        lines.append(f"- Rows: {r['row_count']}")
        cols = ", ".join(f"`{name}` ({dtype})" for name, dtype in r["columns"].items())
        lines.append(f"- Columns: {cols}")
        lines.append("")
    return "\n".join(lines)
