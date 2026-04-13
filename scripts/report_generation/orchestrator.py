"""End-to-end report generation: intent → SQL → validate → SQLite → Tableau placeholder → summary."""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .config import MAX_SQL_ROWS, SUMMARY_MAX_TOKENS
from .db_client import execute_read_only_sql, init_warehouse_schema
from . import jobs
from .llm_client import safe_complete
from .prompts import SUMMARY_SYSTEM
from .sql_generation import generate_sql
from .sql_validate import validate_sql
from .tableau_placeholder import placeholder_workbook_link
from .understand import understand_request


def _default_fail_summary(job_id: str, reason: str) -> str:
    return (
        "(serious) I could not finish that report. "
        f"The job id is {job_id} if you want to look it up later. "
        f"Reason: {reason}"
    )


def _spoken_summary_llm(
    user_text: str,
    intent: dict[str, Any],
    row_count: int,
    job_id: str,
    preview_rows: list[dict[str, Any]],
) -> str:
    preview = json.dumps(preview_rows, ensure_ascii=False, default=str)[:1200]
    intent_s = json.dumps(intent, ensure_ascii=False)
    prompt = (
        f"{SUMMARY_SYSTEM}\n\n"
        f"job_id: {job_id}\n"
        f'user_request: """{user_text[:500]}"""\n'
        f"intent: {intent_s}\n"
        f"row_count: {row_count}\n"
        f"first_rows_json: {preview}\n"
        "The user will get a browser link saved on this job; refer to it as the link for this report.\n"
        "Spoken reply:"
    )
    out = safe_complete(
        prompt,
        max_tokens=SUMMARY_MAX_TOKENS,
        temperature=0.4,
        stop=["User:", "Nexus:", "\n\n"],
    )
    if out and len(out) > 15:
        return out.strip()
    # Voice-friendly fallback
    topic = str(intent.get("topic", "your report"))
    return (
        f"(warm) I generated job {job_id} for {topic}. "
        f"I pulled {row_count} rows from the demo database and saved a Tableau placeholder link on that job."
    )


def run_report_pipeline(user_text: str) -> dict[str, Any]:
    """
    Run the full pipeline. Returns keys: ok, job_id, tableau_link, summary, row_count, error (optional).
    `summary` is suitable for TTS (emotion prefix + plain language).
    """
    init_warehouse_schema()
    job_id = str(uuid.uuid4())
    jobs.create_job(job_id, user_text)

    try:
        return _run_report_pipeline_impl(job_id, user_text)
    except Exception as e:  # noqa: BLE001 — last-resort voice-facing error
        err = str(e)
        try:
            jobs.update_job(job_id, status="failed", error=err)
        except Exception:
            pass
        return {
            "ok": False,
            "job_id": job_id,
            "tableau_link": "",
            "summary": _default_fail_summary(job_id, "unexpected error"),
            "row_count": 0,
            "error": err,
        }


def _run_report_pipeline_impl(job_id: str, user_text: str) -> dict[str, Any]:
    intent = understand_request(user_text)
    jobs.update_job(
        job_id,
        parsed_intent_json=json.dumps(intent, ensure_ascii=False),
        status="understood",
    )

    sql_raw = generate_sql(user_text, intent)
    if not sql_raw:
        msg = "The model did not return SQL."
        jobs.update_job(job_id, status="failed", error=msg)
        return {
            "ok": False,
            "job_id": job_id,
            "tableau_link": "",
            "summary": _default_fail_summary(job_id, msg),
            "row_count": 0,
            "error": msg,
        }

    ok, val_msg, sql = validate_sql(sql_raw, MAX_SQL_ROWS)
    if not ok or not sql:
        jobs.update_job(
            job_id,
            sql_text=sql_raw,
            status="failed",
            error=val_msg,
        )
        return {
            "ok": False,
            "job_id": job_id,
            "tableau_link": "",
            "summary": _default_fail_summary(job_id, val_msg),
            "row_count": 0,
            "error": val_msg,
        }

    jobs.update_job(job_id, sql_text=sql, status="sql_validated")

    try:
        rows = execute_read_only_sql(sql, MAX_SQL_ROWS)
    except sqlite3.Error as e:
        err = str(e)
        jobs.update_job(job_id, status="failed", error=err)
        return {
            "ok": False,
            "job_id": job_id,
            "tableau_link": "",
            "summary": _default_fail_summary(job_id, "database error"),
            "row_count": 0,
            "error": err,
        }

    link = placeholder_workbook_link(job_id)
    sample_full = json.dumps(rows[:20], default=str)
    jobs.update_job(
        job_id,
        status="completed",
        row_count=len(rows),
        tableau_link=link,
        sample_result_json=sample_full,
    )

    summary = _spoken_summary_llm(user_text, intent, len(rows), job_id, rows[:5])
    jobs.update_job(job_id, summary_text=summary)

    return {
        "ok": True,
        "job_id": job_id,
        "tableau_link": link,
        "summary": summary,
        "row_count": len(rows),
    }