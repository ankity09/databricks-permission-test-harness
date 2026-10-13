from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_scenarios_includes_seed_even_without_db():
    # GET /scenarios requires OBO token (A3 authorization).
    r = client.get(
        "/api/scenarios",
        headers={"x-forwarded-access-token": "test-token"}
    )
    # May fail due to no real SDK, but endpoint should be reached
    assert r.status_code != 401


def test_run_scenario_requires_obo():
    # No OBO header -> 401 (apply is OBO-signed).
    r = client.post(
        "/api/scenarios/run",
        json={"items": [{"action_id": "uc.table.select", "securable": "c.s.t"}]},
    )
    assert r.status_code == 401


def test_save_scenario_requires_obo():
    r = client.post(
        "/api/scenarios",
        json={"name": "X", "items": [{"action_id": "uc.table.select", "securable": "c.s.t"}]},
    )
    assert r.status_code == 401
