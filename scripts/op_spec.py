"""Op spec schema and guided_json call for LLM-guided data operations.

Exports:
    OP_SPEC_SCHEMA        - flat JSON Schema dict for vLLM's guided_json parameter
    OP_SPEC_SYSTEM_PROMPT - system prompt describing all 9 op types for Gemma
    generate_op_spec()    - async function returning structured op spec dict
"""

import json
import os
import time
from collections import deque

import httpx

from system_prompts import build_cache_summary_block
from text_utils import _strip_json_fences

# --- Configuration (same env vars as sei_engine.py, self-contained) ---
LLM_URL = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")
LLM_API_KEY = os.environ.get("SEI_LLM_API_KEY", "")
_LLM_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
MODEL_NAME = os.environ.get("SEI_MODEL_NAME", "gemma-4")

# --- JSON Schema for vLLM constrained decoding ---
# Uses oneOf with a distinct shape per op_type so constrained decoding enforces
# required fields for each op (if/then conditionals are not honored by vLLM's
# guided_json backend, but oneOf is).
_FILTER_OPERATORS = ["eq", "neq", "gt", "lt", "gte", "lte", "between", "in", "contains"]
_AGG_FUNCS = ["sum", "avg", "count", "min", "max"]
_EXPL = {"type": "string"}
_MERGE = {"type": ["boolean", "null"]}
_REPORT_ID = {"type": ["string", "null"]}

OP_SPEC_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "filter"},
                "column": {"type": "string"},
                "operator": {"type": "string", "enum": _FILTER_OPERATORS},
                "value": {"type": ["string", "number", "null"]},
                "value2": {"type": ["string", "number", "null"]},
                "values": {"type": ["array", "null"], "items": {"type": ["string", "number"]}},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "column", "operator", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "sort"},
                "sort_specs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "direction": {"type": "string", "enum": ["asc", "desc"]},
                        },
                        "required": ["column", "direction"],
                    },
                },
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "sort_specs", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "top_n"},
                "column": {"type": "string"},
                "n": {"type": "integer"},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "column", "n", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "bottom_n"},
                "column": {"type": "string"},
                "n": {"type": "integer"},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "column", "n", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "aggregate"},
                "column": {"type": "string"},
                "agg_func": {"type": "string", "enum": _AGG_FUNCS},
                "group_by": {"type": ["array", "null"], "items": {"type": "string"}},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "column", "agg_func", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "pivot"},
                "pivot_index": {"type": "string"},
                "pivot_columns": {"type": "string"},
                "pivot_values": {"type": "string"},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "pivot_index", "pivot_columns", "pivot_values", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "select_columns"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "columns", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "rename_columns"},
                "rename_map": {"type": "object"},
                "report_id": _REPORT_ID,
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "rename_map", "explanation"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "op_type": {"const": "cross_report_compare"},
                "report_id": {"type": "string"},
                "compare_report_id": {"type": "string"},
                "compare_column": {"type": "string"},
                "merge_cached": _MERGE,
                "explanation": _EXPL,
            },
            "required": ["op_type", "report_id", "compare_report_id", "compare_column", "explanation"],
            "additionalProperties": False,
        },
    ],
}

# --- System prompt for op spec generation ---
OP_SPEC_SYSTEM_PROMPT = """\
You translate a user's follow-up request into a structured data operation.

## Output format — CRITICAL
Return a FLAT JSON object with all fields at the TOP level. DO NOT nest fields inside a "params" object. DO NOT invent keys not listed in the examples.

Correct format (for filter):
{"op_type": "filter", "column": "rating_score", "operator": "eq", "value": 3, "explanation": "Filtering for suppliers rated 3."}

WRONG format (NEVER do this):
{"op_type": "filter", "params": {"column": "rating_score", "operator": "eq", "value": 3}, "explanation": "..."}

Every example below shows the expected FLAT top-level structure.

You will see: the user's request, the active session cache summary, and (for the target report) the column schema with sample values.

## Anti-hallucination rules
- Use EXACT column names from the schema — never rename or invent.
- If the user references a column or value NOT in the schema, return op_type="_error". Do not guess.
- If the user's phrasing is ambiguous, pick the most literal interpretation of their actual words.

## Operations

### filter
Filter rows where a column matches a condition.
Use for: "which ones have X", "show me X", AND "how many have X value" (after filtering, the row count IS the count answer).
Required: column, operator, value (value2 for "between", values for "in").
Operators: eq, neq, gt, lt, gte, lte, between, in, contains.
Examples:
- "which ones have rating 3" → filter rating eq 3
- "how many have 4 star" → filter rating eq 4 (row count = the answer)
- "show me ones with lead time under 10" → filter lead_time lt 10
- "suppliers in California" → filter region eq "California"

### sort
Order rows by column(s).
Required: sort_specs=[{column,direction}] OR column+direction.
Examples:
- "sort by revenue descending" → sort revenue desc
- "order them alphabetically" → sort name asc

### top_n
N rows with the LARGEST values in column.
Use for: "highest", "longest", "most", "biggest", "top", "best", "greatest", "maximum", "who takes the longest".
Required: n (default 5), column.
Examples:
- "top 3 by revenue" → top_n n=3 column=revenue
- "who takes the longest" → top_n n=1 column=lead_time
- "longest lead times" → top_n column=lead_time
- "which 3 have the longest lead time" → top_n n=3 column=lead_time

### bottom_n
N rows with the SMALLEST values in column.
Use for: "lowest", "shortest", "cheapest", "fewest", "least", "bottom", "worst", "minimum", "fastest" (when small = better).
Required: n (default 5), column.
Examples:
- "3 fastest suppliers" → bottom_n n=3 column=lead_time
- "lowest ratings" → bottom_n column=rating
- "which 3 have the lowest lead time" → bottom_n n=3 column=lead_time

### aggregate
Sum / avg / count / min / max on a column, optionally grouped.
USE ONLY when the user EXPLICITLY says: "average", "mean", "total", "sum", "combined", "overall".
Required: column, agg_func. Optional: group_by.
Examples THAT ARE aggregate:
- "average rating" → aggregate avg rating
- "total revenue" → aggregate sum revenue
- "sum of orders" → aggregate sum orders
- "what's the mean lead time" → aggregate avg lead_time
Examples that are NOT aggregate (use the op shown instead):
- "how many days is their lead time" → return per-row values (select_columns or pass through). DO NOT average.
- "what's the lead time" across multiple rows → list each value. DO NOT average.
- "who takes the longest" → top_n n=1 (not aggregate max).
- "how many have X value" → filter (row count is the answer, not count aggregate).
- "what is its rating" for a named entity → filter by entity name.
When in doubt, DO NOT aggregate — users want raw per-row values unless they said "average" or "total".

### pivot
Reshape rows into a pivot table.
Required: pivot_index, pivot_columns, pivot_values.

### select_columns
Keep only specific columns.
Required: columns (array).
Use for: "just show me the ratings", "only name and lead time".

### rename_columns
Rename columns.
Required: rename_map (old → new).

### cross_report_compare
Compare two cached reports on a shared column.
Required: report_id (primary), compare_report_id, compare_column.

## merge_cached flag
Set true ONLY when combining COMPLEMENTARY cached reports — separate queries covering different rows of the same topic (e.g. a top-5 report plus a separate rank-6 report, now asked to "sort the top 6").
Do NOT set true when:
- The latest report is a filtered/sorted/aggregated SUBSET of an earlier one (e.g. filtered 20 returns to 4 defective — "check again" should operate on those 4, not re-merge to 20).
- Only one cached report exists.

## Rules
- Use report_id from the cache summary. If only one report exists, use that.
- explanation: one short sentence describing what you're doing (shown to the user).
"""

_SAFE_DEFAULT = {
    "op_type": "_error",
    "explanation": "LLM parse error - could not generate operation spec",
}


def _is_incomplete_spec(spec: dict) -> bool:
    """Return True if the op spec is missing required fields for its op_type."""
    op = spec.get("op_type")
    if op == "filter":
        if not spec.get("column") or not spec.get("operator"):
            return True
    elif op in ("top_n", "bottom_n"):
        if not spec.get("column"):
            return True
    elif op == "aggregate":
        if not spec.get("column") or not spec.get("agg_func"):
            return True
    elif op == "sort":
        if not spec.get("sort_specs") and not (spec.get("column") and spec.get("direction")):
            return True
    elif op == "select_columns":
        if not spec.get("columns"):
            return True
    elif op == "rename_columns":
        if not spec.get("rename_map"):
            return True
    elif op == "pivot":
        if not (spec.get("pivot_index") and spec.get("pivot_columns") and spec.get("pivot_values")):
            return True
    elif op == "cross_report_compare":
        if not (spec.get("compare_report_id") and spec.get("compare_column")):
            return True
    return False

# --- Rolling error rate instrumentation (D-20-05) ---
_OP_SPEC_RESULTS: deque[bool] = deque(maxlen=50)  # True=success, False=error
_OP_SPEC_CALL_COUNT: int = 0


def check_op_spec_health() -> None:
    """Log warning if op_spec error rate is high. Call at startup after loading persistence."""
    if len(_OP_SPEC_RESULTS) >= 10:
        error_count = sum(1 for r in _OP_SPEC_RESULTS if not r)
        rate = error_count / len(_OP_SPEC_RESULTS) * 100
        if rate > 5:
            print(f"[WARNING] op_spec error rate is {rate:.0f}% over last {len(_OP_SPEC_RESULTS)} calls. Consider a prompt audit.")


async def generate_op_spec(user_text: str, cache_summary: list[dict], report_data: dict | None = None) -> dict:
    """Call Gemma with guided_json to get a structured op spec.

    Uses vLLM guided_json to guarantee schema-compliant JSON output.
    Falls back to a safe default on any error.

    Args:
        user_text: The raw user utterance describing the follow-up operation.
        cache_summary: Output from SessionCache.summary() -- metadata only.
        report_data: The actual cached report dict (rows, columns) for the target
                     report. When provided, injects real rows into context so the
                     model works from actual data instead of conversation memory.

    Returns:
        Dict with at minimum: op_type, explanation.
    """
    # Build data context — column schema + sample values only (no full rows).
    # Sending full rows bloats context; the model only needs column names and
    # what values exist to generate accurate filter/sort/aggregate operations.
    if report_data and report_data.get("rows"):
        rows = report_data["rows"]
        columns = report_data.get("columns", {})
        # Collect up to 5 unique sample values per column
        samples: dict[str, list] = {}
        for col in columns:
            seen: list = []
            seen_set: set = set()
            for row in rows:
                val = row.get(col)
                key = str(val)
                if key not in seen_set and len(seen) < 5:
                    seen.append(val)
                    seen_set.add(key)
            samples[col] = seen
        data_context = (
            f"## Report Schema\n"
            f"Query: {report_data.get('query', 'unknown')}\n"
            f"Row count: {report_data.get('row_count', len(rows))}\n"
            f"Columns and sample values:\n"
            + "\n".join(f"  {col} ({dtype}): {json.dumps(samples.get(col, []))}" for col, dtype in columns.items())
            + "\n\nUse EXACT column names above. If the user references a value not in the samples, "
            "set op_type to '_error' so a fresh query can be fired instead of guessing."
        )
    else:
        data_context = build_cache_summary_block(cache_summary)

    messages = [
        {"role": "system", "content": OP_SPEC_SYSTEM_PROMPT},
        {"role": "system", "content": data_context},
        {"role": "user", "content": user_text},
    ]

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.0,
        "stream": False,
        "extra_body": {"guided_json": json.dumps(OP_SPEC_SCHEMA)},
    }

    t0 = time.perf_counter()
    _call_success = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_URL}/v1/chat/completions",
                json=payload,
                headers=_LLM_HEADERS,
                timeout=httpx.Timeout(connect=2.0, read=10.0, write=2.0, pool=2.0),
            )
            resp.raise_for_status()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        content = _strip_json_fences(resp.json()["choices"][0]["message"]["content"])
        result = json.loads(content)
        # Defensive: if Gemma nested fields under "params", hoist them to top level
        if isinstance(result.get("params"), dict):
            for k, v in result["params"].items():
                result.setdefault(k, v)
            del result["params"]

        # Retry once if required fields are missing for the chosen op_type
        if _is_incomplete_spec(result):
            nudge = (
                "Your previous attempt was incomplete. For op_type=filter you MUST include "
                "column (exact name from schema), operator (eq/neq/gt/lt/gte/lte/between/in/contains), "
                "and value. For top_n/bottom_n include column and n. For aggregate include column "
                "and agg_func. Try again and fill in ALL required fields."
            )
            retry_messages = messages + [
                {"role": "assistant", "content": json.dumps(result)},
                {"role": "user", "content": nudge},
            ]
            retry_payload = dict(payload)
            retry_payload["messages"] = retry_messages
            try:
                async with httpx.AsyncClient() as client:
                    resp2 = await client.post(
                        f"{LLM_URL}/v1/chat/completions",
                        json=retry_payload,
                        headers=_LLM_HEADERS,
                        timeout=httpx.Timeout(connect=2.0, read=10.0, write=2.0, pool=2.0),
                    )
                    resp2.raise_for_status()
                content2 = _strip_json_fences(resp2.json()["choices"][0]["message"]["content"])
                retry_result = json.loads(content2)
                if not _is_incomplete_spec(retry_result):
                    result = retry_result
                    print(f"  Op spec: retry succeeded after incomplete first attempt")
                else:
                    print(f"  Op spec: retry still incomplete; keeping first result")
            except Exception as retry_exc:
                print(f"  Op spec: retry failed: {retry_exc}; keeping first result")
            elapsed_ms = (time.perf_counter() - t0) * 1000

        print(
            f"  Op spec: {result['op_type']} ({elapsed_ms:.0f}ms)"
            f" for '{user_text[:50]}'"
        )

        _call_success = result.get("op_type") != "_error"
        return result

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  Op spec error after {elapsed_ms:.0f}ms: {exc}")
        print(f"  Op spec: falling back to safe default for '{user_text[:50]}'")
        _call_success = False
        return dict(_SAFE_DEFAULT)

    finally:
        # D-20-05: track call count and error rate (single increment, WR-02)
        global _OP_SPEC_CALL_COUNT
        _OP_SPEC_RESULTS.append(_call_success)
        _OP_SPEC_CALL_COUNT += 1
        if _OP_SPEC_CALL_COUNT % 10 == 0 and len(_OP_SPEC_RESULTS) >= 10:
            error_count = sum(1 for r in _OP_SPEC_RESULTS if not r)
            rate = error_count / len(_OP_SPEC_RESULTS) * 100
            print(f"[metrics.op_spec_errors] rate={rate:.0f}% (window={len(_OP_SPEC_RESULTS)})")
