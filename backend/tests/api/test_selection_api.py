"""HTTP contract tests for truthful on-demand daily selection readiness."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


def test_daily_selection_returns_truthful_empty_readiness(client: TestClient) -> None:
    response = client.get("/api/selection/daily")
    assert response.status_code == 200
    body = response.json()
    assert body["selection_ready"] is False
    assert body["items"] == []
    assert body["diagnostics"]["risk_coverage_ratio"] == 0


def test_daily_selection_rejects_naive_as_of(client: TestClient) -> None:
    response = client.get("/api/selection/daily", params={"as_of": "2026-03-31T16:00:00"})
    assert response.status_code == 422
    aware = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert client.get("/api/selection/daily", params={"as_of": aware.isoformat()}).status_code == 200
