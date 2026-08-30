"""Read-only realtime status endpoint tests."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from stock_selector.models import RealtimeQuote
from stock_selector.storage import LocalMarketRepository


def test_realtime_status_is_unavailable_without_local_snapshot(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    response = client.get("/api/realtime/status")
    assert response.status_code == 200
    body = response.json()
    assert body["freshness"] == "unavailable"
    assert body["latest_ingested_at"] is None
    assert body["stored_quotes"] == 0
    assert body["ranking_allowed"] is False
    assert repository.load_latest_realtime_snapshot() == ()


def test_realtime_status_reports_a_fresh_local_snapshot(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    now = datetime.now(UTC)
    repository.save_realtime_snapshot((_quote(now, source_timestamp=now),))
    before = repository.load_latest_realtime_snapshot()
    fresh = client.get("/api/realtime/status")
    assert fresh.status_code == 200
    body = fresh.json()
    assert body["freshness"] == "fresh"
    assert body["ranking_allowed"] is True
    assert body["source"] == "test:local"
    assert body["stored_quotes"] == 1
    assert body["source_timestamp_available_quotes"] == 1
    assert body["snapshot_scope"] == "selective_persisted"
    assert repository.load_latest_realtime_snapshot() == before


def test_realtime_status_reports_a_stale_local_snapshot(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    repository.save_realtime_snapshot(
        (_quote(datetime.now(UTC) - timedelta(minutes=10)),)
    )
    stale = client.get("/api/realtime/status")
    assert stale.status_code == 200
    assert stale.json()["freshness"] == "stale"
    assert stale.json()["ranking_allowed"] is False
    assert stale.json()["snapshot_scope"] == "selective_persisted"


def _quote(
    ingested_at: datetime,
    *,
    source_timestamp: datetime | None = None,
) -> RealtimeQuote:
    return RealtimeQuote(
        symbol="600519.SH",
        price=10,
        ingested_at=ingested_at,
        source="test:local",
        source_timestamp=source_timestamp,
    )
