"""API tests for the v3 endpoints: /api/query and /api/sweep.

Consistent with existing endpoint patterns:
  * input validation (blocked SQL) returns 400 BEFORE any OBO/SP work,
  * endpoints that enumerate/run under OBO return 401 without a token.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_query_blocked_sql_returns_400_before_obo():
    r = client.post("/api/query", json={"sql": "DROP TABLE c.s.t"})
    assert r.status_code == 400
    assert "read-only" in r.json()["detail"].lower()


def test_query_multi_statement_blocked():
    r = client.post("/api/query", json={"sql": "SELECT 1; DROP TABLE x"})
    assert r.status_code == 400


def test_query_requires_sql_or_table():
    r = client.post("/api/query", json={"limit": 10})
    assert r.status_code == 400


def test_query_valid_sql_without_obo_returns_401():
    # A read-only statement passes the guard, then needs the SP/OBO clients.
    r = client.post("/api/query", json={"sql": "SELECT * FROM c.s.t LIMIT 1"})
    assert r.status_code == 401


def test_sweep_without_obo_returns_401():
    r = client.post("/api/sweep", json={"securable": "c.s.t"})
    assert r.status_code == 401
