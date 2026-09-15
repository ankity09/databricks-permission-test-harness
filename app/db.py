"""Lakebase (Autoscaling Postgres) connection pool + OAuth credential lifecycle.

The app connects to Lakebase AS ITS SERVICE PRINCIPAL. The Postgres password is
a short-lived (~60-min) OAuth token minted via the SDK; we cache it and refresh
before expiry. Pool init is fault-tolerant: a Lakebase outage must never crash
the app (pages still render, the error is surfaced via healthcheck).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.config import get_settings


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
    except Exception as exc:  # noqa: BLE001 — never crash the app
        state.pool = None
        state.error = str(exc)


_STATE = PoolState()


def get_state() -> "PoolState":
    return _STATE


def get_pool():
    if _STATE.pool is None:
        init_pool(_STATE)
    return _STATE.pool


def healthcheck(state: "PoolState | None" = None) -> dict:
    st = state if state is not None else _STATE
    if st.pool is None:
        return {"ok": False, "error": st.error or "pool not initialized"}
    return {"ok": True}
