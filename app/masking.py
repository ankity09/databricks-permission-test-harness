"""UC governance-metadata reader for the masking-aware results grid (Feature 1).

Detects which columns of a table carry a column mask and whether the table has
an active row filter, so the query-runner grid can annotate them. This is what
turns "I think that's masked" into "confirmed: `ssn` is masked by policy".

Read under the OBO identity (the admin can read information_schema). This must
NEVER raise into the grid: any error degrades to empty (no annotations), and
the UI simply shows the plain grid.

Sources (per-catalog Unity Catalog views):
  * <catalog>.information_schema.column_masks  -> masked column names
  * <catalog>.information_schema.row_filters   -> row-filtered tables
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List


def _parts(table: str) -> List[str]:
    return [p for p in table.split(".") if p]


def _cell(row: Any, dict_keys: tuple, list_index: int) -> Any:
    """Pull a value from a row that may be a dict or a positional list."""
    if isinstance(row, dict):
        for k in dict_keys:
            if k in row and row[k] is not None:
                return row[k]
        return None
    if isinstance(row, (list, tuple)) and len(row) > list_index:
        return row[list_index]
    return None


def describe_governance(obo_exec: Callable[[str], Any], table: str) -> Dict[str, Any]:
    """Return ``{masked_columns, row_filter, detail}`` for ``table``.

    ``obo_exec(sql)`` runs a statement under the OBO identity and returns an
    iterable of rows (dicts or positional lists). Never raises.
    """
    empty = {"masked_columns": [], "row_filter": False, "detail": ""}
    parts = _parts(table)
    if len(parts) != 3:
        return {**empty, "detail": "mask annotations shown for 3-part table names only"}
    catalog, schema, name = parts

    masked: List[str] = []
    try:
        rows = obo_exec(
            f"SELECT column_name FROM {catalog}.information_schema.column_masks "
            f"WHERE table_schema = '{schema}' AND table_name = '{name}'"
        ) or []
        for r in rows:
            col = _cell(r, ("column_name", "COLUMN_NAME"), 0)
            if col:
                masked.append(str(col))
    except Exception:  # noqa: BLE001 -- annotations are best-effort
        return {**empty, "detail": "governance metadata unavailable"}

    row_filter = False
    try:
        rows = obo_exec(
            f"SELECT table_name FROM {catalog}.information_schema.row_filters "
            f"WHERE table_schema = '{schema}' AND table_name = '{name}'"
        ) or []
        row_filter = any(_cell(r, ("table_name", "TABLE_NAME"), 0) for r in rows)
    except Exception:  # noqa: BLE001
        pass

    detail = ""
    if masked:
        detail = f"{len(masked)} masked column(s)"
    if row_filter:
        detail = (detail + "; row filter active").lstrip("; ")
    return {"masked_columns": masked, "row_filter": row_filter, "detail": detail}
