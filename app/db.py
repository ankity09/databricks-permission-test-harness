"""Lakebase (Autoscaling Postgres) connection pool + OAuth credential lifecycle.

The app connects to Lakebase AS ITS SERVICE PRINCIPAL. The Postgres password is
a short-lived (~60-min) OAuth token minted via the SDK; we cache it and refresh
before expiry. Pool init is fault-tolerant: a Lakebase outage must never crash
the app (pages still render, the error is surfaced via healthcheck).

On first start, ensure_schema() idempotently creates the schema and required
tables (activity_log, scenarios). This allows the app to self-provision without
manual SQL setup, with graceful error handling for permission/existence issues.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class CredentialProvider:
    """Mints and caches the OAuth token used as the Postgres password."""

    def __init__(self, mint: Callable[[], str], ttl_seconds: int = 3000):
        self._mint = mint
        self._ttl = ttl_seconds
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            now = time.time()
            if self._token is None or now >= self._expires_at:
                self._token = self._mint()
                self._expires_at = now + self._ttl
            return self._token


def mint_databricks_token() -> str:
    """Mint a Lakebase DB credential for the app SP (Autoscaling tier)."""
    from databricks.sdk import WorkspaceClient

    s = get_settings()
    w = WorkspaceClient()  # app SP creds from env
    cred = w.postgres.generate_database_credential(endpoint=s.lakebase_endpoint)
    return cred.token


@dataclass
class PoolState:
    pool: Optional[object] = None
    error: Optional[str] = None
    provider: Optional[CredentialProvider] = None


def _default_pool_factory(conninfo: str):
    from psycopg_pool import ConnectionPool

    return ConnectionPool(conninfo=conninfo, min_size=1, max_size=4, open=True)


def init_pool(state: "PoolState", pool_factory: Callable[..., object] | None = None) -> None:
    """Initialize the pool; NEVER raise (graceful lifespan)."""
    factory = pool_factory or _default_pool_factory
    try:
        s = get_settings()
        state.provider = CredentialProvider(mint=mint_databricks_token)
        password = state.provider.token()
        conninfo = (
            f"host={s.pg_host} port={s.pg_port} dbname={s.pg_database} "
            f"user={s.pg_user} password={password} sslmode=require"
        )
        state.pool = factory(conninfo)
        state.error = None
    except Exception as exc:  # noqa: BLE001 -- never crash the app
        state.pool = None
        state.error = str(exc)


_STATE = PoolState()


def get_state() -> "PoolState":
    return _STATE


def close_pool(state: "PoolState | None" = None, timeout: float = 5.0) -> None:
    """Close the pool on shutdown so the app stops promptly. Never raises."""
    st = state if state is not None else _STATE
    pool, st.pool = st.pool, None
    if pool is not None:
        try:
            pool.close(timeout=timeout)
        except Exception:  # noqa: BLE001
            pass


def get_pool():
    if _STATE.pool is None:
        init_pool(_STATE)
    return _STATE.pool


def healthcheck(state: "PoolState | None" = None) -> dict:
    st = state if state is not None else _STATE
    if st.pool is None:
        return {"ok": False, "error": st.error or "pool not initialized"}
    return {"ok": True}


def _quote_identifier(s: str) -> str:
    """Double-quote a Postgres identifier (Postgres does not accept backticks)."""
    return '"' + s.replace('"', '""') + '"'


def ensure_schema(conn: Any, schema: str) -> None:
    """Create the schema, activity_log, and scenarios tables when they are missing.

    Matches sql/schema.sql. Does nothing when both tables already exist, because
    they may belong to another role and CREATE ... IF NOT EXISTS still checks
    privileges. Logs and returns on any error so a Lakebase problem never blocks
    boot.
    """
    schema_quoted = _quote_identifier(schema)
    try:
        with conn.cursor() as cur:
            regclass = schema_quoted.replace("'", "''")
            cur.execute(
                f"SELECT to_regclass('{regclass}.activity_log') IS NOT NULL "
                f"AND to_regclass('{regclass}.scenarios') IS NOT NULL"
            )
            row = cur.fetchone()
            if row and row[0]:
                return

            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_quoted}")

            # Create activity_log table if it doesn't exist.
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {schema_quoted}.activity_log (
                    id           TEXT PRIMARY KEY,
                    session_id   TEXT,
                    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
                    admin_email  TEXT,
                    sp_id        TEXT,
                    event_type   TEXT NOT NULL,
                    action_id    TEXT,
                    securable    TEXT,
                    verdict      TEXT,
                    raw_message  TEXT,
                    scenario_id  TEXT
                )
                """
            )

            # Create activity_log index if it doesn't exist.
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS activity_log_ts_idx "
                f"ON {schema_quoted}.activity_log (ts DESC)"
            )

            # Create scenarios table if it doesn't exist.
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {schema_quoted}.scenarios (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    description TEXT,
                    created_by  TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    items       JSONB NOT NULL,
                    is_seed     BOOLEAN NOT NULL DEFAULT false
                )
                """
            )

        conn.commit()
    except Exception as exc:  # noqa: BLE001
        # Log but don't raise; the app boots gracefully even if setup fails.
        logger.warning(f"ensure_schema({schema}) failed: {exc}")
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
