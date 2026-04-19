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
    recent = [m for m in history if m.get("role") in ("user", "assistant")][-25:]
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
    last_exc: Exception | None = None
    for attempt in range(2):
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

        except json.JSONDecodeError as exc:
            last_exc = exc
            print(f"  Intent JSON parse error (attempt {attempt + 1}): {exc} — retrying")
        except Exception as exc:
            last_exc = exc
            break

    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"  Intent error after {elapsed_ms:.0f}ms: {last_exc}")
    print(f"  Intent: falling back to normal_chat for '{user_text[:50]}'")
    return dict(_SAFE_DEFAULT)


# --- Follow-up sub-intent: pick which cached report the user means ---

FOLLOWUP_TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "report_id": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["report_id", "confidence"],
    "additionalProperties": False,
}

_FOLLOWUP_TARGET_PROMPT = """You pick which cached report a follow-up question refers to.

Each report has an id, a topic query, a kind (base = original full fetch,
derived = a smaller result from a prior follow-up), a row count, and an age
(most-recent is top of the list).

Rules:
- Default to the most recent BASE report whose topic matches the user's
  wording (e.g. "sort all by rating" after "pull suppliers" -> suppliers base).
- Pick a DERIVED report only when the user uses demonstratives ("these",
  "those", "them", "the top N", "the ones you just showed") or clearly refers
  to the immediately previous smaller result.
- If the user names a different topic ("show me the suppliers again",
  "back to the invoices"), pick the base report matching that topic even if
  it's not the most recent.
- If ambiguous, pick the most recent base.

Respond only with JSON containing the chosen report_id."""


async def classify_followup_target(user_text: str, reports: list[dict]) -> dict:
    """Pick the cached report_id a follow-up refers to.

    reports: list of dicts with keys report_id, query, kind, row_count,
             age_seconds (smallest = newest). Typically the top 10.

    Returns {report_id, confidence}. On any error returns the most-recent
    base report (or first report if none are base).
    """
    if not reports:
        return {"report_id": "", "confidence": 0.0}

    # Build a compact listing for the prompt
    lines = []
    for r in reports:
        lines.append(
            f"- id={r['report_id']} kind={r.get('kind', 'base')} "
            f"rows={r.get('row_count', 0)} age={r.get('age_seconds', 0):.0f}s "
            f"topic={r.get('query', '')[:80]!r}"
        )
    context = "Cached reports (most recent first):\n" + "\n".join(lines) + f"\n\nUser said: {user_text}"

    messages = [
        {"role": "system", "content": _FOLLOWUP_TARGET_PROMPT},
        {"role": "user", "content": context},
    ]
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 40,
        "temperature": 0.0,
        "stream": False,
        "extra_body": {"guided_json": json.dumps(FOLLOWUP_TARGET_SCHEMA)},
    }

    def _fallback() -> dict:
        for r in reports:
            if r.get("kind") == "base":
                return {"report_id": r["report_id"], "confidence": 0.0}
        return {"report_id": reports[0]["report_id"], "confidence": 0.0}

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_URL}/v1/chat/completions",
                json=payload,
                headers=_LLM_HEADERS,
                timeout=httpx.Timeout(connect=2.0, read=4.0, write=2.0, pool=2.0),
            )
            resp.raise_for_status()
        content = _strip_json_fences(resp.json()["choices"][0]["message"]["content"])
        result = json.loads(content)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Validate: returned id must exist in the passed set
        valid_ids = {r["report_id"] for r in reports}
        if result.get("report_id") not in valid_ids:
            print(f"  Followup-target: LLM returned invalid id {result.get('report_id')!r} in {elapsed_ms:.0f}ms -> falling back")
            return _fallback()
        chosen = next(r for r in reports if r["report_id"] == result["report_id"])
        print(
            f"  Followup-target: {result['report_id']} kind={chosen.get('kind')} "
            f"rows={chosen.get('row_count')} (conf={result['confidence']:.2f}) in {elapsed_ms:.0f}ms"
        )
        return result
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  Followup-target error after {elapsed_ms:.0f}ms: {exc} -> fallback")
        return _fallback()
