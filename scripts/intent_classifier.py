"""Intent classifier using vLLM guided_json for structured output.

Exports:
    INTENT_SCHEMA  - JSON schema dict for vLLM's guided_json parameter
    classify_intent() - async function returning {intent, data_query, confidence}
"""

import json
import os
import time

import httpx

from intent_prompt import INTENT_SYSTEM_PROMPT
from text_utils import _strip_json_fences

# --- Configuration (same env vars as sei_engine.py, self-contained) ---
LLM_URL = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")
LLM_API_KEY = os.environ.get("SEI_LLM_API_KEY", "")
_LLM_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
MODEL_NAME = os.environ.get("SEI_MODEL_NAME", "gemma-4")

# --- JSON Schema for vLLM constrained decoding ---
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "new_data_request",
                "follow_up_on_previous",
                "confirm",
                "cancel",
                "list_cached_data",
                "normal_chat",
                "undo",
                "what_can_i_ask",
                "compare_reports",
            ],
        },
        "data_query": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "op_chain": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "op_type": {
                        "type": "string",
                        "enum": ["filter", "sort", "top_n", "bottom_n", "aggregate"],
                    },
                    "column": {"type": ["string", "null"]},
                    "direction": {"type": ["string", "null"]},
                    "n": {"type": ["integer", "null"]},
                    "value": {},
                    "operator": {"type": ["string", "null"]},
                },
                "required": ["op_type"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intent", "data_query", "confidence"],
    "additionalProperties": False,
}

_SAFE_DEFAULT = {"intent": "normal_chat", "data_query": None, "confidence": 0.0, "op_chain": None}


async def classify_intent(
    user_text: str,
    history: list[dict],
    has_active_report: bool,
) -> dict:
    """Classify a user utterance into one of 5 intents via a single LLM call.

    Uses vLLM guided_json to guarantee schema-compliant JSON output.
    Falls back to normal_chat on any error.

    Args:
        user_text: The raw user utterance to classify.
        history: Recent conversation history (reserved for future use).
        has_active_report: Whether a data report was recently delivered.

    Returns:
        Dict with keys: intent, data_query, confidence.
    """
    # Build history context block (last 4 non-system turns, D-01)
    recent = [m for m in history if m.get("role") in ("user", "assistant")][-4:]
    history_block = ""
    if recent:
        lines = [f"  {m['role'].title()}: {m['content'][:100]}" for m in recent]
        history_block = (
            "\n\n## Recent Conversation\n"
            + "\n".join(lines)
            + "\nUse this to resolve pronouns and references like 'those', 'that', 'compare the two'."
        )

    messages = [{"role": "system", "content": INTENT_SYSTEM_PROMPT + history_block}]

    if has_active_report:
        messages.append(
            {
                "role": "system",
                "content": (
                    "A data report was recently delivered in this conversation. "
                    "follow_up_on_previous is valid."
                ),
            }
        )

    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 80,
        "temperature": 0.0,
        "stream": False,
        "extra_body": {"guided_json": json.dumps(INTENT_SCHEMA)},
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_URL}/v1/chat/completions",
                json=payload,
                headers=_LLM_HEADERS,
                timeout=httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0),
            )
            resp.raise_for_status()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        content = _strip_json_fences(resp.json()["choices"][0]["message"]["content"])
        result = json.loads(content)

        print(f"  Intent latency: {elapsed_ms:.0f}ms")
        print(
            f"  Intent: {result['intent']} (conf={result['confidence']:.2f})"
            f" for '{user_text[:50]}'"
        )
        return result

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  Intent error after {elapsed_ms:.0f}ms: {exc}")
        print(f"  Intent: falling back to normal_chat for '{user_text[:50]}'")
        return dict(_SAFE_DEFAULT)
