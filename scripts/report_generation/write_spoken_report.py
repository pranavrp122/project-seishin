"""Write report pipeline spoken-style summary to disk instead of TTS (see nexus_engine report path)."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .config import SPOKEN_REPORT_OUTPUT_ROOT


def write_spoken_report_output(
    job_id: str,
    summary_text: str,
    *,
    tableau_link: str = "",
    ok: bool = False,
    row_count: int = 0,
    error: Optional[str] = None,
) -> str:
    """
    Create ``spoken_report_outputs/<job_id>/`` and write:
    - ``summary.txt`` — text that would have been sent to the mouth daemon
    - ``report.json`` — small metadata for linking / debugging

    Returns absolute path to ``summary.txt``.
    """
    safe_id = job_id.replace("/", "_") if job_id else "unknown"
    out_dir = os.path.join(SPOKEN_REPORT_OUTPUT_ROOT, safe_id)
    os.makedirs(out_dir, exist_ok=True)

    summary_path = os.path.join(out_dir, "summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text or "")

    meta: dict[str, Any] = {
        "job_id": safe_id,
        "tableau_link": tableau_link,
        "ok": ok,
        "row_count": row_count,
    }
    if error:
        meta["error"] = error

    json_path = os.path.join(out_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return os.path.abspath(summary_path)
