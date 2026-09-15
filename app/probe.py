"""Attempt executor + result-state mapping.

The probe is how the app SP ATTEMPTS the action being tested. The Databricks
error text IS the product here: it is captured and surfaced verbatim, never
swallowed or reformatted.

Two probe kinds:
  * ``sql``               — SP runs a side-effect-free statement on a warehouse.
  * ``permission-check``  — read the SP's effective permission level via the
                            Permissions API and compare to the required level.

Write-guarded actions run their real (side-effecting) form only when
``really_do`` is set; otherwise they run the safe/plan-only probe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from app.catalog import resolve
from app.models import ActionDescriptor

# Substrings that identify a grant-authority failure (the admin/OBO identity
# couldn't ISSUE the grant) vs. a probe denial (the SP couldn't DO the action).
_GRANT_AUTHORITY_MARKERS = (
    "GRANT_AUTHORITY",
    "does not have permission to grant",
    "requires ownership",
    "only the owner",
)
_PERMISSION_DENIED_MARKERS = (
    "PERMISSION_DENIED",
    "does not have",
    "is not authorized",
    "requires.*privilege",
    "access denied",
)


@dataclass
class ProbeOutcome:
    status: str  # "pass" | "fail_denied" | "grant_failed" | "error"
    detail: str = ""
    raw_error: str = ""
    rows: Optional[List[dict]] = None


def _looks_like(markers, text: str) -> bool:
    t = (text or "").lower()
    return any(m.lower().split(".*")[0] in t for m in markers)


def map_result(
    *,
    exc_type: Optional[str],
    raw: Optional[str],
    negative: bool,
    rows: Optional[List[dict]] = None,
    allowed: Optional[bool] = None,
) -> ProbeOutcome:
    """Map a raw attempt outcome into a UI result state.

    State machine (spec section 5):
      * no exception + rows/allowed  -> pass
      * grant-authority failure      -> grant_failed (distinct from denial)
      * permission denied            -> fail_denied (or pass when negative test)
      * anything else                -> error
    """
    # Success: rows came back, or a permission-check said allowed.
    if exc_type is None and (rows is not None or allowed):
        if negative:
            # Expected a denial but the action SUCCEEDED -> the negative test failed.
            return ProbeOutcome(
                status="fail_denied",
                detail="Negative test expected a denial, but the action succeeded.",
                rows=rows,
            )
        return ProbeOutcome(status="pass", detail="Action succeeded.", rows=rows)

    text = f"{exc_type or ''} {raw or ''}"

    # Grant-authority failure is a DISTINCT state — the grant never took effect,
    # so this is not a statement about the SP's ability to perform the action.
    if _looks_like(_GRANT_AUTHORITY_MARKERS, text):
        return ProbeOutcome(
            status="grant_failed",
            detail="Your account couldn't issue this grant (insufficient authority).",
            raw_error=raw or "",
        )

    # Permission denied for the SP performing the action.
    if _looks_like(_PERMISSION_DENIED_MARKERS, text):
        if negative:
            return ProbeOutcome(
                status="pass",
                detail="Confirmed: the SP is correctly denied (negative test).",
                raw_error=raw or "",
            )
        return ProbeOutcome(status="fail_denied", detail="SP was denied.", raw_error=raw or "")

    # permission-check explicitly returned not-allowed (no exception).
    if exc_type is None and allowed is False:
        if negative:
            return ProbeOutcome(
                status="pass",
                detail="Confirmed: the SP lacks the required level (negative test).",
            )
        return ProbeOutcome(
            status="fail_denied",
            detail="SP does not hold the required permission level.",
        )

    return ProbeOutcome(status="error", detail="Unexpected probe outcome.", raw_error=raw or "")


def _classify_exception(exc: Exception) -> str:
    """Best-effort classifier for a Databricks SDK exception -> marker string."""
    name = type(exc).__name__
    return f"{name}: {exc}"


def run_probe(
    descriptor: ActionDescriptor,
    *,
    securable: str,
    sp_client: Any,
    warehouse_id: str,
    really_do: bool = False,
    negative: bool = False,
) -> ProbeOutcome:
    """Attempt the action as the app SP and return a mapped outcome."""
    kind = descriptor.probe.get("kind")

    if kind == "sql":
        return _run_sql_probe(
            descriptor,
            securable=securable,
            sp_client=sp_client,
            warehouse_id=warehouse_id,
            negative=negative,
        )
    if kind == "permission-check":
        return _run_permission_check(
            descriptor,
            securable=securable,
            sp_client=sp_client,
            negative=negative,
        )
    return ProbeOutcome(status="error", detail=f"Unknown probe kind: {kind!r}")


def _run_sql_probe(descriptor, *, securable, sp_client, warehouse_id, negative) -> ProbeOutcome:
    statement = resolve(descriptor.probe["statement"], securable=securable)
    try:
        resp = sp_client.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=warehouse_id,
            wait_timeout="30s",
        )
        state = getattr(getattr(resp, "status", None), "state", None)
        state_str = getattr(state, "value", str(state)) if state is not None else ""
        if state_str and state_str.upper() not in ("SUCCEEDED",):
            err = getattr(getattr(resp, "status", None), "error", None)
            raw = getattr(err, "message", str(err)) if err else f"statement state={state_str}"
            return map_result(exc_type=state_str, raw=raw, negative=negative)

        result = getattr(resp, "result", None)
        data = getattr(result, "data_array", None) if result else None
        rows = [{"col": row} for row in data] if data is not None else []
        return map_result(exc_type=None, raw=None, negative=negative, rows=rows)
    except Exception as exc:  # noqa: BLE001 — the error IS the product
        return map_result(exc_type=type(exc).__name__, raw=str(exc), negative=negative)


def _run_permission_check(descriptor, *, securable, sp_client, negative) -> ProbeOutcome:
    api = descriptor.probe["api"]
    required = descriptor.probe["level"]
    sp_app_id = _sp_application_id(sp_client)
    try:
        levels = _effective_levels(sp_client, api, securable, sp_app_id)
        allowed = required in levels
        detail = f"SP effective levels on {api}/{securable}: {sorted(levels) or 'none'}"
        outcome = map_result(exc_type=None, raw=detail, negative=negative, allowed=allowed)
        if not outcome.detail:
            outcome.detail = detail
        return outcome
    except Exception as exc:  # noqa: BLE001
        return map_result(exc_type=type(exc).__name__, raw=str(exc), negative=negative)


def _sp_application_id(sp_client) -> Optional[str]:
    try:
        return sp_client.current_user.me().user_name
    except Exception:  # noqa: BLE001
        return None


def _effective_levels(sp_client, api: str, object_id: str, sp_app_id: Optional[str]) -> set:
    """Return the set of permission levels the app SP effectively holds."""
    perms = sp_client.permissions.get(request_object_type=api, request_object_id=object_id)
    levels: set = set()
    for acl in getattr(perms, "access_control_list", None) or []:
        who = getattr(acl, "service_principal_name", None) or getattr(acl, "user_name", None)
        if sp_app_id and who and who != sp_app_id:
            continue
        for perm in getattr(acl, "all_permissions", None) or []:
            lvl = getattr(perm, "permission_level", None)
            if lvl is not None:
                levels.add(getattr(lvl, "value", str(lvl)))
    return levels
