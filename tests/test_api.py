from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_catalog_endpoint_lists_actions():
    r = client.get("/api/actions")
    assert r.status_code == 200
    assert any(a["id"] == "uc.table.select" for a in r.json())


def test_apply_without_obo_header_returns_401():
    r = client.post(
        "/api/grant/apply",
        json={"action_id": "uc.table.select", "securable": "main.s.t"},
    )
    assert r.status_code == 401


def test_apply_wrong_securable_level_returns_400_before_obo():
    """USE CATALOG given a 3-part name is an input error (400), not a 401/422.

    Validated up front so the user never sees a PARSE_SYNTAX_ERROR mislabeled
    as a grant-authority failure.
    """
    r = client.post(
        "/api/grant/apply",
        json={
            "action_id": "uc.catalog.use",
            "securable": "main.sandbox.analytics",
        },
    )
    assert r.status_code == 400
    assert "catalog" in r.json()["detail"].lower()


def test_me_without_obo_header_returns_401():
    r = client.get("/api/me")
    assert r.status_code == 401


def test_catalog_browse_without_obo_returns_401():
    r = client.post("/api/catalog/browse", json={"level": "root"})
    assert r.status_code == 401


def test_catalog_search_without_obo_returns_401():
    r = client.post("/api/catalog/search", json={"query": "orders"})
    assert r.status_code == 401


def test_promote_requires_obo():
    """Promote now requires OBO token for authorization (A3 hardening)."""
    r = client.post(
        "/api/promote?principal=analyst@corp.com",
        json={"action_id": "uc.table.select", "securable": "main.sales.orders"},
    )
    assert r.status_code == 401
