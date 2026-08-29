"""Read-only point-in-time fundamentals API tests."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_selector.models import FinancialRecord, ValuationRecord
from stock_selector.storage import LocalMarketRepository
from tests.api.conftest import instrument

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_fundamentals_and_valuation_never_use_future_records(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    repository.save_instruments((instrument(),))
    repository.upsert_financial_records(
        (
            FinancialRecord(
                symbol="600519.SH",
                report_period=date(2025, 12, 31),
                announcement_date=date(2026, 3, 25),
                available_at=datetime(2026, 3, 25, 15, 30, tzinfo=_SHANGHAI),
                revenue=100.0,
                source="test",
            ),
        )
    )
    repository.upsert_valuation_records(
        (
            ValuationRecord(
                symbol="600519.SH",
                as_of=datetime(2026, 1, 2, 15, 30, tzinfo=_SHANGHAI),
                pe=-5.0,
                source="test",
            ),
        )
    )
    future_financial = client.get(
        "/api/instruments/600519.SH/fundamentals?as_of=2026-03-25T10:00:00%2B08:00"
    )
    assert future_financial.status_code == 200
    assert future_financial.json()["items"] == []
    visible_financial = client.get(
        "/api/instruments/600519.SH/fundamentals?as_of=2026-03-25T16:00:00%2B08:00"
    )
    assert visible_financial.json()["items"][0]["revenue"] == 100.0
    valuation = client.get(
        "/api/instruments/600519.SH/valuation?as_of=2026-01-03T16:00:00%2B08:00"
    )
    assert valuation.json()["record"]["pe"] == -5.0
    assert (
        client.get(
            "/api/instruments/600519.SH/valuation?as_of=2026-01-01T16:00:00%2B08:00"
        ).json()["record"]
        is None
    )
    assert (
        client.get(
            "/api/instruments/600519.SH/valuation?as_of=2026-01-03T16:00:00"
        ).status_code
        == 422
    )
    status_response = client.get("/api/fundamentals/status")
    assert status_response.status_code == 200
    assert status_response.json()["financial_point_in_time_safe"] is True
