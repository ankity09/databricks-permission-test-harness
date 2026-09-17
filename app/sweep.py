"""Adversarial read-only reach sweep (Feature 2).

Answers "can the SP READ things it shouldn't?" by:
  1. Enumerating the adjacent set under the OBO identity (which can list):
     same-schema sibling tables + one-level-up containers (catalog, schema).
  2. Having the app SP attempt a harmless read (SELECT / USE / SHOW) against
     each, and classifying the outcome.

Verdict language:
  * DENIED               -> "hold"    (boundary holds; green)
  * unexpected SUCCESS   -> "hole"    (SP can read something ungranted; red)
  * neither clean allow
    nor clean deny        -> "error"  (neutral; raw message surfaced)

HARD SCOPE: this is fully side-effect-free. Only SELECT/USE/SHOW are attempted.
No destructive verb (MODIFY/DELETE/DROP/GRANT) is attempted OR inspected. A
green sweep means "no READ over-reach on the checked adjacent set" -- NOT "the
principal is harmless". The API/UI must surface that caveat.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.probe import map_result

# Substring markers reused from probe-style classification.
_DENIED = ("PERMISSION_DENIED", "does not have", "is not authorized", "access denied")


def _split(securable: str) -> List[str]:
    return [p for p in securable.split(".") if p]


def build_targets(obo_exec: Callable[[str], Any], securable: str) -> List[Dict[str, str]]:
    """Enumerate the adjacent read-only target set for ``securable``.

    ``obo_exec(sql)`` runs a statement under the OBO identity and returns an
    iterable of row dicts (used for SHOW TABLES). Enumeration failures degrade
    to just the container targets (partial, honestly labeled by the caller).
    """
    parts = _split(securable)
    targets: List[Dict[str, str]] = []
    if len(parts) < 2:
        return targets
    catalog, schema = parts[0], parts[1]
    target_table = parts[2] if len(parts) >= 3 else None

    # one-level-up containers
    targets.append({"object": catalog, "action": "use_catalog"})
    targets.append({"object": f"{catalog}.{schema}", "action": "use_schema"})

    # same-schema sibling tables (best-effort listing)
    try:
        rows = obo_exec(f"SHOW TABLES IN {catalog}.{schema}") or []
    except Exception:  # noqa: BLE001 -- partial enumeration is acceptable
        rows = []
    for row in rows:
        name = None
        if isinstance(row, dict):
            name = row.get("tableName") or row.get("table_name") or row.get("name")
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            name = row[1]
        if not name or name == target_table:
            continue
        targets.append({"object": f"{catalog}.{schema}.{name}", "action": "select"})

    return targets


_STATEMENT = {
    "use_catalog": "USE CATALOG {obj}",
    "use_schema": "USE SCHEMA {obj}",
    "select": "SELECT * FROM {obj} LIMIT 1",
}


def _attempt(sp_client: Any, warehouse_id: str, obj: str, action: str) -> Dict[str, str]:
    stmt = _STATEMENT[action].format(obj=obj)
    try:
        resp = sp_client.statement_execution.execute_statement(
            statement=stmt, warehouse_id=warehouse_id, wait_timeout="30s"
        )
        status = getattr(resp, "status", None)
        state = getattr(status, "state", None)
        state_str = getattr(state, "value", str(state)) if state is not None else ""
        if state_str and state_str.upper() != "SUCCEEDED":
            err = getattr(status, "error", None)
            raw = getattr(err, "message", str(err)) if err else f"state={state_str}"
            outcome = map_result(exc_type=state_str, raw=raw, negative=False)
        else:
            outcome = map_result(exc_type=None, raw=None, negative=False, rows=[{"ok": 1}])
    except Exception as exc:  # noqa: BLE001
        outcome = map_result(exc_type=type(exc).__name__, raw=str(exc), negative=False)

    if outcome.status == "pass":
        return {"result": "hole", "detail": "SP could read this (unexpected).", "raw": ""}
    if outcome.status == "fail_denied":
        return {"result": "hold", "detail": "SP correctly denied.", "raw": outcome.raw_error}
    return {"result": "error", "detail": outcome.detail, "raw": outcome.raw_error}


def run_sweep(
    targets: List[Dict[str, str]],
    *,
    sp_client: Any,
    warehouse_id: str,
) -> Dict[str, Any]:
    """Attempt each read-only target as the SP; assemble the security matrix."""
    matrix: List[Dict[str, str]] = []
    holes = 0
    for t in targets:
        res = _attempt(sp_client, warehouse_id, t["object"], t["action"])
        row = {"object": t["object"], "action": t["action"], **res}
        if res["result"] == "hole":
            holes += 1
        matrix.append(row)

    status = "holes_found" if holes else "boundaries_hold"
    return {
        "matrix": matrix,
        "verdict": {"status": status, "holes": holes, "checked": len(matrix)},
        "scope_note": (
            "Read over-reach only. This sweep does NOT test write, escalation, "
            "or destructive boundaries. A green result means the SP cannot READ "
            "the adjacent objects checked, not that the principal is harmless."
        ),
    }
