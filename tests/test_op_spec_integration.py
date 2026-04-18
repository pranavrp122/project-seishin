"""Integration tests: 30+ NL requests mapped to op specs and executed.

Tests the full NL -> op_spec -> CacheExecutor pipeline without a live LLM.
Hand-crafted op specs represent what Gemma would return for each natural
language request, and the executor validates correct results.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from cache_executor import CacheExecutor, _fuzzy_match_column
from session_cache import SessionCache
from op_spec import OP_SPEC_SCHEMA
from intent_classifier import INTENT_SCHEMA


@pytest.fixture
def warehouse_report():
    """Simulates a cached report from 'show me warehouse data'."""
    return {
        "rows": [
            {"warehouse": "Portland", "region": "West", "capacity": 5000, "utilization": 0.82, "manager": "Alice Chen"},
            {"warehouse": "Seattle", "region": "West", "capacity": 8000, "utilization": 0.65, "manager": "Bob Park"},
            {"warehouse": "Chicago", "region": "Midwest", "capacity": 12000, "utilization": 0.91, "manager": "Carol White"},
            {"warehouse": "Detroit", "region": "Midwest", "capacity": 6000, "utilization": 0.45, "manager": "Dan Brown"},
            {"warehouse": "Atlanta", "region": "South", "capacity": 9500, "utilization": 0.78, "manager": "Eve Green"},
            {"warehouse": "Miami", "region": "South", "capacity": 7000, "utilization": 0.88, "manager": "Frank Lee"},
            {"warehouse": "Boston", "region": "East", "capacity": 11000, "utilization": 0.72, "manager": "Grace Kim"},
            {"warehouse": "New York", "region": "East", "capacity": 15000, "utilization": 0.95, "manager": "Hank Davis"},
            {"warehouse": "Denver", "region": "West", "capacity": 4500, "utilization": 0.33, "manager": "Iris Wong"},
            {"warehouse": "Dallas", "region": "South", "capacity": 10000, "utilization": 0.67, "manager": "Jack Smith"},
        ],
        "columns": {
            "warehouse": "string",
            "region": "string",
            "capacity": "number",
            "utilization": "number",
            "manager": "string",
        },
    }


@pytest.fixture
def sales_report():
    """Simulates a second cached report for cross-report compare."""
    return {
        "rows": [
            {"warehouse": "Portland", "monthly_sales": 150000},
            {"warehouse": "Seattle", "monthly_sales": 280000},
            {"warehouse": "Chicago", "monthly_sales": 420000},
            {"warehouse": "New York", "monthly_sales": 550000},
            {"warehouse": "Atlanta", "monthly_sales": 310000},
        ],
        "columns": {"warehouse": "string", "monthly_sales": "number"},
    }


@pytest.fixture
def executor():
    return CacheExecutor()


# --- 30 parameterized NL -> op_spec -> execution test cases ---

NL_TEST_CASES = [
    # --- FILTER tests (10) ---
    (
        "only show West warehouses",
        {"op_type": "filter", "column": "region", "operator": "eq", "value": "West", "explanation": "filter region West"},
        lambda r: r["row_count"] == 3,
    ),
    (
        "exclude the Midwest",
        {"op_type": "filter", "column": "region", "operator": "neq", "value": "Midwest", "explanation": "exclude Midwest"},
        lambda r: r["row_count"] == 8,
    ),
    (
        "warehouses with capacity over 8000",
        {"op_type": "filter", "column": "capacity", "operator": "gt", "value": 8000, "explanation": "capacity over 8000"},
        # Chicago(12000), Atlanta(9500), Boston(11000), NY(15000), Dallas(10000)
        lambda r: r["row_count"] == 5,
    ),
    (
        "those under 60% utilization",
        {"op_type": "filter", "column": "utilization", "operator": "lt", "value": 0.6, "explanation": "under 60%"},
        # Detroit(0.45), Denver(0.33)
        lambda r: r["row_count"] == 2,
    ),
    (
        "capacity between 5000 and 10000",
        {"op_type": "filter", "column": "capacity", "operator": "between", "value": 5000, "value2": 10000, "explanation": "cap 5k-10k"},
        # Portland(5000), Seattle(8000), Detroit(6000), Atlanta(9500), Miami(7000), Dallas(10000)
        lambda r: r["row_count"] == 6,
    ),
    (
        "just West and East regions",
        {"op_type": "filter", "column": "region", "operator": "in", "values": ["West", "East"], "explanation": "West and East"},
        # Portland, Seattle, Denver, Boston, NY
        lambda r: r["row_count"] == 5,
    ),
    (
        "find warehouses with 'port' in the name",
        {"op_type": "filter", "column": "warehouse", "operator": "contains", "value": "port", "explanation": "name contains port"},
        lambda r: r["row_count"] == 1,
    ),
    (
        "at least 90% utilized",
        {"op_type": "filter", "column": "utilization", "operator": "gte", "value": 0.9, "explanation": "90%+ utilized"},
        # Chicago(0.91), NY(0.95)
        lambda r: r["row_count"] == 2,
    ),
    (
        "capacity no more than 7000",
        {"op_type": "filter", "column": "capacity", "operator": "lte", "value": 7000, "explanation": "cap <= 7000"},
        # Portland(5000), Detroit(6000), Miami(7000), Denver(4500)
        lambda r: r["row_count"] == 4,
    ),
    (
        "warehouses managed by someone with 'e' in name",
        {"op_type": "filter", "column": "manager", "operator": "contains", "value": "e", "explanation": "manager name with e"},
        # Alice Chen, Carol White, Eve Green, Frank Lee, Grace Kim
        lambda r: r["row_count"] == 5,
    ),

    # --- SORT tests (3) ---
    (
        "sort by capacity descending",
        {"op_type": "sort", "column": "capacity", "direction": "desc", "explanation": "sort cap desc"},
        lambda r: r["rows"][0]["warehouse"] == "New York",
    ),
    (
        "order by utilization ascending",
        {"op_type": "sort", "column": "utilization", "direction": "asc", "explanation": "sort util asc"},
        lambda r: r["rows"][0]["warehouse"] == "Denver",
    ),
    (
        "sort by region then capacity descending",
        {"op_type": "sort", "sort_specs": [{"column": "region", "direction": "asc"}, {"column": "capacity", "direction": "desc"}], "explanation": "multi-sort"},
        lambda r: r["rows"][0]["region"] == "East",
    ),

    # --- TOP_N / BOTTOM_N tests (4) ---
    (
        "top 3 by capacity",
        {"op_type": "top_n", "column": "capacity", "n": 3, "explanation": "top 3 cap"},
        lambda r: r["row_count"] == 3 and r["rows"][0]["capacity"] == 15000,
    ),
    (
        "bottom 2 by utilization",
        {"op_type": "bottom_n", "column": "utilization", "n": 2, "explanation": "bottom 2 util"},
        lambda r: r["row_count"] == 2 and r["rows"][0]["utilization"] <= 0.45,
    ),
    (
        "give me the five biggest warehouses",
        {"op_type": "top_n", "column": "capacity", "n": 5, "explanation": "5 biggest"},
        lambda r: r["row_count"] == 5,
    ),
    (
        "which two have lowest capacity",
        {"op_type": "bottom_n", "column": "capacity", "n": 2, "explanation": "2 lowest cap"},
        lambda r: r["row_count"] == 2,
    ),

    # --- AGGREGATE tests (5) ---
    (
        "total capacity",
        {"op_type": "aggregate", "column": "capacity", "agg_func": "sum", "explanation": "total cap"},
        lambda r: r["rows"][0]["capacity"] == 88000,
    ),
    (
        "average utilization",
        {"op_type": "aggregate", "column": "utilization", "agg_func": "avg", "explanation": "avg util"},
        lambda r: abs(r["rows"][0]["utilization"] - 0.716) < 0.01,
    ),
    (
        "how many warehouses",
        {"op_type": "aggregate", "column": "capacity", "agg_func": "count", "explanation": "count"},
        lambda r: r["rows"][0]["capacity"] == 10,
    ),
    (
        "max capacity",
        {"op_type": "aggregate", "column": "capacity", "agg_func": "max", "explanation": "max cap"},
        lambda r: r["rows"][0]["capacity"] == 15000,
    ),
    (
        "total capacity by region",
        {"op_type": "aggregate", "column": "capacity", "agg_func": "sum", "group_by": ["region"], "explanation": "cap by region"},
        # West, East, Midwest, South
        lambda r: r["row_count"] == 4,
    ),

    # --- PIVOT test (1) ---
    (
        "pivot capacity by region",
        {"op_type": "pivot", "pivot_index": "region", "pivot_columns": "warehouse", "pivot_values": "capacity", "explanation": "pivot"},
        lambda r: r["row_count"] >= 1,
    ),

    # --- SELECT_COLUMNS tests (2) ---
    (
        "just show warehouse and capacity",
        {"op_type": "select_columns", "columns": ["warehouse", "capacity"], "explanation": "select 2 cols"},
        lambda r: len(r["rows"][0]) == 2,
    ),
    (
        "only the names and regions",
        {"op_type": "select_columns", "columns": ["warehouse", "region"], "explanation": "names+regions"},
        lambda r: "capacity" not in r["rows"][0],
    ),

    # --- RENAME_COLUMNS tests (2) ---
    (
        "rename capacity to max_units",
        {"op_type": "rename_columns", "rename_map": {"capacity": "max_units"}, "explanation": "rename cap"},
        lambda r: "max_units" in r["rows"][0],
    ),
    (
        "call utilization pct_full",
        {"op_type": "rename_columns", "rename_map": {"utilization": "pct_full"}, "explanation": "rename util"},
        lambda r: "pct_full" in r["rows"][0],
    ),

    # --- Additional tests to reach 30+ ---
    (
        "min utilization",
        {"op_type": "aggregate", "column": "utilization", "agg_func": "min", "explanation": "min util"},
        lambda r: abs(r["rows"][0]["utilization"] - 0.33) < 0.01,
    ),
    (
        "show only South warehouses",
        {"op_type": "filter", "column": "region", "operator": "eq", "value": "South", "explanation": "South only"},
        # Atlanta, Miami, Dallas
        lambda r: r["row_count"] == 3,
    ),
    (
        "warehouses with 'a' in the name",
        {"op_type": "filter", "column": "warehouse", "operator": "contains", "value": "a", "explanation": "name has a"},
        # Portland, Seattle, Chicago, Atlanta, Miami, Dallas, Dallas -- let me count:
        # Portland(a), Seattle(a), Chicago(a), Detroit(no), Atlanta(a), Miami(a), Boston(no), New York(no), Denver(no), Dallas(a) = 6
        lambda r: r["row_count"] == 6,
    ),
]


@pytest.mark.parametrize(
    "nl_request,op_spec,check",
    NL_TEST_CASES,
    ids=[c[0][:50] for c in NL_TEST_CASES],
)
def test_nl_to_execution(executor, warehouse_report, nl_request, op_spec, check):
    """Validate that the expected op spec produces correct results."""
    result = executor.execute(op_spec, warehouse_report)
    assert check(result), f"Failed for: {nl_request}\nResult: {result}"


# --- Non-parameterized integration tests ---


def test_cross_report_compare_integration(executor, warehouse_report, sales_report):
    """Cross-report merge on shared 'warehouse' column."""
    op_spec = {
        "op_type": "cross_report_compare",
        "compare_column": "warehouse",
        "explanation": "merge warehouse + sales",
    }
    result = executor.execute_cross_report(op_spec, warehouse_report, sales_report)
    # Inner join: Portland, Seattle, Chicago, New York, Atlanta = 5
    assert result["row_count"] == 5
    # Merged result has columns from both reports
    first_row = result["rows"][0]
    assert "monthly_sales" in first_row
    assert "capacity" in first_row or "capacity_report1" in first_row


def test_chained_operations(executor, warehouse_report):
    """Multi-step follow-up chain: filter -> sort -> top_n via cache round-trips."""
    cache = SessionCache()
    cache.store(warehouse_report, "show warehouse data", "SELECT * FROM warehouses")

    # Step 1: Filter to West
    report = cache.get_latest()
    step1 = executor.execute(
        {"op_type": "filter", "column": "region", "operator": "eq", "value": "West", "explanation": "West only"},
        report,
    )
    assert step1["row_count"] == 3
    cache.store(step1, "only West warehouses", "derived")

    # Step 2: Sort West warehouses by capacity desc
    report2 = cache.get_latest()
    step2 = executor.execute(
        {"op_type": "sort", "column": "capacity", "direction": "desc", "explanation": "sort cap desc"},
        report2,
    )
    assert step2["rows"][0]["capacity"] == 8000  # Seattle

    # Step 3: Top 2
    cache.store(step2, "West sorted by capacity", "derived")
    report3 = cache.get_latest()
    step3 = executor.execute(
        {"op_type": "top_n", "column": "capacity", "n": 2, "explanation": "top 2"},
        report3,
    )
    assert step3["row_count"] == 2
    assert step3["rows"][0]["capacity"] == 8000  # Seattle
    assert step3["rows"][1]["capacity"] == 5000  # Portland


def test_schema_validity():
    """Verify all test op specs conform to OP_SPEC_SCHEMA structure."""
    valid_op_types = set(OP_SPEC_SCHEMA["properties"]["op_type"]["enum"])
    schema_props = set(OP_SPEC_SCHEMA["properties"].keys())

    for nl, spec, _ in NL_TEST_CASES:
        # op_type must be in the schema enum
        assert spec["op_type"] in valid_op_types, (
            f"op_type '{spec['op_type']}' not in schema enum for: {nl}"
        )
        # All spec keys must be valid schema properties
        for key in spec:
            assert key in schema_props, (
                f"Key '{key}' not in schema properties for: {nl}"
            )
        # Required fields present
        assert "op_type" in spec
        assert "explanation" in spec


def test_all_op_types_covered():
    """Verify test cases collectively cover all 9 op types."""
    valid_op_types = set(OP_SPEC_SCHEMA["properties"]["op_type"]["enum"])
    tested_types = {spec["op_type"] for _, spec, _ in NL_TEST_CASES}

    # cross_report_compare tested separately (not parameterized)
    tested_types.add("cross_report_compare")

    missing = valid_op_types - tested_types
    assert not missing, f"Op types not tested: {missing}"
    assert tested_types == valid_op_types


# --- Phase 11.1 additions: fuzzy column NL cases ---


def test_fuzzy_column_filter_area(executor, warehouse_report):
    """NL request using 'area' which fuzzy-matches to 'region'."""
    result = executor.execute(
        {"op_type": "filter", "column": "area", "operator": "eq", "value": "West",
         "explanation": "filter area West"},
        warehouse_report,
    )
    assert result["row_count"] == 3


def test_fuzzy_column_top_n_cap(executor, warehouse_report):
    """NL request using 'cap' which is a substring of 'capacity'."""
    result = executor.execute(
        {"op_type": "top_n", "column": "cap", "n": 3,
         "explanation": "top 3 by cap"},
        warehouse_report,
    )
    assert result["row_count"] == 3


def test_intent_schema_has_all_intents():
    """Verify the extended INTENT_SCHEMA includes all 9 intents + op_chain."""
    intents = INTENT_SCHEMA["properties"]["intent"]["enum"]
    assert "undo" in intents
    assert "what_can_i_ask" in intents
    assert "compare_reports" in intents
    assert "new_data_request" in intents
    assert "follow_up_on_previous" in intents
    assert "confirm" in intents
    assert "cancel" in intents
    assert "list_cached_data" in intents
    assert "normal_chat" in intents
    assert len(intents) == 9
    assert "op_chain" in INTENT_SCHEMA["properties"]
