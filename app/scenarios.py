"""Scenario / role testing: named sets of (securable, action) pairs.

Execution is BATCH: apply ALL grants -> probe EACH -> revoke ALL. A role has
dependencies (SELECT needs USE CATALOG + USE SCHEMA present simultaneously), so
per-action isolation would produce misleading failures. revoke-all ALWAYS runs
(finally) so a mid-run error never leaves the SP with orphaned grants.

Apply/probe/revoke are injected callables so the engine is unit-testable and,
in production, reuses the SAME guarded internals as single tests (apply_to_sp /
run_probe / revoke_from_sp). The engine never re-implements grant SQL and never
grants to a real principal.

Pre-flight validation ensures all items are valid before any apply/revoke
operations execute. Errors are reported with row index and securable detail.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable, ContextManager, Optional

import yaml

from app.securable import parse_securable, SecurableParseError

ConnFactory = Callable[[], ContextManager[Any]]
_SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_scenarios.yaml")


class ValidationError(ValueError):
    """Raised when scenario validation fails; carries row index and detail."""

    def __init__(self, message: str, row: int, action_id: str, securable: str):
        self.message = message
        self.row = row
        self.action_id = action_id
        self.securable = securable
        super().__init__(message)


def validate_scenario_items(
    items: list[dict], catalog: dict
) -> None:
    """Pre-validate all items before any execution. Raises ValidationError on first bad row.

    Checks: action_id is known and non-empty, securable parses and is not a
    placeholder template (e.g. {catalog}), and securable is at the correct level
    for the action.
    """
    for idx, it in enumerate(items):
        action_id = it.get("action_id", "").strip() if isinstance(it.get("action_id"), str) else ""
        securable = it.get("securable", "").strip() if isinstance(it.get("securable"), str) else ""

        if not action_id:
            raise ValidationError(
                "action_id is missing or empty",
                row=idx,
                action_id=action_id or "",
                securable=securable,
            )

        if not securable:
            raise ValidationError(
                "securable is missing or empty",
                row=idx,
                action_id=action_id,
                securable="",
            )

        # Check for unfilled placeholders like {catalog}, {sp}, etc.
        if "{" in securable and "}" in securable:
            raise ValidationError(
                f"securable contains unfilled placeholder(s): {securable!r}",
                row=idx,
                action_id=action_id,
                securable=securable,
            )

        # Check if action_id is known.
        if action_id not in catalog:
            raise ValidationError(
                f"action_id not found in catalog: {action_id!r}",
                row=idx,
                action_id=action_id,
                securable=securable,
            )

        descriptor = catalog[action_id]

        # Try to parse the securable; must be valid according to the parser.
        try:
            parse_securable(securable)
        except SecurableParseError as exc:
            raise ValidationError(
                f"securable parse error: {exc}",
                row=idx,
                action_id=action_id,
                securable=securable,
            ) from exc

        # Validate that securable is at the correct level for the action.
        from app.catalog import validate_securable, SecurableLevelError

        try:
            validate_securable(descriptor, securable)
        except SecurableLevelError as exc:
            raise ValidationError(
                str(exc),
                row=idx,
                action_id=action_id,
                securable=securable,
            ) from exc


def run_scenario(
    items: list[dict],
    *,
    apply_fn: Callable[[str, str], Any],
    probe_fn: Callable[[str, str], dict],
    revoke_fn: Callable[[str, str], Any],
    catalog: Optional[dict] = None,
) -> dict:
    """apply ALL -> probe EACH -> revoke ALL (revoke always runs).

    ``apply_fn`` returns False when the SP already held the grant: that row is
    probed but never revoked, so a run can't remove grants that existed before it.

    If catalog is provided, validates all items before execution. Raises
    ValidationError if any item fails pre-flight checks (prior to any apply).
    """
    if catalog is not None:
        validate_scenario_items(items, catalog)

    results: list[dict] = []
    applied: list[dict] = []
    held: set[int] = set()  # rows whose grant existed before the run: never revoked
    try:
        for i, it in enumerate(items):
            if apply_fn(it["action_id"], it["securable"]) is False:
                held.add(i)
            else:
                applied.append(it)
        for i, it in enumerate(items):
            try:
                outcome = probe_fn(it["action_id"], it["securable"])
                status = outcome.get("status", "error")
                detail = outcome.get("detail", "")
            except Exception as exc:  # noqa: BLE001
                status, detail = "error", str(exc)
            results.append({
                "action_id": it["action_id"],
                "securable": it["securable"],
                "status": status,
                "detail": detail,
                "already_held": i in held,
            })
    finally:
        for it in applied:
            try:
                revoke_fn(it["action_id"], it["securable"])
            except Exception:  # noqa: BLE001
                pass
    overall = "pass" if results and all(r["status"] == "pass" for r in results) else "fail"
    return {"overall": overall, "results": results}


def load_seed_scenarios() -> list[dict]:
    with open(_SEED_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("scenarios", [])


def list_scenarios(*, conn_factory: ConnFactory, schema: str) -> list[dict]:
    sql = (
        "SELECT id, name, description, created_by, created_at, items, is_seed "
        f"FROM {schema}.scenarios ORDER BY is_seed DESC, name"
    )
    with conn_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [_normalize_row(r) for r in rows]


def save_scenario(
    *,
    conn_factory: ConnFactory,
    schema: str,
    name: str,
    description: str,
    created_by: str,
    items: list[dict],
    scenario_id: Optional[str] = None,
) -> str:
    sid = scenario_id or str(uuid.uuid4())
    sql = (
        f"INSERT INTO {schema}.scenarios (id, name, description, created_by, items, is_seed) "
        "VALUES (%s, %s, %s, %s, %s, false) "
        "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, "
        "description=EXCLUDED.description, items=EXCLUDED.items"
    )
    with conn_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (sid, name, description, created_by, json.dumps(items)))
        conn.commit()
    return sid


def get_scenario(*, conn_factory: ConnFactory, schema: str, scenario_id: str) -> Optional[dict]:
    sql = (
        "SELECT id, name, description, created_by, created_at, items, is_seed "
        f"FROM {schema}.scenarios WHERE id = %s"
    )
    with conn_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (scenario_id,))
            row = cur.fetchone()
    return _normalize_row(row) if row else None


def _normalize_row(row: Any) -> dict:
    d = dict(row) if not isinstance(row, dict) else row
    items = d.get("items")
    if isinstance(items, str):
        d["items"] = json.loads(items)
    return d
