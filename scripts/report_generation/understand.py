"""Report mode: turn free text into structured intent JSON via LLM."""
import json
from typing import Optional

from .config import UNDERSTAND_MAX_TOKENS
from .llm_client import safe_complete
from .prompts import REPORT_UNDERSTAND_SYSTEM


def _parse_json_object(raw: str) -> Optional[dict]:
    s = raw.strip()
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(s[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def understand_request(user_text: str) -> dict:
    """Return intent dict; on failure, minimal fallback."""
    prompt = (
        f"{REPORT_UNDERSTAND_SYSTEM}\n\n"
        f'User request (transcript): """{user_text}"""\n'
        "JSON:"
    )
    raw = safe_complete(
        prompt,
        max_tokens=UNDERSTAND_MAX_TOKENS,
        temperature=0.1,
        stop=["\n\nUser:", "\n\nNexus:", "```"],
    )
    if not raw:
        return {
            "topic": user_text[:120],
            "audience": "general",
            "time_window": "unspecified",
            "metrics": [],
        }
    data = _parse_json_object(raw)
    if data is not None:
        return {
            "topic": str(data.get("topic", "")) or user_text[:80],
            "audience": str(data.get("audience", "general") or "general"),
            "time_window": str(data.get("time_window", "unspecified") or "unspecified"),
            "metrics": data.get("metrics") if isinstance(data.get("metrics"), list) else [],
        }
    return {
        "topic": user_text[:120],
        "audience": "general",
        "time_window": "unspecified",
        "metrics": [],
    }
