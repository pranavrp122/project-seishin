"""Dedicated handler: LLM emits fenced SQL only."""
import json
import re

from .config import SQL_LLM_MAX_TOKENS
from .llm_client import safe_complete
from .prompts import SQL_GENERATION_SYSTEM, schema_snippet


_SQL_FENCE = re.compile(r"```sql\s*([\s\S]*?)\s*```", re.IGNORECASE)


def generate_sql(user_text: str, intent: dict) -> str:
    intent_json = json.dumps(intent, ensure_ascii=False)
    prompt = (
        f"{SQL_GENERATION_SYSTEM}\n"
        f"{schema_snippet()}\n\n"
        f"Intent JSON: {intent_json}\n"
        f'Original user request: """{user_text}"""\n'
    )
    raw = safe_complete(
        prompt,
        max_tokens=SQL_LLM_MAX_TOKENS,
        temperature=0.05,
        stop=["\n\n", "User:", "Nexus:"],
    )
    if not raw:
        return ""
    m = _SQL_FENCE.search(raw)
    if m:
        return m.group(1).strip()
    # Fallback: if model omitted fences but returned SELECT...
    if re.search(r"^\s*select\b", raw, re.IGNORECASE):
        return raw.strip()
    return ""
