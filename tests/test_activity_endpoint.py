from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_activity_endpoint_returns_empty_when_db_down():
    # With no Lakebase pool, the endpoint should degrade gracefully to [].
    r = client.get("/api/activity")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["db"]["ok"] is False
