"""Unit tests for text_utils._normalize_datetime."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from datetime import datetime
from unittest.mock import patch
from text_utils import _normalize_datetime


# Freeze datetime.now() to Saturday April 18, 2026 for deterministic tests
_FROZEN = datetime(2026, 4, 18, 10, 0, 0)


@pytest.fixture(autouse=True)
def freeze_time():
    with patch("text_utils.datetime") as mock_dt:
        mock_dt.now.return_value = _FROZEN
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        yield mock_dt


class TestNormalizeDatetime:
    def test_yesterday(self):
        result = _normalize_datetime("show me yesterday data")
        assert "April 17, 2026" in result
        assert "yesterday" not in result.lower()

    def test_today(self):
        result = _normalize_datetime("what happened today")
        assert "April 18, 2026" in result
        assert "today" not in result.lower()

    def test_tomorrow(self):
        result = _normalize_datetime("schedule for tomorrow")
        assert "April 19, 2026" in result
        assert "tomorrow" not in result.lower()

    def test_last_week(self):
        result = _normalize_datetime("orders from last week")
        # Last week Mon-Sun: April 6-12
        assert "Apr 06" in result
        assert "Apr 12" in result
        assert "last week" not in result.lower()

    def test_this_week(self):
        result = _normalize_datetime("this week's data")
        # This week Mon-Sun: April 13-19
        assert "Apr 13" in result
        assert "Apr 19" in result
        assert "this week" not in result.lower()

    def test_last_month(self):
        result = _normalize_datetime("last month revenue")
        assert "March 2026" in result
        assert "last month" not in result.lower()

    def test_this_month(self):
        result = _normalize_datetime("this month so far")
        assert "April 2026" in result
        assert "this month" not in result.lower()

    def test_last_quarter(self):
        result = _normalize_datetime("last quarter results")
        assert "Q1 2026" in result
        assert "Jan-Mar" in result
        assert "last quarter" not in result.lower()

    def test_this_quarter(self):
        result = _normalize_datetime("this quarter performance")
        assert "Q2 2026" in result
        assert "Apr-Jun" in result
        assert "this quarter" not in result.lower()

    def test_this_year(self):
        result = _normalize_datetime("this year totals")
        assert "2026 so far" in result
        assert "this year" not in result.lower()

    def test_ytd(self):
        result = _normalize_datetime("YTD numbers")
        assert "2026 so far" in result

    def test_last_year(self):
        result = _normalize_datetime("compare to last year")
        assert "2025" in result
        assert "last year" not in result.lower()

    def test_no_dates(self):
        text = "show me all clients"
        result = _normalize_datetime(text)
        assert result == text

    def test_multiple_dates(self):
        result = _normalize_datetime("compare last month to this month")
        assert "March 2026" in result
        assert "April 2026" in result
        assert "last month" not in result.lower()
        assert "this month" not in result.lower()

    def test_case_insensitive(self):
        result = _normalize_datetime("LAST MONTH revenue")
        assert "March 2026" in result
