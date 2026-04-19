"""Op spec schema and guided_json call for LLM-guided data operations.

Exports:
    OP_SPEC_SCHEMA        - flat JSON Schema dict for vLLM's guided_json parameter
    OP_SPEC_SYSTEM_PROMPT - system prompt describing all 9 op types for Gemma
    generate_op_spec()    - async function returning structured op spec dict
"""

import json
import os
import time

import httpx

from system_prompts import build_cache_summary_block
from text_utils import _strip_json_fences

# --- Configuration (same env vars as sei_engine.py, self-contained) ---
LLM_URL = os.environ.get("SEI_LLM_URL", "http://127.0.0.1:8000")
LLM_API_KEY = os.environ.get("SEI_LLM_API_KEY", "")
_LLM_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
MODEL_NAME = os.environ.get("SEI_MODEL_NAME", "gemma-4")

# --- JSON Schema for vLLM constrained decoding ---
OP_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "op_type": {
            "type": "string",
            "enum": [
                "filter", "sort", "top_n", "bottom_n",
                "aggregate", "pivot", "select_columns",
                "rename_columns", "cross_report_compare",
            ],
        },
        "report_id": {"type": ["string", "null"]},
        "column": {"type": ["string", "null"]},
        "columns": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
        "value": {"type": ["string", "number", "null"]},
        "value2": {"type": ["string", "number", "null"]},
        "values": {
            "type": ["array", "null"],
            "items": {"type": ["string", "number"]},
        },
        "operator": {
            "type": ["string", "null"],
            "enum": [
                "eq", "neq", "gt", "lt", "gte", "lte",
                "between", "in", "contains", None,
            ],
        },
        "direction": {
            "type": ["string", "null"],
            "enum": ["asc", "desc", None],
        },
        "sort_specs": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "direction": {"type": "string", "enum": ["asc", "desc"]},
                },
                "required": ["column", "direction"],
            },
        },
        "n": {"type": ["integer", "null"]},
        "agg_func": {
            "type": ["string", "null"],
            "enum": ["sum", "avg", "count", "min", "max", None],
        },
        "group_by": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
        "pivot_index": {"type": ["string", "null"]},
        "pivot_columns": {"type": ["string", "null"]},
        "pivot_values": {"type": ["string", "null"]},
        "rename_map": {"type": ["object", "null"]},
        "compare_report_id": {"type": ["string", "null"]},
        "compare_column": {"type": ["string", "null"]},
        "explanation": {"type": "string"},
    },
    "required": ["op_type", "explanation"],
    "additionalProperties": False,
}

# --- System prompt for op spec generation ---
OP_SPEC_SYSTEM_PROMPT = """\
You are an operations interpreter for a data assistant. Given a user's follow-up \
request and the available cached reports, determine what operation to perform.

Return a JSON object with:
- op_type: the operation to perform
- All relevant parameters for that operation
- explanation: a brief natural-language explanation of what you're doing

## Operations

### filter
Filter rows where a column matches a condition.
Required: column, operator, value (and value2 for "between", values for "in")
Operators: eq, neq, gt, lt, gte, lte, between, in, contains

### sort
Sort rows by one or more columns.
Required: sort_specs (array of {column, direction}) OR column + direction

### top_n / bottom_n
Get the N largest/smallest rows by a column.
Required: n (default 5), column (to rank by)

### aggregate
Compute sum/avg/count/min/max on a column, optionally grouped.
Required: column, agg_func. Optional: group_by (array of column names)

### pivot
Reshape data into a pivot table.
Required: pivot_index, pivot_columns, pivot_values

### select_columns
Keep only specific columns.
Required: columns (array of column names)

### rename_columns
Rename columns.
Required: rename_map (object mapping old_name -> new_name)

### cross_report_compare
Compare two cached reports on a shared column.
Required: report_id (primary), compare_report_id, compare_column

## Rules
- Use the report_id from the cache summary. If only one report exists, use that.
- For column names, use EXACT names from the cache summary.
- If the user's request is ambiguous, pick the most likely interpretation.
"""

_SAFE_DEFAULT = {
    "op_type": "_error",
    "explanation": "LLM parse error - could not generate operation spec",
}


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
    # Build data context block — use actual rows when available, fall back to summary
    if report_data and report_data.get("rows"):
        rows_preview = json.dumps(report_data["rows"][:20], default=str)
        columns = report_data.get("columns", {})
        data_context = (
            f"## Target Report Data\n"
            f"Query: {report_data.get('query', 'unknown')}\n"
            f"Columns: {json.dumps(columns)}\n"
            f"Row count: {report_data.get('row_count', len(report_data['rows']))}\n"
            f"Rows (first 20):\n{rows_preview}\n\n"
            "Use EXACT column names from above. Base your operation on the actual data shown."
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

        print(
            f"  Op spec: {result['op_type']} ({elapsed_ms:.0f}ms)"
            f" for '{user_text[:50]}'"
        )
        return result

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  Op spec error after {elapsed_ms:.0f}ms: {exc}")
        print(f"  Op spec: falling back to safe default for '{user_text[:50]}'")
        return dict(_SAFE_DEFAULT)
