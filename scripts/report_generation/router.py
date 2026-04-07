"""Route voice transcripts into the report pipeline when intent matches."""
import re

# Explicit prefix (recommended in noisy environments) or common report language.
_REPORT_PREFIX = re.compile(r"^\s*nexus\s+report\s*[:,-]?\s+", re.IGNORECASE)
_TOPIC = re.compile(
    r"\b("
    r"generate\s+(a\s+)?report"
    r"|build\s+(a\s+)?dashboard"
    r"|tableau"
    r"|run\s+(a\s+)?query"
    r"|sql\s+report"
    r"|warehouse\s+report"
    r"|analytics\s+report"
    r")\b",
    re.IGNORECASE,
)


def is_report_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _REPORT_PREFIX.search(t):
        return True
    return bool(_TOPIC.search(t))
