"""Run a read-only query AS THE APP SP and return the actual rows.

Feature 1 ("see what the user sees"): the tester runs a SELECT as the SP and
sees the returned data, so column masks and row filters are directly
observable. The Databricks error text IS the product; a denial is captured as
``error`` in the result and never raised into the request path.

Read-only enforcement for user-supplied SQL lives in ``app.sql_guard`` and is
applied at the API layer BEFORE calling this module. The guided path builds its
own ``SELECT`` via ``build_select`` and never accepts user SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_select(table: str, limit: int) -> str:
    """Build a safe ``SELECT * FROM <table> LIMIT <n>`` for the guided path.

    ``table`` must be a fully-qualified 3-part name (catalog.schema.table).
    """
    parts = [p for p in table.split(".") if p]
    if len(parts) != 3:
        raise ValueError(
            f"Expected a 3-part table name (catalog.schema.table), got {table!r}."
        )
    return f"SELECT * FROM {table} LIMIT {int(limit)}"


def _column_names(resp: Any) -> List[str]:
    manifest = getattr(resp, "manifest", None)
    schema = getattr(manifest, "schema", None)
    cols = getattr(schema, "columns", None) or []
    return [getattr(c, "name", "") for c in cols]


def run_query_as_sp(
    sql: str,
    *,
    sp_client: Any,
    warehouse_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Execute ``sql`` as the app SP; return columns/rows/truncated/error.

    Never raises: a denial or failure is captured in ``error`` with empty
    columns/rows so the caller can surface the real Databricks message.
    """
    try:
        resp = sp_client.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=warehouse_id,
            wait_timeout="30s",
        )
    except Exception as exc:  # noqa: BLE001 -- the error IS the product
        return {"columns": [], "rows": [], "truncated": False, "error": str(exc)}

    status = getattr(resp, "status", None)
    state = getattr(status, "state", None)
    state_str = getattr(state, "value", str(state)) if state is not None else ""
    if state_str and state_str.upper() != "SUCCEEDED":
        err = getattr(status, "error", None)
        msg = getattr(err, "message", str(err)) if err else f"state={state_str}"
        return {"columns": [], "rows": [], "truncated": False, "error": msg}

    columns = _column_names(resp)
    result = getattr(resp, "result", None)
    data = getattr(result, "data_array", None) if result else None
    rows: List[list] = list(data) if data is not None else []

    truncated = False
    if limit is not None and len(rows) > limit:
        rows = rows[:limit]
        truncated = True

    return {"columns": columns, "rows": rows, "truncated": truncated, "error": None}
