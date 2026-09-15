"""Scenario / role testing: named sets of (securable, action) pairs.

Execution is BATCH: apply ALL grants -> probe EACH -> revoke ALL. A role has
dependencies (SELECT needs USE CATALOG + USE SCHEMA present simultaneously), so
per-action isolation would produce misleading failures. revoke-all ALWAYS runs
(finally) so a mid-run error never leaves the SP with orphaned grants.

Apply/probe/revoke are injected callables so the engine is unit-testable and,
in production, reuses the SAME guarded internals as single tests (apply_to_sp /
run_probe / revoke_from_sp). The engine never re-implements grant SQL and never
grants to a real principal.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable, ContextManager, Optional

import yaml

ConnFactory = Callable[[], ContextManager[Any]]
_SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_scenarios.yaml")


def run_scenario(
    items: list[dict],
    *,
    apply_fn: Callable[[str, str], Any],
    probe_fn: Callable[[str, str], dict],
    revoke_fn: Callable[[str, str], Any],
) -> dict:
    """apply ALL -> probe EACH -> revoke ALL (revoke always runs)."""
    results: list[dict] = []
    applied: list[dict] = []
    try:
        for it in items:
            apply_fn(it["action_id"], it["securable"])
            applied.append(it)
        for it in items:
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
