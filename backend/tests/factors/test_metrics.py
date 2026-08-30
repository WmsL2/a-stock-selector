"""Direct synthetic regression tests for five-family raw formulas."""

from datetime import date, datetime, timedelta
from math import sqrt
from statistics import pstdev
from zoneinfo import ZoneInfo

import pytest

from stock_selector.factors.metrics import (
    financial_components,
    growth_components,
    price_components,
    value_components,
)
from stock_selector.factors.models import (
    AdjustedClosePoint,
    ComponentUnavailableReason,
    PriceSeriesInput,
    StockFactorInput,
)
from stock_selector.models import FinancialRecord, ValuationRecord

_AS_OF = datetime(2026, 3, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


def _financial(period=date(2025, 9, 30), **changes):
    values = {
        "symbol": "600519.SH",
        "report_period": period,
        "announcement_date": date(2026, 1, 1),
        "available_at": datetime(2026, 1, 1, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        "roe": 20.0,
        "roa": 10.0,
        "gross_margin": 60.0,
        "net_margin": 30.0,
        "revenue": 120.0,
        "net_profit": 150.0,
        "deducted_net_profit": 80.0,
        "source": "fixture",
    }
    values.update(changes)
    return FinancialRecord(**values)


def _stock(**changes):
    values = {"symbol": "600519.SH", "as_of": _AS_OF}
    values.update(changes)
    return StockFactorInput(**values)


def _series(count, adjusted=True, closes=None):
    values = closes or [100.0 + index for index in range(count)]
    return PriceSeriesInput(
        symbol="600519.SH",
        as_of=_AS_OF,
        points=tuple(
            AdjustedClosePoint(
                trade_date=_AS_OF.date() - timedelta(days=count - index), close=value
            )
            for index, value in enumerate(values)
        ),
        corporate_action_adjusted=adjusted,
        source="fixture",
    )


def test_quality_value_and_growth_formulas_and_reasons():
    quality = financial_components(_stock(financial_current=_financial()))
    assert {name: item.value for name, item in quality.items()} == {
        "quality_roe": 20.0,
        "quality_roa": 10.0,
        "quality_gross_margin": 60.0,
        "quality_net_margin": 30.0,
    }
    valuation = ValuationRecord(
        symbol="600519.SH", as_of=_AS_OF, pe=10, pb=2, pcf=5, source="fixture"
    )
    values = value_components(_stock(valuation=valuation))
    assert values["value_earnings_yield"].value == pytest.approx(0.1)
    assert values["value_book_to_price"].value == pytest.approx(0.5)
    assert values["value_cashflow_yield"].value == pytest.approx(0.2)
    growth = growth_components(
        _stock(
            financial_current=_financial(),
            financial_prior_year=_financial(
                date(2024, 9, 30), revenue=100, net_profit=100, deducted_net_profit=100
            ),
        )
    )
    assert [growth[name].value for name in growth] == [20.0, 50.0, -20.0]
    negative = value_components(
        _stock(
            valuation=ValuationRecord(
                symbol="600519.SH",
                as_of=_AS_OF,
                pe=-10,
                pb=0,
                pcf=None,
                source="fixture",
            )
        )
    )
    assert all(
        item.reason
        in (
            ComponentUnavailableReason.NONPOSITIVE_VALUATION_MULTIPLE,
            ComponentUnavailableReason.MISSING_COMPONENT_VALUE,
        )
        for item in negative.values()
    )
    missing_financial = financial_components(_stock(financial_current=None))
    assert all(
        item.reason is ComponentUnavailableReason.MISSING_FINANCIAL
        for item in missing_financial.values()
    )
    partial_quality = financial_components(_stock(financial_current=_financial(roa=None)))
    assert (
        partial_quality["quality_roa"].reason
        is ComponentUnavailableReason.MISSING_COMPONENT_VALUE
    )
    assert all(
        partial_quality[name].value is not None
        for name in ("quality_roe", "quality_gross_margin", "quality_net_margin")
    )


def test_growth_and_price_boundaries_and_formulas():
    wrong = growth_components(
        _stock(
            financial_current=_financial(),
            financial_prior_year=_financial(date(2024, 12, 31)),
        )
    )
    assert all(
        item.reason is ComponentUnavailableReason.MISSING_PRIOR_YEAR
        for item in wrong.values()
    )
    negative_current = growth_components(
        _stock(
            financial_current=_financial(net_profit=-20),
            financial_prior_year=_financial(date(2024, 9, 30), net_profit=100),
        )
    )
    assert negative_current["growth_net_profit_yoy"].value == -120.0
    for base in (0, -100):
        growth = growth_components(
            _stock(
                financial_current=_financial(net_profit=50),
                financial_prior_year=_financial(
                    date(2024, 9, 30), net_profit=base
                ),
            )
        )
        assert growth["growth_net_profit_yoy"].value is None
        assert (
            growth["growth_net_profit_yoy"].reason
            is ComponentUnavailableReason.NONPOSITIVE_GROWTH_BASE
        )
    for count, expected_20d, expected_60d in (
        (10, False, False),
        (30, True, False),
        (60, True, False),
        (61, True, True),
    ):
        components = price_components(_stock(price_series=_series(count)))
        for name in ("momentum_20d", "low_volatility_20d"):
            assert (components[name].value is not None) is expected_20d
        for name in ("momentum_60d", "low_volatility_60d"):
            assert (components[name].value is not None) is expected_60d
    closes = [100.0] + [101.0] * 59 + [120.0]
    price = price_components(_stock(price_series=_series(61, closes=closes)))
    assert price["momentum_20d"].value == pytest.approx((120 / 101 - 1) * 100)
    assert price["momentum_60d"].value == pytest.approx(20.0)
    returns = [closes[index] / closes[index - 1] - 1 for index in range(41, 61)]
    assert price["low_volatility_20d"].value == pytest.approx(
        pstdev(returns) * sqrt(252) * 100
    )
    returns_60d = [closes[index] / closes[index - 1] - 1 for index in range(1, 61)]
    assert price["low_volatility_60d"].value == pytest.approx(
        pstdev(returns_60d) * sqrt(252) * 100
    )
    raw = price_components(_stock(price_series=_series(61, adjusted=False)))
    assert all(
        item.reason is ComponentUnavailableReason.UNADJUSTED_PRICE_SERIES
        for item in raw.values()
    )
