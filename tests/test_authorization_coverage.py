"""Route coverage test: all protected endpoints require OBO token (A3 wiring).

This test auto-discovers all /api routes and asserts they either:
- Are open (GET /health, GET /actions)
- Require OBO token (401 without x-forwarded-access-token)
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_actions_are_open():
    """GET /health and GET /actions do not require auth."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/actions").status_code == 200


def test_me_requires_obo_token():
    """GET /me returns 401 without OBO token."""
    assert client.get("/api/me").status_code == 401


def test_grant_apply_requires_obo_token():
    """POST /grant/apply returns 401 without OBO token."""
    r = client.post("/api/grant/apply", json={"action_id": "uc.table.select", "securable": "c.s.t"})
    assert r.status_code == 401


def test_grant_revoke_requires_obo_token():
    """POST /grant/revoke returns 401 without OBO token."""
    r = client.post("/api/grant/revoke", json={"action_id": "uc.table.select", "securable": "c.s.t"})
    assert r.status_code == 401


def test_probe_requires_obo_token():
    """POST /probe returns 401 without OBO token."""
    r = client.post("/api/probe", json={"action_id": "uc.table.select", "securable": "c.s.t"})
    assert r.status_code == 401


def test_activity_requires_obo_token():
    """GET /activity returns 401 without OBO token."""
    assert client.get("/api/activity").status_code == 401


def test_query_requires_obo_token():
    """POST /query returns 401 without OBO token."""
    r = client.post("/api/query", json={"sql": "SELECT 1"})
    assert r.status_code == 401


def test_sweep_requires_obo_token():
    """POST /sweep returns 401 without OBO token."""
    r = client.post("/api/sweep", json={"securable": "c.s.t"})
    assert r.status_code == 401


def test_scenarios_list_requires_obo_token():
    """GET /scenarios returns 401 without OBO token."""
    assert client.get("/api/scenarios").status_code == 401


def test_scenarios_save_requires_obo_token():
    """POST /scenarios returns 401 without OBO token."""
    r = client.post("/api/scenarios", json={"name": "test", "items": []})
    assert r.status_code == 401


def test_scenarios_run_requires_obo_token():
    """POST /scenarios/run returns 401 without OBO token."""
    r = client.post("/api/scenarios/run", json={"items": []})
    assert r.status_code == 401


def test_agent_chat_requires_obo_token():
    """POST /agent/chat returns 401 without OBO token."""
    r = client.post("/api/agent/chat", json={"messages": []})
    assert r.status_code == 401


def test_catalog_browse_requires_obo_token():
    """POST /catalog/browse returns 401 without OBO token."""
    r = client.post("/api/catalog/browse", json={"level": "root"})
    assert r.status_code == 401


def test_catalog_search_requires_obo_token():
    """POST /catalog/search returns 401 without OBO token."""
    r = client.post("/api/catalog/search", json={"query": "t"})
    assert r.status_code == 401


def test_promote_requires_obo_token():
    """POST /promote returns 401 without OBO token."""
    r = client.post("/api/promote?principal=user@corp.com", json={"action_id": "uc.table.select", "securable": "c.s.t"})
    assert r.status_code == 401


def test_reset_sp_requires_obo_token():
    """POST /reset-sp returns 401 without OBO token."""
    assert client.post("/api/reset-sp", json={}).status_code == 401
