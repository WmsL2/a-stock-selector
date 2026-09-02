"""Offline current structural-universe API tests."""

from datetime import date

from fastapi.testclient import TestClient

from stock_selector.storage import LocalMarketRepository
from tests.api.conftest import instrument


def test_universe_status_reports_structural_counts_and_explicit_limits(
    client: TestClient, repository: LocalMarketRepository
) -> None:
    repository.save_instruments(
        (
            instrument("600519.SH", "贵州茅台"),
            instrument("000001.SZ", "平安银行"),
        )
    )
    response = client.get("/api/universe/status")
    assert response.status_code == 200
    body = response.json()
    assert date.fromisoformat(body["as_of"]) >= date(2000, 1, 1)
    assert body["data_scope"] == "current_instrument_master"
    assert body["input_instruments"] == 2
    assert body["included_instruments"] == 2
    assert body["excluded_instruments"] == 0
    assert body["boards"] == {
        "sh_main": 1,
        "sz_main": 1,
        "chinext": 0,
        "star": 0,
        "bse": 0,
    }
    assert body["exclusions"] == {
        "non_a_share_security": 0,
        "board_disabled": 0,
        "not_yet_listed": 0,
        "delisted": 0,
        "min_listing_days": 0,
    }
    assert body["risk_filters_applied"] is False
    assert body["historical_survivorship_safe"] is False
