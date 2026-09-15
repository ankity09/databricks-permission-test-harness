import time

import app.db as db


def test_credential_provider_caches_and_refreshes():
    calls = {"n": 0}

    def fake_mint():
        calls["n"] += 1
        return f"token-{calls['n']}"

    prov = db.CredentialProvider(mint=fake_mint, ttl_seconds=1)
    assert prov.token() == "token-1"
    assert prov.token() == "token-1"  # cached within ttl
    assert calls["n"] == 1
    prov._expires_at = time.time() - 1  # force expiry
    assert prov.token() == "token-2"  # refreshed
    assert calls["n"] == 2


def test_init_pool_failure_is_swallowed(monkeypatch):
    # A failing pool factory must not raise out of init_pool (graceful lifespan).
    monkeypatch.setattr(db, "mint_databricks_token", lambda: "tok")

    def boom(*a, **k):
        raise RuntimeError("no postgres")

    state = db.PoolState()
    db.init_pool(state, pool_factory=boom)
    assert state.pool is None
    assert "no postgres" in (state.error or "")


def test_healthcheck_reports_pool_state():
    # A fresh (uninitialized) module state healthchecks as not-ok.
    fresh = db.PoolState()
    assert db.healthcheck(fresh)["ok"] is False


def test_init_pool_success_sets_pool(monkeypatch):
    monkeypatch.setattr(db, "mint_databricks_token", lambda: "tok")
    made = {}

    def factory(conninfo):
        made["conninfo"] = conninfo
        return object()

    state = db.PoolState()
    db.init_pool(state, pool_factory=factory)
    assert state.pool is not None
    assert state.error is None
    assert "sslmode=require" in made["conninfo"]
    assert "password=tok" in made["conninfo"]
