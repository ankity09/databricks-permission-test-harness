"""Gated live-workspace integration test (opt-in).

Skipped by default. Runs the full harness loop against a REAL workspace using a
user-selected profile — never auto-selected.

Required env vars (set before running):
  HARNESS_IT=1                 enable this suite
  DATABRICKS_HOST              workspace URL
  DATABRICKS_TOKEN             a token for an identity that can grant on the sandbox
  HARNESS_WAREHOUSE_ID         SQL warehouse id for probes/grants
  HARNESS_SANDBOX_TABLE        a throwaway table the SP can be granted SELECT on
                               (e.g. perm_sandbox.test.orders)
  HARNESS_SP                   the app SP application id (the only grantable principal)

Run:
  HARNESS_IT=1 DATABRICKS_HOST=... DATABRICKS_TOKEN=... \\
  HARNESS_WAREHOUSE_ID=... HARNESS_SANDBOX_TABLE=... HARNESS_SP=... \\
  pytest tests/test_integration.py -v -m integration
"""

import os

import pytest

pytestmark = pytest.mark.integration

_ENABLED = os.environ.get("HARNESS_IT") == "1"

skip_reason = "integration suite disabled (set HARNESS_IT=1 + required env vars)"


@pytest.fixture(scope="module")
def wc():
    if not _ENABLED:
        pytest.skip(skip_reason)
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient(
        host=os.environ["DATABRICKS_HOST"],
        token=os.environ["DATABRICKS_TOKEN"],
    )
    # FIRST ASSERTION: OBO/auth must resolve the current user, else abort early
    # with a clear message rather than confusing downstream failures.
    try:
        me = client.current_user.me()
        assert me.user_name, "current user has no user_name"
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"OBO not configured / auth failed: {exc}")
    return client


def _exec(wc, sql):
    resp = wc.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=os.environ["HARNESS_WAREHOUSE_ID"],
        wait_timeout="30s",
    )
    return resp


def test_full_loop_apply_probe_revoke(wc):
    from app.catalog import load_catalog
    from app.grant import apply_to_sp, revoke_from_sp

    sp = os.environ["HARNESS_SP"]
    table = os.environ["HARNESS_SANDBOX_TABLE"]
    d = load_catalog()["uc.table.select"]

    def executor(sql):
        return _exec(wc, sql)

    # apply SELECT to SP
    apply_to_sp(d.grant_sql, principal=sp, configured_sp=sp, executor=executor, securable=table)

    # probe: SP should now be able to select (run as the same client here)
    r = _exec(wc, f"SELECT * FROM {table} LIMIT 1")
    state = r.status.state.value if r.status and r.status.state else ""
    assert state == "SUCCEEDED"

    # revoke
    revoke_from_sp(d.revoke_sql, principal=sp, configured_sp=sp, executor=executor, securable=table)


def test_guard_blocks_real_principal_live(wc):
    """Even against a live workspace, the guard must refuse a non-SP principal."""
    from app.grant import ForbiddenPrincipalError, apply_to_sp

    sp = os.environ["HARNESS_SP"]

    def executor(sql):  # pragma: no cover - must never be called
        raise AssertionError("executor ran for a forbidden principal")

    with pytest.raises(ForbiddenPrincipalError):
        apply_to_sp(
            "GRANT SELECT ON TABLE t TO `{sp}`",
            principal="real.user@corp.com",
            configured_sp=sp,
            executor=executor,
        )
