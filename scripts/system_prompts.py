import re
from pathlib import Path


def _md_to_plain(text: str) -> str:
    """Strip markdown formatting for LLM consumption.

    Keeps all content but removes tables, headers, backticks, bold markers,
    and other markdown syntax that causes smaller models to hallucinate.
    """
    lines = []
    for line in text.split('\n'):
        stripped = line.strip()

        # Skip the document title (# heading)
        if stripped.startswith('# ') and stripped == stripped:
            continue

        # Convert ## and ### headers to plain uppercase labels
        if stripped.startswith('#'):
            label = stripped.lstrip('#').strip()
            if label:
                lines.append(f'\n{label.upper()}')
            continue

        # Skip table separator rows (|---|---|)
        if re.match(r'^\|[-: |]+\|$', stripped):
            continue

        # Convert table header rows and data rows to prose
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            cells = [c for c in cells if c]
            if cells:
                # Skip if it's a header row with no tag/rule content
                lines.append(' | '.join(cells))
            continue

        # Skip horizontal rules
        if stripped in ('---', '***', '___', '----'):
            continue

        lines.append(line)

    result = '\n'.join(lines)

    # Remove code fences (``` blocks)
    result = re.sub(r'```[^\n]*\n', '', result)
    result = re.sub(r'```', '', result)

    # Remove backticks (inline code)
    result = re.sub(r'`([^`]+)`', r'\1', result)
    result = result.replace('`', '')

    # Remove **bold**
    result = re.sub(r'\*\*([^*]+)\*\*', r'\1', result)

    # Remove *italic*
    result = re.sub(r'\*([^*]+)\*', r'\1', result)

    # Remove XML-style blocks
    result = re.sub(r'<[^>]+>', '', result)

    # Collapse 3+ blank lines to 2
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


_PROMPT_FILE = Path(__file__).parent / "miyako_system_prompt.md"
SYSTEM_PROMPT = _md_to_plain(_PROMPT_FILE.read_text(encoding="utf-8"))

SEED_HISTORY = [
    ('User', 'Hey Miyako.'),
    ('Miyako', "[happy] Hey you! [playful] What're we getting into today?"),
]

DODGE_PHRASES = [
    'not sure', "don't know", 'no idea',
    'database', 'glitch', 'cannot', "can't help",
]
