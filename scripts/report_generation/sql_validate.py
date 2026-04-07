"""Validate LLM-produced SQL before sending to the thin SQLite client."""
import re
from typing import Optional, Tuple

from .config import ALLOWED_SQL_TABLES, MAX_SQL_ROWS


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|attach|pragma|vacuum|replace|create|alter|truncate|grant|revoke|detach)\b",
    re.IGNORECASE | re.DOTALL,
)

# Rough extraction of base table names after FROM / JOIN (MVP; subqueries may confuse this).
_FROM_JOIN_TABLE = re.compile(
    r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)\b",
    re.IGNORECASE,
)


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _referenced_tables(sql: str) -> set[str]:
    return {m.group(1).lower() for m in _FROM_JOIN_TABLE.finditer(sql)}


def ensure_limit(sql: str, max_rows: int) -> str:
    s = sql.strip().rstrip(";")
    if not re.search(r"\blimit\s+\d+\s*$", s, re.IGNORECASE):
        return f"{s} LIMIT {max_rows}"
    return s


def validate_sql(sql: str, max_rows: int = MAX_SQL_ROWS) -> Tuple[bool, str, Optional[str]]:
    """
    Returns (ok, message, normalized_sql_or_none).
    Only a single SELECT against allow-listed tables; injects LIMIT if missing.
    """
    raw = sql.strip()
    if not raw:
        return False, "Empty SQL.", None

    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if len(parts) != 1:
        return False, "Multiple SQL statements are not allowed.", None

    single = parts[0]
    if not re.match(r"^\s*select\b", single, re.IGNORECASE):
        return False, "Only SELECT queries are allowed.", None

    if _FORBIDDEN.search(single):
        return False, "Forbidden keyword in SQL.", None

    tables = _referenced_tables(single)
    if not tables:
        return False, "Could not parse table references (FROM/JOIN).", None

    bad = tables - ALLOWED_SQL_TABLES
    if bad:
        return False, f"Disallowed table(s): {', '.join(sorted(bad))}.", None

    limited = ensure_limit(single, max_rows)
    return True, "ok", limited
