"""Whitelist pandas executor for cache op specs.

Maps each op_type to safe pandas operations. Data values from op specs
go into pandas method arguments -- never into eval, exec, or string templates.

Exports:
    CacheExecutor - dispatch to _op_* handlers for all 9 op types.
"""

import pandas as pd

_AGG_MAP = {"sum": "sum", "avg": "mean", "count": "count", "min": "min", "max": "max"}


def _infer_dtype(series: pd.Series) -> str:
    """Return a simplified dtype string for a pandas Series."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    return "string"


def _coerce_filter_value(val, series: pd.Series):
    """Coerce a filter value to match the target column's dtype."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        coerced = pd.to_numeric(val, errors="coerce")
        if pd.isna(coerced):
            return val
        return coerced
    return str(val) if val is not None else val


class CacheExecutor:
    """Execute op specs against cached report data using pandas."""

    def execute(self, op_spec: dict, report_data: dict) -> dict:
        """Execute op spec against cached data. Returns {rows, columns, row_count}."""
        df = pd.DataFrame(report_data["rows"])
        op_type = op_spec["op_type"]

        if op_type == "cross_report_compare":
            raise ValueError(
                "cross_report_compare requires execute_cross_report()"
            )

        handler = getattr(self, f"_op_{op_type}", None)
        if handler is None:
            raise ValueError(f"Unknown op_type: {op_type}")

        result_df = handler(df, op_spec)
        return self._to_result(result_df)

    def execute_cross_report(
        self, op_spec: dict, primary: dict, secondary: dict
    ) -> dict:
        """Handle cross_report_compare: merge two reports on a shared column."""
        df1 = pd.DataFrame(primary["rows"])
        df2 = pd.DataFrame(secondary["rows"])
        compare_column = op_spec["compare_column"]

        if compare_column not in df1.columns:
            raise ValueError(
                f"Column '{compare_column}' not in primary report"
            )
        if compare_column not in df2.columns:
            raise ValueError(
                f"Column '{compare_column}' not in secondary report"
            )

        merged = df1.merge(
            df2,
            on=compare_column,
            how="inner",
            suffixes=("_report1", "_report2"),
        )
        return self._to_result(merged)

    # --- Op handlers ---

    def _op_filter(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec["column"]
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found. Available: {list(df.columns)}")
        op = spec["operator"]
        val = spec.get("value")

        # Type coercion for filter values
        if val is not None:
            val = _coerce_filter_value(val, df[col])

        if op == "eq":
            return df[df[col] == val]
        elif op == "neq":
            return df[df[col] != val]
        elif op == "gt":
            return df[df[col] > val]
        elif op == "lt":
            return df[df[col] < val]
        elif op == "gte":
            return df[df[col] >= val]
        elif op == "lte":
            return df[df[col] <= val]
        elif op == "between":
            val2 = spec["value2"]
            if val2 is not None:
                val2 = _coerce_filter_value(val2, df[col])
            return df[df[col].between(val, val2)]
        elif op == "in":
            values = spec["values"]
            coerced = [_coerce_filter_value(v, df[col]) for v in values]
            return df[df[col].isin(coerced)]
        elif op == "contains":
            return df[
                df[col].astype(str).str.contains(str(val), case=False, na=False)
            ]
        raise ValueError(f"Unknown filter operator: {op}")

    def _op_sort(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        sort_specs = spec.get("sort_specs")
        if sort_specs:
            cols = [s["column"] for s in sort_specs]
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(f"Sort columns not found: {missing}")
            ascending = [s["direction"] == "asc" for s in sort_specs]
            return df.sort_values(by=cols, ascending=ascending)
        col = spec.get("column")
        if col is None or col not in df.columns:
            raise ValueError(f"Sort column '{col}' not found in data")
        direction = spec.get("direction", "asc")
        return df.sort_values(by=col, ascending=(direction == "asc"))

    def _op_top_n(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec.get("column")
        n = spec.get("n", 5)
        if col:
            return df.nlargest(n, col)
        return df.head(n)

    def _op_bottom_n(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec.get("column")
        n = spec.get("n", 5)
        if col:
            return df.nsmallest(n, col)
        return df.tail(n)

    def _op_aggregate(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec["column"]
        func = spec["agg_func"]
        if func not in _AGG_MAP:
            raise ValueError(f"Unknown agg_func: {func!r}. Must be one of: {list(_AGG_MAP)}")
        pandas_func = _AGG_MAP[func]
        group_by = spec.get("group_by")

        if group_by:
            grouped = df.groupby(group_by)
            return getattr(grouped[col], pandas_func)().reset_index()

        # Scalar aggregate -- single-row DataFrame
        val = getattr(df[col], pandas_func)()
        return pd.DataFrame([{col: val, "aggregation": func}])

    def _op_pivot(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        return pd.pivot_table(
            df,
            index=spec["pivot_index"],
            columns=spec["pivot_columns"],
            values=spec["pivot_values"],
            aggfunc="sum",
        ).reset_index()

    def _op_select_columns(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        return df[spec["columns"]]

    def _op_rename_columns(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        return df.rename(columns=spec["rename_map"])

    # --- Helpers ---

    @staticmethod
    def _to_result(result_df: pd.DataFrame) -> dict:
        """Convert a DataFrame to the standard result dict."""
        return {
            "rows": result_df.to_dict(orient="records"),
            "columns": {col: _infer_dtype(result_df[col]) for col in result_df.columns},
            "row_count": len(result_df),
        }
