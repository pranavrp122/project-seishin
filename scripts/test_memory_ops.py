import pytest
from scripts.memory_ops import execute_op, aggregate_multi

ROWS = [
    {"name": "Alpha", "lead_time": 10, "rating": 3, "state": "CA"},
    {"name": "Beta", "lead_time": 25, "rating": 5, "state": "TX"},
    {"name": "Gamma", "lead_time": 5, "rating": 3, "state": "CA"},
    {"name": "Delta", "lead_time": 18, "rating": 1, "state": "TX"},
    {"name": "Epsilon", "lead_time": 30, "rating": 4, "state": "NY"},
]


class TestMin:
    def test_min(self):
        result = execute_op(ROWS, {"op_type": "min", "column": "lead_time"})
        assert len(result) == 1
        assert result[0]["lead_time"] == 5

    def test_min_string_col(self):
        result = execute_op(ROWS, {"op_type": "min", "column": "name"})
        assert result[0]["name"] == "Alpha"


class TestMax:
    def test_max(self):
        result = execute_op(ROWS, {"op_type": "max", "column": "lead_time"})
        assert len(result) == 1
        assert result[0]["lead_time"] == 30


class TestTopN:
    def test_top_3(self):
        result = execute_op(ROWS, {"op_type": "top_n", "column": "lead_time", "n": 3})
        assert len(result) == 3
        assert result[0]["lead_time"] == 30
        assert result[2]["lead_time"] == 18

    def test_top_n_exceeds_rows(self):
        result = execute_op(ROWS, {"op_type": "top_n", "column": "lead_time", "n": 100})
        assert len(result) == len(ROWS)


class TestBottomN:
    def test_bottom_3(self):
        result = execute_op(ROWS, {"op_type": "bottom_n", "column": "lead_time", "n": 3})
        assert len(result) == 3
        assert result[0]["lead_time"] == 5
        assert result[2]["lead_time"] == 18


class TestFilter:
    def test_eq(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "rating", "operator": "eq", "value": 3})
        assert len(result) == 2

    def test_neq(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "rating", "operator": "neq", "value": 3})
        assert len(result) == 3

    def test_gt(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "lead_time", "operator": "gt", "value": 18})
        assert len(result) == 2

    def test_gte(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "lead_time", "operator": "gte", "value": 18})
        assert len(result) == 3

    def test_lt(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "lead_time", "operator": "lt", "value": 10})
        assert len(result) == 1

    def test_lte(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "lead_time", "operator": "lte", "value": 10})
        assert len(result) == 2

    def test_contains(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "name", "operator": "contains", "value": "lph"})
        assert len(result) == 1

    def test_in(self):
        result = execute_op(ROWS, {"op_type": "filter", "column": "state", "operator": "in", "value": ["CA", "NY"]})
        assert len(result) == 3


class TestSort:
    def test_sort_desc(self):
        result = execute_op(ROWS, {"op_type": "sort", "column": "rating", "direction": "desc"})
        assert len(result) == len(ROWS)
        assert result[0]["rating"] == 5

    def test_sort_asc(self):
        result = execute_op(ROWS, {"op_type": "sort", "column": "rating", "direction": "asc"})
        assert result[0]["rating"] == 1


class TestCount:
    def test_count(self):
        result = execute_op(ROWS, {"op_type": "count"})
        assert result == [{"count": 5}]


class TestGroupby:
    def test_groupby_max(self):
        result = execute_op(ROWS, {"op_type": "groupby", "column": "state", "agg_column": "rating", "agg_op": "max"})
        by_state = {r["state"]: r for r in result}
        assert by_state["CA"]["max_rating"] == 3
        assert by_state["TX"]["max_rating"] == 5
        assert by_state["NY"]["max_rating"] == 4

    def test_groupby_min(self):
        result = execute_op(ROWS, {"op_type": "groupby", "column": "state", "agg_column": "rating", "agg_op": "min"})
        by_state = {r["state"]: r for r in result}
        assert by_state["TX"]["min_rating"] == 1

    def test_groupby_count(self):
        result = execute_op(ROWS, {"op_type": "groupby", "column": "state", "agg_column": "rating", "agg_op": "count"})
        by_state = {r["state"]: r for r in result}
        assert by_state["CA"]["count_rating"] == 2


class TestAggregateMulti:
    def test_conjunctive(self):
        result = aggregate_multi(ROWS, {"aggregations": [
            {"op": "max", "column": "lead_time"},
            {"op": "min", "column": "lead_time"},
        ]})
        assert result["max_lead_time"]["lead_time"] == 30
        assert result["min_lead_time"]["lead_time"] == 5


class TestEdgeCases:
    def test_empty_rows(self):
        assert execute_op([], {"op_type": "min", "column": "x"}) == []
        assert execute_op([], {"op_type": "count"}) == [{"count": 0}]

    def test_missing_column(self):
        with pytest.raises(ValueError):
            execute_op(ROWS, {"op_type": "min", "column": "nonexistent"})

    def test_unknown_op(self):
        with pytest.raises(ValueError):
            execute_op(ROWS, {"op_type": "bogus", "column": "x"})
