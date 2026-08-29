"""Offline daily storage status endpoint tests."""

from datetime import date

from fastapi.testclient import TestClient

from stock_selector.models import AdjustmentType, DailyBar
from stock_selector.storage import LocalMarketRepository


def test_daily_status_is_explicit_for_empty_and_persisted_storage(client: TestClient, repository: LocalMarketRepository) -> None:
    empty = client.get("/api/daily/status")
    assert empty.status_code == 200
    assert empty.json() == {
        "stored_symbols": 0,
        "stored_rows": 0,
        "earliest_trade_date": None,
        "latest_trade_date": None,
        "adjustment_basis": "raw",
        "corporate_action_adjusted": False,
        "full_market_completeness_verified": False,
        "trading_calendar_gap_check_applied": False,
    }
    repository.upsert_daily_bars((_bar("600519.SH", 3), _bar("600519.SH", 5)))
    repository.upsert_daily_bars((_bar("000001.SZ", 4),))
    body = client.get("/api/daily/status").json()
    assert body["stored_symbols"] == 2
    assert body["stored_rows"] == 3
    assert body["earliest_trade_date"] == "2026-08-03"
    assert body["latest_trade_date"] == "2026-08-05"


def _bar(symbol: str, day: int) -> DailyBar:
    return DailyBar(symbol=symbol, trade_date=date(2026, 8, day), adjustment=AdjustmentType.RAW, open=9, high=11, low=8, close=10, volume=100, amount=1000, source="test")
