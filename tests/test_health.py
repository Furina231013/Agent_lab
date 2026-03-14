"""A tiny smoke test still has value.

It checks that the app imports, routes register correctly, and the simplest
response contract stays stable while the project grows.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
