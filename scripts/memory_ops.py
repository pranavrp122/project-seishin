"""Pure-function in-memory ops over list[dict]. No pandas dependency."""


class OpSpecError(Exception):
    """Raised when an op_spec is missing required fields — caller should fall back to refetch."""


def execute_op(rows: list[dict], op_spec: dict) -> list[dict]:
    op_type = op_spec.get("op_type", "")
    dispatch = {
        "min": _op_min,
        "max": _op_max,
        "top_n": _op_top_n,
        "bottom_n": _op_bottom_n,
        "filter": _op_filter,
        "sort": _op_sort,
        "count": _op_count,
        "groupby": _op_groupby,
    }
    fn = dispatch.get(op_type)
    if fn is None:
        raise OpSpecError(f"Unknown op_type: {op_type!r}")
    try:
        return fn(rows, op_spec)
    except KeyError as exc:
        raise OpSpecError(f"op_spec missing required field {exc!s} for op_type={op_type!r}") from exc


def aggregate_multi(rows: list[dict], spec: dict) -> dict:
    if not rows:
        return {}
    result = {}
    for agg in spec["aggregations"]:
        op, col = agg["op"], agg["column"]
        _validate_column(rows, col)
        if op == "max":
            result[f"max_{col}"] = max(rows, key=lambda r: r[col])
        elif op == "min":
            result[f"min_{col}"] = min(rows, key=lambda r: r[col])
        else:
            raise ValueError(f"Unsupported aggregation op: {op!r}")
    return result


def _validate_column(rows: list[dict], col: str):
    if rows and col not in rows[0]:
        raise ValueError(f"Column {col!r} not found in rows. Available: {list(rows[0].keys())}")


def _op_min(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    return [min(rows, key=lambda r: r[col])]


def _op_max(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    return [max(rows, key=lambda r: r[col])]


def _op_top_n(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    n = spec.get("n", 5)
    return sorted(rows, key=lambda r: r[col], reverse=True)[:n]


def _op_bottom_n(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    n = spec.get("n", 5)
    return sorted(rows, key=lambda r: r[col])[:n]


def _op_filter(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    operator = spec.get("operator", "eq")
    value = spec["value"]
    ops = {
        "eq": lambda v: v == value,
        "neq": lambda v: v != value,
        "gt": lambda v: v > value,
        "gte": lambda v: v >= value,
        "lt": lambda v: v < value,
        "lte": lambda v: v <= value,
        "contains": lambda v: value in str(v),
        "in": lambda v: v in value,
    }
    fn = ops.get(operator)
    if fn is None:
        raise ValueError(f"Unknown filter operator: {operator!r}")
    return [r for r in rows if fn(r[col])]


def _op_sort(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    _validate_column(rows, col)
    desc = spec.get("direction", "asc") == "desc"
    return sorted(rows, key=lambda r: r[col], reverse=desc)


def _op_count(rows, spec):
    return [{"count": len(rows)}]


def _op_groupby(rows, spec):
    if not rows:
        return []
    col = spec["column"]
    agg_col = spec["agg_column"]
    agg_op = spec.get("agg_op", "count")
    _validate_column(rows, col)
    _validate_column(rows, agg_col)

    groups: dict[str, list] = {}
    for r in rows:
        key = r[col]
        groups.setdefault(key, []).append(r[agg_col])

    result = []
    for key, vals in groups.items():
        entry = {col: key}
        if agg_op == "max":
            entry[f"max_{agg_col}"] = max(vals)
        elif agg_op == "min":
            entry[f"min_{agg_col}"] = min(vals)
        elif agg_op == "count":
            entry[f"count_{agg_col}"] = len(vals)
        elif agg_op == "sum":
            entry[f"sum_{agg_col}"] = sum(vals)
        else:
            raise ValueError(f"Unknown groupby agg_op: {agg_op!r}")
        result.append(entry)
    return result
