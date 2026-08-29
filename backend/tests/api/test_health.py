"""Health endpoint tests with no provider boundary involved."""

from fastapi.testclient import TestClient

from stock_selector import __version__


def test_health_reports_local_application_ready(client: TestClient) -> None:
    """Health means only the application and local storage boundary are available."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "a-stock-selector",
        "version": __version__,
        "storage": "ready",
    }
