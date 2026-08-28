"""Offline local-storage status route tests."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_selector.models import AdjustmentType, DailyBar
from stock_selector.storage import LocalMarketRepository
from tests.api.conftest import instrument, quote


def test_storage_status_is_empty_for_fresh_local_repository(client: TestClient) -> None:
    """Fresh server startup initializes empty local storage and nothing else."""
    response = client.get("/api/storage/status")
    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in body if key.endswith(("rows", "symbols"))} == {
        "instrument_rows": 0,
        "daily_rows": 0,
        "daily_symbols": 0,
        "realtime_rows": 0,
        "realtime_symbols": 0,
    }
    assert body["realtime_snapshots"] == 0
    assert body["latest_realtime_at"] is None
    assert body["disk_usage_bytes"] >= 0


def test_storage_status_reports_persisted_local_coverage(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    """The API maps repository statistics without reading data files itself."""
    repository.save_instruments((instrument(), instrument("000001.SZ", "平安银行")))
    repository.upsert_daily_bars(
        tuple(
            DailyBar(
                symbol="600519.SH",
                trade_date=date(2026, 8, day),
                adjustment=AdjustmentType.RAW,
                open=10.0,
                high=12.0,
                low=9.0,
                close=11.0,
                volume=100.0,
                amount=1100.0,
                source="test:local",
            )
            for day in (3, 4, 5)
        )
    )
    at = datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    repository.save_realtime_snapshot((quote("600519.SH", at), quote("000001.SZ", at)))

    response = client.get("/api/storage/status")
    assert response.status_code == 200
    assert response.json() | {"storage_root": "", "duckdb_path": ""} == {
        "instrument_rows": 2,
        "daily_rows": 3,
        "daily_symbols": 1,
        "realtime_rows": 2,
        "realtime_symbols": 2,
        "realtime_snapshots": 1,
        "latest_realtime_at": "2026-08-28T16:00:00+08:00",
        "disk_usage_bytes": response.json()["disk_usage_bytes"],
        "storage_root": "",
        "duckdb_path": "",
    }
