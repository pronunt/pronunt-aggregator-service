from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_request_id() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_liveness_and_readiness_endpoints_are_available() -> None:
    client = TestClient(app)

    live_response = client.get("/api/v1/health/live")
    ready_response = client.get("/api/v1/health/ready")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "live"
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"
