"""Instrument, daily-bar, and realtime local-data API tests."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_selector.models import AdjustmentType, DailyBar
from stock_selector.storage import LocalMarketRepository
from tests.api.conftest import instrument, quote


def _save_instruments(repository: LocalMarketRepository) -> None:
    repository.save_instruments(
        (
            instrument("600519.SH", "贵州茅台"),
            instrument("000001.SZ", "平安银行"),
            instrument("430047.BJ", "诺思兰德"),
        )
    )


def _bar(day: int) -> DailyBar:
    return DailyBar(
        symbol="600519.SH",
        trade_date=date(2026, 8, day),
        adjustment=AdjustmentType.RAW,
        open=10.0 + day,
        high=12.0 + day,
        low=9.0 + day,
        close=11.0 + day,
        volume=100.0 * day,
        amount=1100.0 * day,
        source="test:local",
    )


def test_instrument_list_supports_pagination_and_substring_search(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    _save_instruments(repository)
    response = client.get("/api/instruments")
    assert response.status_code == 200
    assert [item["symbol"] for item in response.json()["items"]] == [
        "000001.SZ",
        "430047.BJ",
        "600519.SH",
    ]
    assert client.get("/api/instruments?q=600519").json()["total"] == 1
    assert client.get("/api/instruments?q=sh").json()["total"] == 1
    assert client.get("/api/instruments?q=茅台").json()["total"] == 1
    page = client.get("/api/instruments?limit=1&offset=1").json()
    assert page["total"] == 3
    assert [item["symbol"] for item in page["items"]] == ["430047.BJ"]
    for invalid in ("?limit=0", "?limit=201", "?offset=-1"):
        assert client.get(f"/api/instruments{invalid}").status_code == 422


def test_instrument_detail_validates_and_distinguishes_missing(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    _save_instruments(repository)
    response = client.get("/api/instruments/600519.SH")
    assert response.status_code == 200
    assert response.json()["exchange"] == "SH"
    assert client.get("/api/instruments/600520.SH").json() == {
        "detail": "instrument not found"
    }
    assert client.get("/api/instruments/invalid").status_code == 422


def test_daily_endpoint_handles_empty_filtered_and_limited_local_bars(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    _save_instruments(repository)
    empty = client.get("/api/instruments/000001.SZ/daily").json()
    assert empty["available_rows"] == empty["returned_rows"] == 0
    assert empty["items"] == []
    repository.upsert_daily_bars(tuple(_bar(day) for day in (3, 4, 5)))
    response = client.get("/api/instruments/600519.SH/daily?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert body["available_rows"] == 3
    assert body["returned_rows"] == 2
    assert [item["trade_date"] for item in body["items"]] == ["2026-08-04", "2026-08-05"]
    assert {item["adjustment"] for item in body["items"]} == {"raw"}
    filtered = client.get(
        "/api/instruments/600519.SH/daily?start_date=2026-08-04&end_date=2026-08-04"
    ).json()
    assert [item["trade_date"] for item in filtered["items"]] == ["2026-08-04"]
    assert client.get(
        "/api/instruments/600519.SH/daily?start_date=2026-08-05&end_date=2026-08-04"
    ).status_code == 422
    assert client.get("/api/instruments/invalid/daily").status_code == 422
    assert client.get("/api/instruments/600520.SH/daily").json() == {
        "detail": "instrument not found"
    }


def test_realtime_endpoint_uses_only_latest_local_snapshot(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    _save_instruments(repository)
    empty = client.get("/api/instruments/600519.SH/realtime").json()
    assert empty["available"] is False
    assert empty["latest_snapshot_at"] is None
    at = datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    repository.save_realtime_snapshot((quote("000001.SZ", at),))
    absent = client.get("/api/instruments/600519.SH/realtime").json()
    assert absent["available"] is False
    assert absent["latest_snapshot_at"] == "2026-08-28T08:00:00Z"
    later = at.replace(minute=1)
    repository.save_realtime_snapshot((quote("600519.SH", later),))
    response = client.get("/api/instruments/600519.SH/realtime")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["quote"]["source_timestamp"] == "2026-08-28T08:00:00Z"
    assert body["quote"]["ingested_at"] == "2026-08-28T08:01:00Z"
    assert client.get("/api/instruments/600520.SH/realtime").json() == {
        "detail": "instrument not found"
    }
    assert client.get("/api/instruments/invalid/realtime").status_code == 422
