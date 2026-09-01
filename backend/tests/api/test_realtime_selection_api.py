"""Offline HTTP regressions for the compact Task25 realtime selection projection."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import stock_selector.realtime.runtime as runtime_module
from stock_selector.api.app import create_app
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.providers.base import ProviderInfo, RealtimeMarketDataProvider
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.providers.requests import RealtimeQuotesRequest
from stock_selector.risk import DatedRiskState

AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
CAPTURE_AT = AS_OF + timedelta(seconds=10)
CALCULATION_AT = CAPTURE_AT + timedelta(seconds=10)
CLASSIFICATION = "证监会行业分类标准（2012）"


class FakeRealtimeProvider(RealtimeMarketDataProvider):
    """A countable all-market provider with no external side effects."""

    def __init__(self, response: tuple[RealtimeQuote, ...] | Exception) -> None:
        self.response = response
        self.requests: list[RealtimeQuotesRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake")

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _application(tmp_path, provider: FakeRealtimeProvider):  # type: ignore[no-untyped-def]
    return create_app(AppPaths.from_project_root(tmp_path), Settings(), provider)


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _quote(symbol: str, *, signal: float = 1) -> RealtimeQuote:
    price = 10 + signal
    return RealtimeQuote(
        symbol=symbol,
        price=price,
        open=10,
        high=price + 0.1,
        low=price - 0.1,
        prev_close=10,
        volume=100,
        amount=1100,
        change_pct=signal,
        turnover_rate=signal,
        volume_ratio=signal,
        ingested_at=CAPTURE_AT,
        source="fake:realtime",
    )


def _seed_ready(client: TestClient, symbols: tuple[str, ...]) -> None:
    repository = client.app.state.repository
    repository.save_instruments(tuple(_instrument(symbol) for symbol in symbols))
    for index, symbol in enumerate(symbols):
        current = 20 + index
        repository.upsert_financial_records(
            (
                FinancialRecord(
                    symbol=symbol,
                    report_period=date(2024, 12, 31),
                    announcement_date=date(2025, 3, 1),
                    available_at=AS_OF - timedelta(days=20),
                    roe=10,
                    roa=10,
                    gross_margin=10,
                    net_margin=10,
                    revenue=100,
                    net_profit=100,
                    deducted_net_profit=100,
                    source="test",
                ),
                FinancialRecord(
                    symbol=symbol,
                    report_period=date(2025, 12, 31),
                    announcement_date=date(2026, 3, 1),
                    available_at=AS_OF - timedelta(days=20),
                    roe=current,
                    roa=current,
                    gross_margin=current,
                    net_margin=current,
                    revenue=100 + current,
                    net_profit=100 + current,
                    deducted_net_profit=100 + current,
                    source="test",
                ),
            )
        )
        repository.upsert_valuation_records(
            (
                ValuationRecord(
                    symbol=symbol,
                    as_of=AS_OF - timedelta(days=1),
                    pe=30 - index,
                    pb=4 - index / 10,
                    pcf=8 - index / 10,
                    source="test",
                ),
            )
        )
        repository.upsert_industry_records(
            (
                IndustryRecord(
                    symbol=symbol,
                    industry_code="C15",
                    industry_name="test",
                    classification=CLASSIFICATION,
                    effective_from=date(2020, 1, 1),
                    source="test",
                ),
            )
        )
    repository.upsert_risk_states(
        tuple(
            DatedRiskState(
                symbol=symbol,
                as_of=AS_OF.date(),
                is_st=False,
                is_suspended=False,
                is_delisting_period=False,
                observed_at=AS_OF,
                source="test",
            )
            for symbol in symbols
        )
    )


def test_realtime_selection_projects_one_ready_runtime_without_persistence(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, 21))
    provider = FakeRealtimeProvider(
        tuple(_quote(symbol, signal=index + 1) for index, symbol in enumerate(symbols))
        + (_quote("600519.SH"),)
    )
    application = _application(tmp_path, provider)
    monkeypatch.setattr(runtime_module, "_system_calculation_at", lambda _timezone: CALCULATION_AT)
    with TestClient(application) as client:
        assert client.app.state.realtime_provider is provider
        _seed_ready(client, symbols)
        before = client.app.state.repository.get_stats()
        response = client.get("/api/selection/realtime", params={"as_of": AS_OF.isoformat()})
        after = client.app.state.repository.get_stats()

    assert response.status_code == 200
    body = response.json()
    assert provider.requests == [RealtimeQuotesRequest(symbols=None)]
    assert before == after
    assert body["selection_ready"] is True
    assert body["blockers"] == []
    assert body["diagnostics"]["capture_scope"] == "all_market"
    assert body["diagnostics"]["received_quotes"] == 21
    assert body["diagnostics"]["persisted_quotes"] == 0
    assert body["diagnostics"]["selection_ready"] is True
    assert body["policy"]["top_n"] == 100
    assert body["items"]
    item = body["items"][0]
    assert {"realtime_rank", "market_rank", "quote", "realtime_score", "industry_key"} <= item.keys()
    assert item["quote"]["symbol"] == item["symbol"]
    assert "capture" not in body and "pipeline" not in body and "factors" not in body


def test_realtime_selection_blocked_and_ready_empty_are_truthful(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime_module, "_system_calculation_at", lambda _timezone: CALCULATION_AT)
    blocked_provider = FakeRealtimeProvider((_quote("600519.SH"),))
    with TestClient(_application(tmp_path / "blocked", blocked_provider)) as client:
        client.app.state.repository.save_instruments((_instrument("600519.SH"),))
        response = client.get("/api/selection/realtime", params={"as_of": AS_OF.isoformat()})
    assert response.status_code == 200
    assert response.json()["selection_ready"] is False
    assert response.json()["items"] == []
    assert len(blocked_provider.requests) == 1

    empty_provider = FakeRealtimeProvider((_quote("600519.SH"),))
    with TestClient(_application(tmp_path / "empty", empty_provider)) as client:
        _seed_ready(client, ("600519.SH",))
        response = client.get("/api/selection/realtime", params={"as_of": AS_OF.isoformat()})
    assert response.status_code == 200
    assert response.json()["selection_ready"] is True
    assert response.json()["diagnostics"]["candidate_ready"] is True
    assert response.json()["items"] == []
    assert len(empty_provider.requests) == 1


def test_realtime_selection_rejects_naive_time_and_translates_expected_provider_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    with TestClient(_application(tmp_path / "naive", provider)) as client:
        response = client.get("/api/selection/realtime", params={"as_of": "2026-03-31T16:00:00"})
    assert response.status_code == 422
    assert provider.requests == []

    offline = FakeRealtimeProvider(ProviderConnectionError("fake", "quotes", "offline"))
    with TestClient(_application(tmp_path / "offline", offline)) as client:
        response = client.get("/api/selection/realtime", params={"as_of": AS_OF.isoformat()})
    assert response.status_code == 503
    assert response.json() == {"detail": "realtime selection unavailable"}
    assert len(offline.requests) == 1


def test_realtime_selection_openapi_and_other_local_routes_do_not_capture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    with TestClient(_application(tmp_path, provider)) as client:
        openapi = client.get("/openapi.json").json()
        realtime = openapi["paths"]["/api/selection/realtime"]["get"]
        assert [parameter["name"] for parameter in realtime["parameters"]] == ["as_of"]
        assert client.get("/api/realtime/status").status_code == 200
        assert client.get("/api/selection/daily", params={"as_of": AS_OF.isoformat()}).status_code == 200
    assert provider.requests == []


def test_unexpected_runtime_error_remains_an_internal_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = FakeRealtimeProvider(RuntimeError("bug"))
    with TestClient(
        _application(tmp_path, provider), raise_server_exceptions=False
    ) as client:
        response = client.get("/api/selection/realtime", params={"as_of": AS_OF.isoformat()})
    assert response.status_code == 500
