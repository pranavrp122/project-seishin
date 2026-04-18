"""Text preprocessing utilities for natural language input.

Exports:
    _normalize_datetime() - Replace relative date references with concrete dates.
"""

import re
import calendar
from datetime import datetime, timedelta

# --- Compiled regex patterns for date normalization (module-level for performance) ---
_RE_YESTERDAY = re.compile(r"\byesterday\b", re.IGNORECASE)
_RE_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
_RE_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_RE_LAST_WEEK = re.compile(r"\blast week\b", re.IGNORECASE)
_RE_THIS_WEEK = re.compile(r"\bthis week\b", re.IGNORECASE)
_RE_LAST_MONTH = re.compile(r"\blast month\b", re.IGNORECASE)
_RE_THIS_MONTH = re.compile(r"\bthis month\b", re.IGNORECASE)
_RE_LAST_QUARTER = re.compile(r"\blast quarter\b", re.IGNORECASE)
_RE_THIS_QUARTER = re.compile(r"\bthis quarter\b", re.IGNORECASE)
_RE_THIS_YEAR = re.compile(r"\b(?:this year|YTD|year to date)\b", re.IGNORECASE)
_RE_LAST_YEAR = re.compile(r"\blast year\b", re.IGNORECASE)


def _week_range(now: datetime, offset: int) -> str:
    """Return 'Mon DD-Mon DD, YYYY' for the given week offset (Monday-Sunday)."""
    monday = now - timedelta(days=now.weekday())
    target_monday = monday + timedelta(weeks=offset)
    target_sunday = target_monday + timedelta(days=6)
    return f"{target_monday.strftime('%b %d')}-{target_sunday.strftime('%b %d, %Y')}"


def _month_name(now: datetime, offset: int) -> str:
    """Return 'MonthName YYYY' for the given month offset."""
    month = now.month + offset
    year = now.year
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{calendar.month_name[month]} {year}"


def _quarter_range(now: datetime, offset: int) -> str:
    """Return 'Q# YYYY (Mon-Mon)' for the given quarter offset."""
    current_q = (now.month - 1) // 3 + 1
    target_q = current_q + offset
    target_year = now.year

    while target_q < 1:
        target_q += 4
        target_year -= 1
    while target_q > 4:
        target_q -= 4
        target_year += 1

    month_ranges = {1: "Jan-Mar", 2: "Apr-Jun", 3: "Jul-Sep", 4: "Oct-Dec"}
    return f"Q{target_q} {target_year} ({month_ranges[target_q]})"


def _normalize_datetime(text: str) -> str:
    """Replace relative date references with concrete dates.

    Runs before classify_intent on every utterance. Pure regex, <5ms.
    """
    now = datetime.now()

    text = _RE_YESTERDAY.sub((now - timedelta(days=1)).strftime("%B %d, %Y"), text)
    text = _RE_TODAY.sub(now.strftime("%B %d, %Y"), text)
    text = _RE_TOMORROW.sub((now + timedelta(days=1)).strftime("%B %d, %Y"), text)
    text = _RE_LAST_WEEK.sub(_week_range(now, -1), text)
    text = _RE_THIS_WEEK.sub(_week_range(now, 0), text)
    text = _RE_LAST_MONTH.sub(_month_name(now, -1), text)
    text = _RE_THIS_MONTH.sub(_month_name(now, 0), text)
    text = _RE_LAST_QUARTER.sub(_quarter_range(now, -1), text)
    text = _RE_THIS_QUARTER.sub(_quarter_range(now, 0), text)
    text = _RE_THIS_YEAR.sub(f"{now.year} so far", text)
    text = _RE_LAST_YEAR.sub(str(now.year - 1), text)

    return text
