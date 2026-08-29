"""Offline quality-status API contract tests."""

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository
from tests.api.conftest import instrument


def test_quality_status_reports_missing_data_as_not_ready(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    repository.save_instruments((instrument(),))
    response = client.get("/api/quality/status")
    assert response.status_code == 200
    body = response.json()
    assert body["risk_filter_ready"] is False
    assert body["risk_eligible_instruments"] is None
    assert body["risk_complete_instruments"] == 0


def test_quality_status_reports_complete_exact_date_states(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    repository.save_instruments((instrument(),))
    initial = client.get("/api/quality/status")
    assert initial.status_code == 200
    as_of = date.fromisoformat(initial.json()["as_of"])
    repository.upsert_risk_states(
        (
            DatedRiskState(
                symbol="600519.SH",
                as_of=as_of,
                is_st=False,
                is_suspended=False,
                is_delisting_period=False,
                observed_at=datetime(2026, 8, 29, 9, tzinfo=UTC),
                source="test",
            ),
        )
    )
    response = client.get("/api/quality/status")
    assert response.status_code == 200
    body = response.json()
    assert body["risk_filter_ready"] is True
    assert body["risk_eligible_instruments"] == 1
