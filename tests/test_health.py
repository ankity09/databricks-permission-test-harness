from fastapi.testclient import TestClient
from app.main import app

class TestHealth:
    def setup_method(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}