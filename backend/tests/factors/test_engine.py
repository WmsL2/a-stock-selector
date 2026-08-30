"""Essential factor-family and adjusted-price boundary checks."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.factors import (
    AdjustedClosePoint,
    FactorDataError,
    FiveFactorEngine,
    FiveFactorRequest,
    PriceSeriesInput,
    StockFactorInput,
)
from stock_selector.models import FinancialRecord, ValuationRecord

_AS_OF = datetime(2026, 3, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


def _financial(
    symbol: str,
    *,
    roe: float | None,
    period: date = date(2025, 12, 31),
    available_at: datetime | None = None,
    **values: float | None,
) -> FinancialRecord:
    return FinancialRecord(
        symbol=symbol,
        report_period=period,
        announcement_date=date(2026, 2, 1),
        available_at=available_at
        or datetime(2026, 2, 1, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        roe=roe,
        roa=values.get("roa", roe),
        gross_margin=values.get("gross_margin", roe),
        net_margin=values.get("net_margin", roe),
        revenue=values.get("revenue"),
        net_profit=values.get("net_profit"),
        deducted_net_profit=values.get("deducted_net_profit"),
        source="fixture",
    )


def _stock(
    symbol: str, value: float, industry: str | None = "A", **changes: object
) -> StockFactorInput:
    values: dict[str, object] = {
        "symbol": symbol,
        "as_of": _AS_OF,
        "industry_key": industry,
        "financial_current": _financial(
            symbol,
            roe=value,
            revenue=value,
            net_profit=value,
            deducted_net_profit=value,
        ),
    }
    values.update(changes)
    return StockFactorInput(**values)


def _components(result, symbol: str) -> dict[str, object]:
    stock = next(item for item in result.stocks if item.symbol == symbol)
    return {
        item.factor_name: item
        for family in (
            stock.quality,
            stock.value,
            stock.growth,
            stock.momentum,
            stock.low_volatility,
        )
        for item in family.components
    }


def _prices(symbol: str, returns: float) -> PriceSeriesInput:
    closes = [100.0 + index * returns for index in range(61)]
    return PriceSeriesInput(
        symbol=symbol,
        as_of=_AS_OF,
        points=tuple(
            AdjustedClosePoint(
                trade_date=_AS_OF.date() - timedelta(days=61 - index), close=close
            )
            for index, close in enumerate(closes)
        ),
        corporate_action_adjusted=True,
        source="synthetic",
    )


def test_unadjusted_prices_never_supply_momentum_or_low_volatility() -> None:
    stock = StockFactorInput(
        symbol="600519.SH",
        as_of=_AS_OF,
        price_series=PriceSeriesInput(
            symbol="600519.SH",
            as_of=_AS_OF,
            points=(AdjustedClosePoint(trade_date=date(2026, 3, 30), close=10.0),),
            corporate_action_adjusted=False,
        ),
    )
    result = FiveFactorEngine().compute(FiveFactorRequest(stocks=(stock,)))
    assert result.stocks[0].momentum.available is False
    assert result.stocks[0].low_volatility.available is False


def test_cross_section_rejects_empty_and_mixed_as_of() -> None:
    with pytest.raises(FactorDataError):
        FiveFactorEngine().compute(FiveFactorRequest(stocks=()))
    one = StockFactorInput(symbol="600519.SH", as_of=_AS_OF)
    other = StockFactorInput(symbol="000001.SZ", as_of=_AS_OF.replace(day=30))
    with pytest.raises(FactorDataError):
        FiveFactorEngine().compute(FiveFactorRequest(stocks=(one, other)))


def test_quality_industry_percentiles_and_missing_aggregation() -> None:
    stocks = (
        _stock("000001.SZ", 1, "A"),
        _stock(
            "600519.SH",
            2,
            "A",
            financial_current=_financial(
                "600519.SH", roe=2, roa=None, gross_margin=2, net_margin=2
            ),
        ),
        _stock("601398.SH", 3, "A"),
        _stock("600000.SH", 100, "B"),
        _stock("600036.SH", 200, "B"),
        _stock("600030.SH", 300, "B"),
    )
    result = FiveFactorEngine().compute(FiveFactorRequest(stocks=stocks))
    components = _components(result, "600519.SH")
    assert components["quality_roe"].score == 50.0
    assert (
        _components(result, "000001.SZ")["quality_roe"].score
        == _components(result, "600000.SH")["quality_roe"].score
        == 0.0
    )
    middle = next(item for item in result.stocks if item.symbol == "600519.SH").quality
    assert (
        middle.available_components,
        middle.total_components,
        middle.component_coverage,
    ) == (3, 4, 0.75)
    assert middle.score == pytest.approx(
        sum(item.score for item in middle.components if item.score is not None) / 3
    )


def test_value_growth_and_missing_industry_engine_paths() -> None:
    stocks = tuple(
        _stock(
            symbol,
            value,
            financial_prior_year=_financial(
                symbol,
                roe=value,
                period=date(2024, 12, 31),
                revenue=100,
                net_profit=100,
                deducted_net_profit=100,
            ),
            valuation=ValuationRecord(
                symbol=symbol, as_of=_AS_OF, pe=pe, pb=2, pcf=5, source="fixture"
            ),
        )
        for symbol, value, pe in (
            ("000001.SZ", 120, 10),
            ("600519.SH", 150, 20),
            ("601398.SH", 200, 40),
        )
    )
    result = FiveFactorEngine().compute(FiveFactorRequest(stocks=stocks))
    assert [
        _components(result, symbol)["value_earnings_yield"].score
        for symbol in ("000001.SZ", "600519.SH", "601398.SH")
    ] == [100.0, 50.0, 0.0]
    assert _components(result, "000001.SZ")["growth_revenue_yoy"].raw_value == 20.0
    missing = FiveFactorEngine().compute(
        FiveFactorRequest(
            stocks=(
                _stock(
                    "600000.SH",
                    10,
                    None,
                    valuation=ValuationRecord(
                        symbol="600000.SH",
                        as_of=_AS_OF,
                        pe=10,
                        pb=2,
                        pcf=5,
                        source="fixture",
                    ),
                ),
            )
        )
    )
    assert (
        _components(missing, "600000.SH")[
            "quality_roe"
        ].preprocessing_unavailable_reason.value
        == "missing_industry"
    )


def test_adjusted_price_rankings_pit_and_determinism() -> None:
    stocks = tuple(
        _stock(symbol, value, price_series=_prices(symbol, slope))
        for symbol, value, slope in (
            ("000001.SZ", 1, 0.1),
            ("600519.SH", 2, 0.5),
            ("601398.SH", 3, 1.0),
        )
    )
    normal = FiveFactorEngine().compute(FiveFactorRequest(stocks=stocks))
    reverse = FiveFactorEngine().compute(
        FiveFactorRequest(stocks=tuple(reversed(stocks)))
    )
    assert normal == reverse
    scores = [
        _components(normal, symbol)["momentum_20d"].score
        for symbol in ("000001.SZ", "600519.SH", "601398.SH")
    ]
    assert scores == sorted(scores)
    assert all(
        _components(normal, symbol)["momentum_60d"].available
        for symbol in ("000001.SZ", "600519.SH", "601398.SH")
    )
    future = _stock(
        "600000.SH",
        1,
        financial_current=_financial(
            "600000.SH", roe=1, available_at=_AS_OF + timedelta(seconds=1)
        ),
    )
    with pytest.raises(FactorDataError):
        FiveFactorEngine().compute(FiveFactorRequest(stocks=(future,)))
