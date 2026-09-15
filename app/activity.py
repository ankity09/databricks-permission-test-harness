"""Durable activity log (Lakebase). SP-written telemetry; reads served to UI/agent.

log_event() is called server-side after each harness operation. It is NOT a
permission grant -- the SP writing its own audit table does not touch the grant
trust model. Writes never require OBO (telemetry decoupled from user auth).
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, ContextManager, Optional

# conn_factory() -> context manager yielding a DBAPI connection.
ConnFactory = Callable[[], ContextManager[Any]]

_EVENT_TYPES = {"apply", "probe", "revoke", "promote_viewed"}


def log_event(
    *,
    conn_factory: ConnFactory,
    schema: str,
    session_id: str,
    admin_email: str,
    sp_id: str,
    event_type: str,
    action_id: str,
    securable: str,
    verdict: Optional[str],
    raw_message: str = "",
    scenario_id: Optional[str] = None,
) -> str:
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type}")
    row_id = str(uuid.uuid4())
    sql = (
        f"INSERT INTO {schema}.activity_log "
        "(id, session_id, ts, admin_email, sp_id, event_type, action_id, "
        " securable, verdict, raw_message, scenario_id) "
        "VALUES (%s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    params = (
        row_id,
        session_id,
        admin_email,
        sp_id,
        event_type,
        action_id,
        securable,
        verdict,
        raw_message,
        scenario_id,
    )
    with conn_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    return row_id


def read_events(
    *,
    conn_factory: ConnFactory,
    schema: str,
    admin_email: Optional[str] = None,
    verdict: Optional[str] = None,
    securable: Optional[str] = None,
    scenario_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    for col, val in (
        ("admin_email", admin_email),
        ("verdict", verdict),
        ("securable", securable),
        ("scenario_id", scenario_id),
    ):
        if val is not None:
            clauses.append(f"{col} = %s")
            params.append(val)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT id, session_id, ts, admin_email, sp_id, event_type, action_id, "
        "securable, verdict, raw_message, scenario_id "
        f"FROM {schema}.activity_log {where} ORDER BY ts DESC LIMIT %s"
    )
    params.append(limit)
    row_factory = _dict_row()
    with conn_factory() as conn:
        cur = conn.cursor(row_factory=row_factory) if row_factory else conn.cursor()
        with cur as c:
            c.execute(sql, tuple(params))
            return list(c.fetchall())


def _dict_row():
    """Return psycopg's dict_row factory if available, else None (tests inject a
    cursor that already yields dicts and ignores the kwarg)."""
    try:
        from psycopg.rows import dict_row

        return dict_row
    except Exception:  # noqa: BLE001
        return None
