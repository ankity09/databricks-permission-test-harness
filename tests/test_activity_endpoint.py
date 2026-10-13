from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_activity_endpoint_returns_empty_when_db_down():
    # With no Lakebase pool, the endpoint should degrade gracefully to [].
    # Now requires OBO token (A3 authorization).
    r = client.get("/api/activity", headers={"x-forwarded-access-token": "test-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["db"]["ok"] is False
