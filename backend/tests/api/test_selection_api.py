"""HTTP contract tests for truthful on-demand daily selection readiness."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from stock_selector.api.app import create_app
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    ValuationRecord,
)
from stock_selector.risk import DatedRiskState

_AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_CLASSIFICATION = "证监会行业分类标准（2012）"


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _seed_ready_selection(client: TestClient) -> None:
    repository = client.app.state.repository
    symbols = ("000001.SZ", "600519.SH", "601398.SH")
    repository.save_instruments(tuple(_instrument(symbol) for symbol in symbols))
    for symbol in symbols:
        repository.upsert_risk_states(
            (
                DatedRiskState(
                    symbol=symbol,
                    as_of=_AS_OF.date(),
                    is_st=False,
                    is_suspended=False,
                    is_delisting_period=False,
                    observed_at=_AS_OF,
                    source="synthetic",
                ),
            )
        )
        repository.upsert_financial_records(
            tuple(
                FinancialRecord(
                    symbol=symbol,
                    report_period=period,
                    announcement_date=(_AS_OF - timedelta(days=10)).date(),
                    available_at=_AS_OF - timedelta(days=10),
                    roe=10,
                    roa=10,
                    gross_margin=10,
                    net_margin=10,
                    revenue=110,
                    net_profit=110,
                    deducted_net_profit=110,
                    source="synthetic",
                )
                for period in (date(2024, 12, 31), date(2025, 12, 31))
            )
        )
        repository.upsert_valuation_records(
            (
                ValuationRecord(
                    symbol=symbol,
                    as_of=_AS_OF - timedelta(days=1),
                    pe=10,
                    pb=2,
                    pcf=5,
                    source="synthetic",
                ),
            )
        )
        repository.upsert_industry_records(
            (
                IndustryRecord(
                    symbol=symbol,
                    industry_code="C15",
                    industry_name="酒、饮料和精制茶制造业",
                    classification=_CLASSIFICATION,
                    effective_from=date(2020, 1, 1),
                    source="synthetic",
                ),
            )
        )

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


def test_daily_selection_ready_contract_returns_ranked_qvg_items(tmp_path) -> None:  # type: ignore[no-untyped-def]
    application = create_app(AppPaths.from_project_root(tmp_path), settings=Settings())
    with TestClient(application) as client:
        _seed_ready_selection(client)
        response = client.get("/api/selection/daily", params={"as_of": _AS_OF.isoformat()})

    assert response.status_code == 200
    body = response.json()
    assert body["selection_ready"] is True
    assert body["blockers"] == []
    assert [item["symbol"] for item in body["items"]] == [
        "000001.SZ",
        "600519.SH",
        "601398.SH",
    ]
    assert [item["rank"] for item in body["items"]] == [1, 2, 3]
    assert [item["base_score"] for item in body["items"]] == sorted(
        (item["base_score"] for item in body["items"]), reverse=True
    )
    item = body["items"][0]
    assert {"rank", "symbol", "name", "board", "base_score", "confidence_adjusted_score", "data_completeness", "confidence", "quality_score", "value_score", "growth_score", "momentum_score", "low_volatility_score"} <= item.keys()
    assert item["data_completeness"] == 0.75
    assert item["momentum_score"] is None
    assert item["low_volatility_score"] is None
    assert isinstance(item["evidence"], list) and item["evidence"]
    assert {"code", "message", "factor_name", "value", "percentile", "contribution"} <= item["evidence"][0].keys()
    assert isinstance(item["risks"], list) and item["risks"]
    assert {"code", "message", "severity"} <= item["risks"][0].keys()
    assert any(risk["code"] == "price_factors_unavailable" for risk in item["risks"])
