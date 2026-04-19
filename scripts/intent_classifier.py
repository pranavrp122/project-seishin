"""Intent classifier using vLLM guided_json for structured output.

Exports:
    INTENT_SCHEMA  - JSON schema dict for vLLM's guided_json parameter
    classify_intent() - async function returning {intent, data_query, confidence}
"""

import json
import os
import re
import time

import httpx

from intent_prompt import INTENT_SYSTEM_PROMPT
from text_utils import _strip_json_fences

# D-12 guardrail: deterministic verb/pattern set for re-routing low-confidence
# normal_chat to follow_up_on_previous when active report exists.
_FOLLOWUP_VERB_PATTERNS = re.compile(
    r"\b(which|show me|top|lowest|highest|fastest|shortest|longest|"
    r"sort|filter|best|worst|how many|average|total|"
    r"the ones|those with|what about)\b",
    re.IGNORECASE,
)

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
        "opening_phrase": {
            "type": "string",
            "description": "Miyako's short natural opener. For new_data_request: 'On it!' style ack. For follow_up_on_previous: 'Sure thing!' style. For normal_chat: a brief complete reply. Empty string for confirm/cancel.",
        },
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
    "required": ["intent", "data_query", "confidence", "opening_phrase"],
    "additionalProperties": False,
}

_SAFE_DEFAULT = {"intent": "normal_chat", "data_query": None, "confidence": 0.0, "op_chain": None, "opening_phrase": ""}


def _apply_guardrails(result: dict, user_text: str, has_active_report: bool) -> dict:
    """D-12 guardrail: re-route low-confidence normal_chat to follow_up when
    active report exists and utterance contains data-reference verbs."""
    if (
        result["intent"] == "normal_chat"
        and result["confidence"] < 0.8
        and has_active_report
        and _FOLLOWUP_VERB_PATTERNS.search(user_text)
    ):
        print(
            f"  [intent.guardrail] D-12 re-route: normal_chat conf={result['confidence']:.2f} "
            f"-> follow_up_on_previous for '{user_text[:50]}'"
        )
        result["intent"] = "follow_up_on_previous"
        result["confidence"] = max(result["confidence"], 0.6)
    return result


async def classify_intent(
    user_text: str,
    history: list[dict],
    has_active_report: bool,
    last_target: dict | None = None,
) -> dict:
    """Classify a user utterance into one of 5 intents via a single LLM call.

    Uses vLLM guided_json to guarantee schema-compliant JSON output.
    Falls back to normal_chat on any error.

    Args:
        user_text: The raw user utterance to classify.
        history: Recent conversation history (reserved for future use).
        has_active_report: Whether a data report was recently delivered.
        last_target: Most recent cached report (dict with keys like query, topic,
            kind, row_count, columns). Used to resolve elliptical follow-ups
            like "and 5 star?" that reference a prior filter/aggregation.

    Returns:
        Dict with keys: intent, data_query, confidence.
    """
    # Build prior-turn context: last 5 user messages + last 2 assistant replies
    # (extra context helps the classifier disambiguate terse follow-ups).
    convo = [m for m in history if m.get("role") in ("user", "assistant")]
    last_user_msgs = [m for m in convo if m["role"] == "user"][-5:]
    last_assistant = [m for m in convo if m["role"] == "assistant"][-5:]
    prior_lines: list[str] = []
    if last_user_msgs:
        prior_lines.append("Recent user messages (oldest→newest):")
        for m in last_user_msgs:
            prior_lines.append(f"  - {m['content'][:300]}")
    if last_assistant:
        prior_lines.append("Recent assistant replies (what was spoken back — use to resolve what 'it', 'those', 'and 3?' refer to):")
        for m in last_assistant:
            prior_lines.append(f"  - {m['content'][:400]}")
    if last_target:
        cols = list((last_target.get("columns") or {}).keys()) if isinstance(last_target.get("columns"), dict) else (last_target.get("columns") or [])
        prior_lines.append(
            "Last resolved report target: "
            f"topic={last_target.get('topic') or last_target.get('query', '')[:60]!r}, "
            f"kind={last_target.get('kind', 'base')}, "
            f"row_count={last_target.get('row_count', '?')}, "
            f"columns={cols[:12]}"
        )
    prior_block = ""
    if prior_lines:
        prior_block = (
            "\n\n## Prior Turn Context\n"
            + "\n".join(prior_lines)
            + "\nUse this to resolve pronouns, references ('those', 'that'), and terse elliptical "
            "follow-ups like 'and 5 star?' or 'what about 4?' that reuse the prior filter/column."
        )

    messages = [{"role": "system", "content": INTENT_SYSTEM_PROMPT + prior_block}]

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
        "max_tokens": 150,
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
                    timeout=httpx.Timeout(connect=2.0, read=8.0, write=2.0, pool=2.0),
                )
                resp.raise_for_status()

            elapsed_ms = (time.perf_counter() - t0) * 1000
            content = _strip_json_fences(resp.json()["choices"][0]["message"]["content"])
            result = json.loads(content)

            # Ensure opening_phrase present (backward compat with older model outputs)
            result.setdefault("opening_phrase", "")
            result = _apply_guardrails(result, user_text, has_active_report)
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
    # Context-aware fallback: if an active report exists and the utterance looks
    # like a data follow-up, preserve conversation continuity instead of dumping
    # into normal_chat. Same heuristic as the D-12 guardrail.
    fallback = dict(_SAFE_DEFAULT)
    if has_active_report and _FOLLOWUP_VERB_PATTERNS.search(user_text):
        fallback["intent"] = "follow_up_on_previous"
        fallback["confidence"] = 0.5
        print(f"  Intent: LLM error fallback -> follow_up_on_previous for '{user_text[:50]}'")
    else:
        print(f"  Intent: falling back to normal_chat for '{user_text[:50]}'")
    return fallback


# --- Follow-up sub-intent: pick which cached report the user means ---

FOLLOWUP_TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "report_id": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reason": {"type": "string"},
    },
    "required": ["report_id", "confidence", "reason"],
    "additionalProperties": False,
}

_FOLLOWUP_TARGET_PROMPT = """You pick which cached report a follow-up question refers to.

Each report has an id, a topic query, a kind (base = original full fetch,
derived = a smaller result from a prior follow-up), a row count, an age
(most-recent is top of the list), and a derivation summary (how it was
produced from its parent, if derived).

Rules:
- Default to the most recent BASE report whose topic matches the user's
  wording (e.g. "sort all by rating" after "pull suppliers" -> suppliers base).
- Pick a DERIVED report only when the user uses demonstratives ("these",
  "those", "them", "the top N", "the ones you just showed") or clearly refers
  to the immediately previous smaller result.
- If the user names a different topic ("show me the suppliers again",
  "back to the invoices"), pick the base report matching that topic even if
  it's not the most recent.
- Scope-widening overrides demonstrative: if the user says "all", "every",
  "the full list", "not just X", or contrasts against a prior smaller result
  ("rank ALL departments by revenue, not just the few"), pick the BASE for
  that topic even if a derived is newer. The user is explicitly asking to go
  back to the full dataset.
- If ambiguous, pick the most recent base.

Examples:
- History: [derived (3 rows, "top 3 by rating"), base (16 rows, "all suppliers")]
  User: "sort those by lead time" -> derived (demonstrative "those")
- History: [derived (3 rows, "top 3 by rating"), base (16 rows, "all suppliers")]
  User: "rank all of them by lead time" -> base ("all" widens scope back to full set)
- History: [derived (5 rows, "departments with revenue > 1M"), base (40 rows, "all departments")]
  User: "rank all departments by revenue, not just the few" -> base (explicit contrast)
- History: [derived (10 rows, "top 10 invoices"), base (200 rows, "all invoices")]
  User: "which ones are overdue" -> derived (no scope-widening cue)

Respond only with JSON containing the chosen report_id."""


async def classify_followup_target(user_text: str, reports: list[dict], op_context: dict | None = None, history: list[dict] | None = None) -> dict:
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
        deriv = r.get('derivation_summary', '')
        deriv_part = f" derivation={deriv[:100]!r}" if deriv else ""
        cols = r.get('columns', {})
        cols_part = f" columns=[{', '.join(list(cols.keys())[:15])}]" if cols else ""
        lines.append(
            f"- id={r['report_id']} kind={r.get('kind', 'base')} "
            f"rows={r.get('row_count', 0)} age={r.get('age_seconds', 0):.0f}s "
            f"topic={r.get('query', '')[:80]!r}{deriv_part}{cols_part}"
        )
    op_hint = ""
    if op_context:
        op_type = op_context.get("op_type", "unknown")
        columns = ", ".join(op_context.get("columns", []))
        op_hint = f"\n\nThe user's intended operation is: {op_type} on column(s) {columns}. Prefer the widest report that contains those columns."

    # Prior-turn context: terse follow-ups like "and 3?" need the previous
    # exchange to resolve which column/filter the fragment is referencing.
    prior = ""
    if history:
        convo = [m for m in history if m.get("role") in ("user", "assistant")]
        prev_users = [m for m in convo if m["role"] == "user"][-3:]
        prev_assts = [m for m in convo if m["role"] == "assistant"][-3:]
        lines_p: list[str] = []
        if prev_users:
            lines_p.append("Recent user messages (oldest→newest):")
            for m in prev_users:
                lines_p.append(f"  - {m['content'][:250]}")
        if prev_assts:
            lines_p.append("Recent assistant replies:")
            for m in prev_assts:
                lines_p.append(f"  - {m['content'][:350]}")
        if lines_p:
            prior = (
                "\n\nPrior turn context (use to resolve terse fragments like 'and 3?' "
                "which reuse the previous filter/column):\n" + "\n".join(lines_p)
            )

    context = "Cached reports (most recent first):\n" + "\n".join(lines) + f"\n\nUser said: {user_text}" + op_hint + prior

    messages = [
        {"role": "system", "content": _FOLLOWUP_TARGET_PROMPT},
        {"role": "user", "content": context},
    ]
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 80,
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
        conf = float(result.get("confidence", 0.0))
        print(
            f"  Followup-target: {result['report_id']} kind={chosen.get('kind')} "
            f"rows={chosen.get('row_count')} (conf={conf:.2f}) in {elapsed_ms:.0f}ms"
        )
        return {"report_id": result["report_id"], "confidence": conf, "reason": result.get("reason", "")}
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  Followup-target error after {elapsed_ms:.0f}ms: {exc} -> fallback")
        return _fallback()
