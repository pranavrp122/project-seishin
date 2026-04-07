"""Persist report job metadata for re-linking and audit."""
import json
from typing import Any, Optional

from .db_client import _conn, init_warehouse_schema


def create_job(
    job_id: str,
    user_request: str,
) -> None:
    init_warehouse_schema()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO report_jobs (job_id, user_request, status)
            VALUES (?, ?, 'started')
            """,
            (job_id, user_request),
        )
        conn.commit()


def update_job(
    job_id: str,
    *,
    parsed_intent_json: Optional[str] = None,
    sql_text: Optional[str] = None,
    status: Optional[str] = None,
    row_count: Optional[int] = None,
    error: Optional[str] = None,
    tableau_link: Optional[str] = None,
    summary_text: Optional[str] = None,
    sample_result_json: Optional[str] = None,
) -> None:
    init_warehouse_schema()
    fields: list[str] = []
    values: list[Any] = []
    if parsed_intent_json is not None:
        fields.append("parsed_intent_json = ?")
        values.append(parsed_intent_json)
    if sql_text is not None:
        fields.append("sql_text = ?")
        values.append(sql_text)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if row_count is not None:
        fields.append("row_count = ?")
        values.append(row_count)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if tableau_link is not None:
        fields.append("tableau_link = ?")
        values.append(tableau_link)
    if summary_text is not None:
        fields.append("summary_text = ?")
        values.append(summary_text)
    if sample_result_json is not None:
        fields.append("sample_result_json = ?")
        values.append(sample_result_json)
    if not fields:
        return
    values.append(job_id)
    with _conn() as conn:
        conn.execute(
            f"UPDATE report_jobs SET {', '.join(fields)} WHERE job_id = ?",
            values,
        )
        conn.commit()


def job_to_dict(job_id: str) -> Optional[dict[str, Any]]:
    init_warehouse_schema()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM report_jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    for k in ("parsed_intent_json", "sample_result_json"):
        if d.get(k) and isinstance(d[k], str):
            try:
                d[k + "_parsed"] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
