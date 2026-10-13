"""A test never removes a grant the app SP held before the test."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.catalog import load_catalog
from app.grant import sp_holds_directly
from app.scenarios import run_scenario

SP = "app-sp-id"
TOKEN = {"x-forwarded-access-token": "test-token"}
SELECT_TEMPLATE = "GRANT SELECT ON TABLE {securable} TO `{sp}`"


def grants_exec(rows, sent=None):
    def _exec(sql):
        if sent is not None:
            sent.append(sql)
        return rows
    return _exec


def test_direct_grant_to_the_sp_counts_as_held():
    sent = []
    rows = [{"Principal": SP, "ActionType": "SELECT", "ObjectType": "TABLE", "ObjectKey": "main.s.t"}]
    assert sp_holds_directly(SELECT_TEMPLATE, securable="main.s.t", sp=SP, row_exec=grants_exec(rows, sent))
    assert sent == ["SHOW GRANTS `app-sp-id` ON TABLE `main`.`s`.`t`"]


@pytest.mark.parametrize("row", [
    {"Principal": SP, "ActionType": "SELECT", "ObjectType": "SCHEMA"},       # inherited: REVOKE won't touch it
    {"Principal": "someone-else", "ActionType": "SELECT", "ObjectType": "TABLE"},
    {"Principal": SP, "ActionType": "MODIFY", "ObjectType": "TABLE"},
])
def test_other_grants_do_not_count(row):
    assert not sp_holds_directly(SELECT_TEMPLATE, securable="main.s.t", sp=SP, row_exec=grants_exec([row]))


def test_lookup_failure_or_unknown_template_means_not_held():
    def broken(sql):
        raise RuntimeError("warehouse down")
    assert not sp_holds_directly(SELECT_TEMPLATE, securable="main.s.t", sp=SP, row_exec=broken)
    assert not sp_holds_directly("", securable="main.s.t", sp=SP, row_exec=grants_exec([]))


def test_every_grant_template_is_recognized():
    shapes = {}
    for d in load_catalog().values():
        if d.grant_sql:
            privilege = d.grant_sql.split(" ON ")[0].removeprefix("GRANT ").upper()
            kind = d.grant_sql.split(" ON ")[1].split()[0].upper()
            row = {"Principal": SP, "ActionType": privilege, "ObjectType": kind}
            shapes[d.id] = sp_holds_directly(d.grant_sql, securable="a.b.c", sp=SP, row_exec=grants_exec([row]))
    assert shapes and all(shapes.values()), shapes


def test_scenario_never_revokes_a_grant_that_existed_before_the_run():
    revoked = []
    result = run_scenario(
        [{"action_id": "x", "securable": "held"}, {"action_id": "y", "securable": "new"}],
        apply_fn=lambda a, s: s != "held",
        probe_fn=lambda a, s: {"status": "pass", "detail": ""},
        revoke_fn=lambda a, s: revoked.append(s),
    )
    assert revoked == ["new"]
    assert [r["already_held"] for r in result["results"]] == [True, False]


def test_apply_skips_a_held_grant_and_revoke_refuses_it():
    client = TestClient(main.app)
    main._PREEXISTING.clear()
    executed = []
    held = [{"Principal": SP, "ActionType": "SELECT", "ObjectType": "TABLE"}]
    with patch("app.main._obo_sql_executor", return_value=executed.append), \
         patch("app.main._configured_sp", return_value=SP), \
         patch("app.main._lazy_row_exec", return_value=grants_exec(held)), \
         patch("app.main._log_event"):
        body = {"action_id": "uc.table.select", "securable": "main.s.t"}
        applied = client.post("/api/grant/apply", json=body, headers=TOKEN)
        revoked = client.post("/api/grant/revoke", json=body, headers=TOKEN)
    assert applied.status_code == 200 and applied.json()["status"] == "already_held"
    assert revoked.status_code == 409 and "before your test" in revoked.json()["detail"]
    assert executed == []  # neither GRANT nor REVOKE ran
    main._PREEXISTING.clear()


def test_apply_grants_when_not_held():
    client = TestClient(main.app)
    main._PREEXISTING.clear()
    executed = []
    with patch("app.main._obo_sql_executor", return_value=executed.append), \
         patch("app.main._configured_sp", return_value=SP), \
         patch("app.main._lazy_row_exec", return_value=grants_exec([])), \
         patch("app.main._log_event"):
        r = client.post("/api/grant/apply", json={"action_id": "uc.table.select", "securable": "main.s.t"},
                        headers=TOKEN)
    assert r.status_code == 200 and r.json()["status"] == "applied"
    assert executed == ["GRANT SELECT ON TABLE `main`.`s`.`t` TO `app-sp-id`"]
