"""Gated live-workspace integration tests for v2 (Lakebase, scenarios, UAIG).

These hit real infrastructure and are SKIPPED unless HARNESS_INTEGRATION=1 is set
(and the relevant env vars are present). Never auto-run: run explicitly with
    HARNESS_INTEGRATION=1 <profile env> python -m pytest -m integration
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_ENABLED = os.environ.get("HARNESS_INTEGRATION") == "1"


@pytest.mark.skipif(not _ENABLED, reason="HARNESS_INTEGRATION!=1")
def test_lakebase_write_read_roundtrip():
    """Write one activity row via the real pool, then read it back."""
    import app.db as db
    from app import activity
    from app.config import get_settings

    db.init_pool(db.get_state())
    pool = db.get_pool()
    assert pool is not None, f"pool not available: {db.get_state().error}"

    import contextlib

    @contextlib.contextmanager
    def factory():
        with pool.connection() as conn:
            yield conn

    schema = get_settings().db_schema
    row_id = activity.log_event(
        conn_factory=factory,
        schema=schema,
        session_id="itest",
        admin_email="itest@example.com",
        sp_id="itest-sp",
        event_type="probe",
        action_id="uc.table.select",
        securable="itest.itest.itest",
        verdict="pass",
        raw_message="",
    )
    rows = activity.read_events(conn_factory=factory, schema=schema, limit=50)
    assert any(r.get("id") == row_id for r in rows)


@pytest.mark.skipif(not _ENABLED, reason="HARNESS_INTEGRATION!=1")
def test_scenario_run_matrix_on_sandbox():
    """Run a small scenario end-to-end and assert a matrix shape.

    Requires a sandbox securable the app SP can be granted on (set via
    HARNESS_ITEST_CATALOG/SCHEMA/TABLE) and a live OBO/SP environment.
    """
    pytest.skip("Requires live OBO admin token + sandbox securable; run manually.")


@pytest.mark.skipif(not _ENABLED, reason="HARNESS_INTEGRATION!=1")
def test_uaig_call_returns_response():
    """One live UAIG call through the governed model service."""
    from app.config import get_settings
    from app.uaig import call_model

    s = get_settings()
    if not (s.uaig_base_url and s.uaig_model_service):
        pytest.skip("UAIG env not configured")
    token = os.environ.get("HARNESS_ITEST_TOKEN")
    if not token:
        pytest.skip("no HARNESS_ITEST_TOKEN for the UAIG call")
    out = call_model(
        [{"role": "user", "content": "Say OK."}],
        tools=[],
        token=token,
    )
    assert "content" in out
