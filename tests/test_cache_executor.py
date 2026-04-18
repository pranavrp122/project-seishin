"""Scarce-case unit tests for CacheExecutor — all 9 op types plus edge cases."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from cache_executor import CacheExecutor, _fuzzy_match_column


@pytest.fixture
def sample_report():
    return {
        "rows": [
            {"name": "Alpha", "region": "West", "revenue": 1000, "units": 50, "active": True},
            {"name": "Beta", "region": "East", "revenue": 2500, "units": 120, "active": True},
            {"name": "Gamma", "region": "West", "revenue": 800, "units": 30, "active": False},
            {"name": "Delta", "region": "East", "revenue": 3200, "units": 200, "active": True},
            {"name": "Epsilon", "region": "North", "revenue": 1500, "units": 75, "active": False},
            {"name": "Zeta", "region": "West", "revenue": 4000, "units": 300, "active": True},
            {"name": "Eta", "region": "East", "revenue": 600, "units": 15, "active": False},
            {"name": "Theta", "region": "North", "revenue": 2200, "units": 95, "active": True},
        ],
        "columns": {
            "name": "string",
            "region": "string",
            "revenue": "number",
            "units": "number",
            "active": "boolean",
        },
    }


@pytest.fixture
def executor():
    return CacheExecutor()


# --- FILTER tests ---


class TestFilterOps:
    def test_filter_eq(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "region", "operator": "eq", "value": "West"},
            sample_report,
        )
        assert result["row_count"] == 3

    def test_filter_neq(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "region", "operator": "neq", "value": "East"},
            sample_report,
        )
        assert result["row_count"] == 5

    def test_filter_gt(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "revenue", "operator": "gt", "value": 2000},
            sample_report,
        )
        # Beta(2500), Delta(3200), Zeta(4000), Theta(2200)
        assert result["row_count"] == 4

    def test_filter_lt(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "units", "operator": "lt", "value": 50},
            sample_report,
        )
        assert result["row_count"] == 2

    def test_filter_gte(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "revenue", "operator": "gte", "value": 2500},
            sample_report,
        )
        # Beta(2500), Delta(3200), Zeta(4000)
        assert result["row_count"] == 3

    def test_filter_lte(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "units", "operator": "lte", "value": 75},
            sample_report,
        )
        # Alpha(50), Gamma(30), Epsilon(75), Eta(15)
        assert result["row_count"] == 4

    def test_filter_between(self, executor, sample_report):
        result = executor.execute(
            {
                "op_type": "filter",
                "column": "revenue",
                "operator": "between",
                "value": 1000,
                "value2": 2500,
            },
            sample_report,
        )
        # Alpha(1000), Beta(2500), Epsilon(1500), Theta(2200)
        assert result["row_count"] == 4

    def test_filter_in(self, executor, sample_report):
        result = executor.execute(
            {
                "op_type": "filter",
                "column": "region",
                "operator": "in",
                "values": ["West", "North"],
            },
            sample_report,
        )
        assert result["row_count"] == 5

    def test_filter_contains(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "name", "operator": "contains", "value": "a"},
            sample_report,
        )
        # Alpha, Beta, Gamma, Delta, Zeta, Eta, Theta all contain 'a' case-insensitive
        assert result["row_count"] == 7

    def test_filter_type_coercion_string_to_number(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "revenue", "operator": "gt", "value": "2000"},
            sample_report,
        )
        # Same as gt 2000: Beta(2500), Delta(3200), Zeta(4000), Theta(2200)
        assert result["row_count"] == 4

    def test_filter_empty_result(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "filter", "column": "revenue", "operator": "gt", "value": 99999},
            sample_report,
        )
        assert result["row_count"] == 0
        assert result["rows"] == []


# --- SORT tests ---


class TestSortOps:
    def test_sort_single_asc(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "sort", "column": "revenue", "direction": "asc"},
            sample_report,
        )
        assert result["rows"][0]["name"] == "Eta"
        assert result["rows"][0]["revenue"] == 600

    def test_sort_single_desc(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "sort", "column": "revenue", "direction": "desc"},
            sample_report,
        )
        assert result["rows"][0]["name"] == "Zeta"
        assert result["rows"][0]["revenue"] == 4000

    def test_sort_multi_column(self, executor, sample_report):
        result = executor.execute(
            {
                "op_type": "sort",
                "sort_specs": [
                    {"column": "region", "direction": "asc"},
                    {"column": "revenue", "direction": "desc"},
                ],
            },
            sample_report,
        )
        # East first (alphabetical), then by revenue desc within East
        assert result["rows"][0]["region"] == "East"
        assert result["rows"][0]["revenue"] == 3200  # Delta


# --- TOP_N / BOTTOM_N tests ---


class TestTopBottomN:
    def test_top_n(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "top_n", "column": "revenue", "n": 3},
            sample_report,
        )
        assert result["row_count"] == 3
        assert result["rows"][0]["revenue"] == 4000  # Zeta
        assert result["rows"][1]["revenue"] == 3200  # Delta
        assert result["rows"][2]["revenue"] == 2500  # Beta

    def test_bottom_n(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "bottom_n", "column": "units", "n": 2},
            sample_report,
        )
        assert result["row_count"] == 2
        assert result["rows"][0]["units"] == 15  # Eta
        assert result["rows"][1]["units"] == 30  # Gamma

    def test_top_n_default(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "top_n", "column": "revenue"},
            sample_report,
        )
        assert result["row_count"] == 5  # default n=5


# --- AGGREGATE tests ---


class TestAggregateOps:
    def test_aggregate_sum(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "aggregate", "column": "revenue", "agg_func": "sum"},
            sample_report,
        )
        assert result["rows"][0]["revenue"] == 15800

    def test_aggregate_avg(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "aggregate", "column": "units", "agg_func": "avg"},
            sample_report,
        )
        expected_avg = (50 + 120 + 30 + 200 + 75 + 300 + 15 + 95) / 8
        assert abs(result["rows"][0]["units"] - expected_avg) < 0.01

    def test_aggregate_count(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "aggregate", "column": "revenue", "agg_func": "count"},
            sample_report,
        )
        assert result["rows"][0]["revenue"] == 8

    def test_aggregate_min_max(self, executor, sample_report):
        min_result = executor.execute(
            {"op_type": "aggregate", "column": "revenue", "agg_func": "min"},
            sample_report,
        )
        max_result = executor.execute(
            {"op_type": "aggregate", "column": "revenue", "agg_func": "max"},
            sample_report,
        )
        assert min_result["rows"][0]["revenue"] == 600
        assert max_result["rows"][0]["revenue"] == 4000

    def test_aggregate_with_group_by(self, executor, sample_report):
        result = executor.execute(
            {
                "op_type": "aggregate",
                "column": "revenue",
                "agg_func": "sum",
                "group_by": ["region"],
            },
            sample_report,
        )
        assert result["row_count"] == 3  # West, East, North


# --- PIVOT test ---


class TestPivotOps:
    def test_pivot(self, executor, sample_report):
        result = executor.execute(
            {
                "op_type": "pivot",
                "pivot_index": "region",
                "pivot_columns": "active",
                "pivot_values": "revenue",
            },
            sample_report,
        )
        assert result["row_count"] >= 1


# --- SELECT / RENAME tests ---


class TestSelectRename:
    def test_select_columns(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "select_columns", "columns": ["name", "revenue"]},
            sample_report,
        )
        assert len(result["rows"][0]) == 2
        assert "name" in result["rows"][0]
        assert "revenue" in result["rows"][0]

    def test_rename_columns(self, executor, sample_report):
        result = executor.execute(
            {"op_type": "rename_columns", "rename_map": {"revenue": "total_revenue"}},
            sample_report,
        )
        assert "total_revenue" in result["rows"][0]
        assert "revenue" not in result["rows"][0]


# --- CROSS REPORT tests ---


class TestCrossReport:
    def test_cross_report_compare(self, executor, sample_report):
        secondary = {
            "rows": [
                {"name": "Alpha", "score": 90},
                {"name": "Beta", "score": 85},
                {"name": "Delta", "score": 95},
            ],
            "columns": {"name": "string", "score": "number"},
        }
        result = executor.execute_cross_report(
            {"op_type": "cross_report_compare", "compare_column": "name"},
            sample_report,
            secondary,
        )
        assert result["row_count"] == 3  # inner join on shared names
        # Merged result has columns from both
        assert "revenue" in result["rows"][0] or "revenue_report1" in result["rows"][0]
        assert "score" in result["rows"][0] or "score_report2" in result["rows"][0]

    def test_cross_report_missing_column(self, executor, sample_report):
        secondary = {
            "rows": [{"foo": 1}],
            "columns": {"foo": "number"},
        }
        with pytest.raises(ValueError, match="not in secondary report"):
            executor.execute_cross_report(
                {"op_type": "cross_report_compare", "compare_column": "name"},
                sample_report,
                secondary,
            )


# --- EDGE CASES ---


class TestEdgeCases:
    def test_unknown_op_type(self, executor, sample_report):
        with pytest.raises(ValueError, match="Unknown op_type"):
            executor.execute({"op_type": "delete_all"}, sample_report)

    def test_unknown_filter_operator(self, executor, sample_report):
        with pytest.raises(ValueError, match="Unknown filter operator"):
            executor.execute(
                {"op_type": "filter", "column": "revenue", "operator": "regex", "value": ".*"},
                sample_report,
            )

    def test_single_row_report(self, executor):
        single = {
            "rows": [{"name": "Solo", "value": 100}],
            "columns": {"name": "string", "value": "number"},
        }
        # Filter
        result = executor.execute(
            {"op_type": "filter", "column": "name", "operator": "eq", "value": "Solo"},
            single,
        )
        assert result["row_count"] == 1
        # Sort
        result = executor.execute(
            {"op_type": "sort", "column": "value", "direction": "asc"},
            single,
        )
        assert result["row_count"] == 1
        # Top N
        result = executor.execute(
            {"op_type": "top_n", "column": "value", "n": 5},
            single,
        )
        assert result["row_count"] == 1

    def test_conflicting_ops_sort_specs_priority(self, executor, sample_report):
        """When sort_specs and column+direction both provided, sort_specs wins."""
        result = executor.execute(
            {
                "op_type": "sort",
                "column": "units",
                "direction": "asc",
                "sort_specs": [{"column": "revenue", "direction": "desc"}],
            },
            sample_report,
        )
        # sort_specs should win: sorted by revenue desc
        assert result["rows"][0]["revenue"] == 4000

    def test_cross_report_via_execute_raises(self, executor, sample_report):
        """cross_report_compare via execute() raises ValueError directing to execute_cross_report."""
        with pytest.raises(ValueError, match="execute_cross_report"):
            executor.execute(
                {"op_type": "cross_report_compare", "compare_column": "name"},
                sample_report,
            )


# --- FUZZY COLUMN MATCHING tests ---


class TestFuzzyColumnMatching:
    """Tests for _fuzzy_match_column synonym dictionary and fallback logic."""

    def test_fuzzy_exact_match(self):
        assert _fuzzy_match_column("revenue", ["revenue", "name"]) == "revenue"

    def test_fuzzy_exact_case_insensitive(self):
        assert _fuzzy_match_column("Revenue", ["revenue", "name"]) == "revenue"

    def test_fuzzy_synonym_hit(self):
        assert _fuzzy_match_column("revenue", ["total_dollars", "name"]) == "total_dollars"

    def test_fuzzy_synonym_sales(self):
        assert _fuzzy_match_column("sales", ["total_dollars", "name"]) == "total_dollars"

    def test_fuzzy_date_synonym(self):
        assert _fuzzy_match_column("date", ["created_at", "name"]) == "created_at"

    def test_fuzzy_customer_synonym(self):
        assert _fuzzy_match_column("customer", ["client_name", "id"]) == "client_name"

    def test_fuzzy_substring_fallback(self):
        assert _fuzzy_match_column("capacity", ["max_capacity", "name"]) == "max_capacity"

    def test_fuzzy_no_match(self):
        assert _fuzzy_match_column("nonexistent", ["a", "b", "c"]) is None

    def test_fuzzy_spaces_to_underscores(self):
        assert _fuzzy_match_column("client name", ["client_name", "id"]) == "client_name"

    def test_filter_with_fuzzy_column(self, executor, sample_report):
        """Filter using synonym column name 'area' resolves to 'region'."""
        result = executor.execute(
            {"op_type": "filter", "column": "area", "operator": "eq", "value": "West"},
            sample_report,
        )
        assert result["row_count"] == 3

    def test_sort_with_fuzzy_column(self, executor, sample_report):
        """Sort using synonym column name 'area' resolves to 'region'."""
        result = executor.execute(
            {"op_type": "sort", "column": "area", "direction": "asc"},
            sample_report,
        )
        assert result["rows"][0]["region"] == "East"

    def test_top_n_with_fuzzy_column(self, executor, sample_report):
        """Top N using synonym column name 'amount' resolves to 'revenue'."""
        result = executor.execute(
            {"op_type": "top_n", "column": "amount", "n": 3},
            sample_report,
        )
        assert result["row_count"] == 3
        assert result["rows"][0]["revenue"] == 4000
