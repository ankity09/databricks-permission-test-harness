from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_scenarios_includes_seed_even_without_db():
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["scenarios"]]
    assert "Data Analyst" in names  # seed always present


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
