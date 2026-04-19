"""Whitelist pandas executor for cache op specs.

Maps each op_type to safe pandas operations. Data values from op specs
go into pandas method arguments -- never into eval, exec, or string templates.

Exports:
    CacheExecutor - dispatch to _op_* handlers for all 9 op types.
"""

import re

import pandas as pd

_AGG_MAP = {"sum": "sum", "avg": "mean", "count": "count", "min": "min", "max": "max"}

# --- Synonym dictionary for fuzzy column matching (D-02) ---
_COLUMN_SYNONYMS: dict[str, list[str]] = {
    "revenue": [r"revenue", r"total_dollars", r"amount", r"sales", r"income"],
    "sales": [r"sales", r"revenue", r"total_dollars", r"amount"],
    "date": [r"date", r"created_at", r"issued_at", r"due_at", r"timestamp", r"_at$"],
    "time": [r"date", r"created_at", r"issued_at", r"due_at", r"timestamp", r"_at$"],
    "when": [r"date", r"created_at", r"issued_at", r"due_at", r"timestamp", r"_at$"],
    "name": [r"name", r"client_name", r"customer_name", r"company"],
    "customer": [r"customer", r"client", r"account"],
    "client": [r"customer", r"client", r"account"],
    "quantity": [r"quantity", r"units", r"count", r"qty"],
    "price": [r"price", r"cost", r"rate", r"unit_price"],
    "cost": [r"price", r"cost", r"rate", r"unit_price"],
    "status": [r"status", r"state", r"active", r"enabled"],
    "region": [r"region", r"area", r"territory", r"zone"],
    "area": [r"region", r"area", r"territory", r"zone"],
    "id": [r"_id$", r"^id$"],
    "amount": [r"amount", r"total", r"dollars", r"revenue", r"total_dollars"],
}


def _fuzzy_match_column(name: str, columns: list[str]) -> str | None:
    """Match a business term to an actual column name via synonym dictionary.

    Returns the matched column name, or None if no match found.
    Silent -- no logging to voice output.
    """
    name_lower = name.lower().replace(" ", "_")

    # 1. Exact match (case-insensitive)
    for col in columns:
        if col.lower() == name_lower:
            return col

    # 2. Synonym dictionary lookup
    patterns = _COLUMN_SYNONYMS.get(name_lower, [])
    for pattern in patterns:
        for col in columns:
            if re.search(pattern, col.lower()):
                return col

    # 3. Substring containment fallback
    for col in columns:
        if name_lower in col.lower() or col.lower() in name_lower:
            return col

    return None


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

        # Alias fallback: try common ID column aliases
        _COLUMN_ALIASES = [
            ("id", "customer_id"),
            ("id", "client_id"),
            ("id", "order_id"),
        ]

        in_df1 = compare_column in df1.columns
        in_df2 = compare_column in df2.columns

        if not in_df1 or not in_df2:
            renamed_col = None
            for alias_a, alias_b in _COLUMN_ALIASES:
                if in_df1 and not in_df2:
                    if compare_column == alias_a and alias_b in df2.columns:
                        df2 = df2.rename(columns={alias_b: compare_column})
                        renamed_col = alias_b
                        break
                    elif compare_column == alias_b and alias_a in df2.columns:
                        df2 = df2.rename(columns={alias_a: compare_column})
                        renamed_col = alias_a
                        break
                elif in_df2 and not in_df1:
                    if compare_column == alias_a and alias_b in df1.columns:
                        df1 = df1.rename(columns={alias_b: compare_column})
                        renamed_col = alias_b
                        break
                    elif compare_column == alias_b and alias_a in df1.columns:
                        df1 = df1.rename(columns={alias_a: compare_column})
                        renamed_col = alias_a
                        break
            if renamed_col is None:
                if not in_df1:
                    raise ValueError(
                        f"Column '{compare_column}' not in primary report"
                    )
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
        col = spec.get("column")
        op = spec.get("operator")
        if not col or not op:
            raise ValueError(
                f"filter op missing required fields (column={col!r}, operator={op!r}). "
                f"Available columns: {list(df.columns)}"
            )
        if col not in df.columns:
            matched = _fuzzy_match_column(col, list(df.columns))
            if matched:
                col = matched
            else:
                raise ValueError(f"Column '{col}' not found. Available: {list(df.columns)}")
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
            for s in sort_specs:
                if s["column"] not in df.columns:
                    matched = _fuzzy_match_column(s["column"], list(df.columns))
                    if matched:
                        s["column"] = matched
            cols = [s["column"] for s in sort_specs]
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(f"Sort columns not found: {missing}")
            ascending = [s["direction"] == "asc" for s in sort_specs]
            return df.sort_values(by=cols, ascending=ascending)
        col = spec.get("column")
        if col is not None and col not in df.columns:
            matched = _fuzzy_match_column(col, list(df.columns))
            if matched:
                col = matched
        if col is None or col not in df.columns:
            raise ValueError(f"Sort column '{col}' not found in data")
        direction = spec.get("direction", "asc")
        return df.sort_values(by=col, ascending=(direction == "asc"))

    def _op_top_n(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec.get("column")
        n = spec.get("n", 5)
        # direction="asc" means the caller wants smallest (e.g. "shortest lead time")
        direction = spec.get("direction", "desc")
        if col:
            if col not in df.columns:
                matched = _fuzzy_match_column(col, list(df.columns))
                if matched:
                    col = matched
                else:
                    raise ValueError(f"Column '{col}' not found. Available: {list(df.columns)}")
            return df.nsmallest(n, col) if direction == "asc" else df.nlargest(n, col)
        return df.head(n)

    def _op_bottom_n(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec.get("column")
        n = spec.get("n", 5)
        # direction="desc" means the caller wants largest (e.g. "longest lead time" via bottom_n)
        direction = spec.get("direction", "asc")
        if col:
            if col not in df.columns:
                matched = _fuzzy_match_column(col, list(df.columns))
                if matched:
                    col = matched
                else:
                    raise ValueError(f"Column '{col}' not found. Available: {list(df.columns)}")
            return df.nlargest(n, col) if direction == "desc" else df.nsmallest(n, col)
        return df.tail(n)

    def _op_aggregate(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        col = spec["column"]
        if col not in df.columns:
            matched = _fuzzy_match_column(col, list(df.columns))
            if matched:
                col = matched
            else:
                raise ValueError(f"Column '{col}' not found. Available: {list(df.columns)}")
        func = spec["agg_func"]
        if func not in _AGG_MAP:
            raise ValueError(f"Unknown agg_func: {func!r}. Must be one of: {list(_AGG_MAP)}")
        pandas_func = _AGG_MAP[func]
        group_by = spec.get("group_by")

        if group_by:
            # Resolve each group_by column via fuzzy match
            resolved_group_by = []
            for gb_col in group_by:
                if gb_col not in df.columns:
                    gb_matched = _fuzzy_match_column(gb_col, list(df.columns))
                    if gb_matched:
                        resolved_group_by.append(gb_matched)
                    else:
                        raise ValueError(f"Group-by column '{gb_col}' not found. Available: {list(df.columns)}")
                else:
                    resolved_group_by.append(gb_col)
            group_by = resolved_group_by
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


def merge_compatible_reports(reports: list[dict]) -> dict | None:
    """Union all cached reports that share the same column schema.

    Takes a list of report dicts (each with 'rows', 'columns', 'query').
    Returns a merged report dict, or None if no compatible pair exists.
    Compatible = same set of column names.
    """
    if len(reports) < 2:
        return None

    # Group by frozenset of column names
    groups: dict[frozenset, list[dict]] = {}
    for r in reports:
        key = frozenset(r.get("columns", {}).keys())
        groups.setdefault(key, []).append(r)

    # Find the largest compatible group
    best = max(groups.values(), key=len)
    if len(best) < 2:
        return None

    import pandas as pd
    frames = [pd.DataFrame(r["rows"]) for r in best if r.get("rows")]
    merged = pd.concat(frames, ignore_index=True).drop_duplicates()

    queries = " + ".join(r.get("query", "") for r in best)
    return {
        "rows": merged.to_dict(orient="records"),
        "columns": best[0]["columns"],
        "row_count": len(merged),
        "query": f"merged: {queries}",
        "sql": "",
    }
