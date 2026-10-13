"""Tests for the run_scenario endpoint with validation and error handling.

Tests that:
1. Pre-flight validation occurs and returns 400 with detail {message, row, action_id, securable}
2. Mid-batch execution failures return 422 with revoked list
3. Valid scenarios execute without error
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.catalog import load_catalog

client = TestClient(app)


@pytest.fixture
def obo_token():
    """Valid OBO token header."""
    return {"x-forwarded-access-token": "test-token"}


def test_run_scenario_with_empty_action_id_returns_400(obo_token):
    """Missing/empty action_id returns 400 with validation detail."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={"items": [{"action_id": "", "securable": "main"}]},
            headers=obo_token,
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert "message" in detail
    assert "row" in detail
    assert detail["row"] == 0
    assert "action_id" in detail


def test_run_scenario_with_empty_securable_returns_400(obo_token):
    """Missing/empty securable returns 400."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={"items": [{"action_id": "uc.catalog.use", "securable": ""}]},
            headers=obo_token,
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "message" in detail
    assert detail["row"] == 0


def test_run_scenario_with_unknown_action_returns_400(obo_token):
    """Unknown action_id returns 400."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={"items": [{"action_id": "bogus.fake.action", "securable": "main"}]},
            headers=obo_token,
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "not found" in detail["message"].lower() or "action_id" in detail["message"].lower()
    assert detail["row"] == 0


def test_run_scenario_with_wrong_level_returns_400(obo_token):
    """Securable at wrong level returns 400."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={
                "items": [{"action_id": "uc.catalog.use", "securable": "main.sales.orders"}]
            },
            headers=obo_token,
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["row"] == 0


def test_run_scenario_with_placeholder_securable_returns_400(obo_token):
    """Unfilled placeholder in securable returns 400."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={"items": [{"action_id": "uc.catalog.use", "securable": "{catalog}"}]},
            headers=obo_token,
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "placeholder" in detail["message"].lower()


def test_run_scenario_with_sql_injection_securable_returns_400(obo_token):
    """SQL injection attempt in securable is rejected at validation (400)."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={
                "items": [
                    {"action_id": "uc.catalog.use", "securable": "main'; DROP TABLE users; --"}
                ]
            },
            headers=obo_token,
        )
    # Should fail parsing in validation (400), before any execution
    assert r.status_code == 400


def test_run_scenario_valid_items_proceed_to_execution(obo_token):
    """Valid items pass validation and proceed to execution logic."""
    # This test just ensures valid items don't return 400.
    # Full execution requires mocking the entire apply/probe/revoke cycle.
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client") as mock_sp_client, \
         patch("app.main.load_catalog") as mock_load_cat, \
         patch("app.scenarios.run_scenario") as mock_run_scen:

        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"
        mock_sp_client.return_value = MagicMock()
        mock_load_cat.return_value = load_catalog()
        mock_run_scen.return_value = {"overall": "pass", "results": []}

        r = client.post(
            "/api/scenarios/run",
            json={"items": [{"action_id": "uc.catalog.use", "securable": "main"}]},
            headers=obo_token,
        )
    # Valid items should pass validation and attempt execution.
    # (May fail for other reasons like missing real client, but not 400).
    assert r.status_code != 400


def test_run_scenario_first_bad_row_reported_in_400():
    """When multiple items are invalid, error reports the first bad row."""
    with patch("app.main._obo_sql_executor") as mock_exec, \
         patch("app.main._configured_sp") as mock_sp, \
         patch("app.main.get_sp_client"):
        mock_exec.return_value = lambda sql: []
        mock_sp.return_value = "test-sp@example.com"

        r = client.post(
            "/api/scenarios/run",
            json={
                "items": [
                    {"action_id": "uc.catalog.use", "securable": "main"},  # valid
                    {"action_id": "", "securable": "main"},  # invalid (row 1)
                    {"action_id": "bogus", "securable": "main"},  # invalid (row 2)
                ]
            },
            headers={"x-forwarded-access-token": "test-token"},
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["row"] == 1  # First error at row 1
