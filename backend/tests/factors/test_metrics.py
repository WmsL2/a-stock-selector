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
    AdjustedReturnSeriesInput,
    ComponentUnavailableReason,
    PriceSeriesInput,
    StockFactorInput,
)
from stock_selector.models import (
    AdjustedDailyReturn,
    AdjustmentType,
    FinancialRecord,
    ValuationRecord,
)

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


def _return_series(
    values: list[float], *, source: str = "fixture", gap_before_last: bool = False
) -> AdjustedReturnSeriesInput:
    start = _AS_OF.date() - timedelta(days=len(values))
    points = []
    for index, value in enumerate(values):
        trade_date = start + timedelta(days=index + 1)
        previous = trade_date - timedelta(days=1)
        if gap_before_last and index == len(values) - 1:
            previous -= timedelta(days=1)
        points.append(
            AdjustedDailyReturn(
                symbol="600519.SH",
                trade_date=trade_date,
                previous_trade_date=previous,
                return_fraction=value,
                adjustment=AdjustmentType.HFQ,
                observed_at=_AS_OF,
                source=source,
            )
        )
    return AdjustedReturnSeriesInput(symbol="600519.SH", as_of=_AS_OF, points=tuple(points))


def _return_components(values: list[float], **kwargs):
    return price_components(_stock(adjusted_return_series=_return_series(values, **kwargs)))


def _return_components_with_sources(
    values: list[float], sources: list[str]
):
    series = _return_series(values)
    points = tuple(
        point.model_copy(update={"source": source})
        for point, source in zip(series.points, sources, strict=True)
    )
    return price_components(
        _stock(
            adjusted_return_series=AdjustedReturnSeriesInput(
                symbol="600519.SH", as_of=_AS_OF, points=points
            )
        )
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


def test_adjusted_return_20_and_60_day_formulas_and_exact_windows():
    twenty = _return_components([0.01] * 20)
    assert twenty["momentum_20d"].value == pytest.approx((1.01**20 - 1) * 100)
    assert twenty["low_volatility_20d"].value == pytest.approx(0)
    assert twenty["momentum_60d"].reason is ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY
    assert twenty["low_volatility_60d"].reason is ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY

    values = [0.001 * (index % 7) for index in range(60)]
    sixty = _return_components(values)
    expected_momentum = 1.0
    for value in values:
        expected_momentum *= 1 + value
    assert sixty["momentum_60d"].value == pytest.approx((expected_momentum - 1) * 100)
    assert sixty["low_volatility_60d"].value == pytest.approx(pstdev(values) * sqrt(252) * 100)
    longer = _return_components([0.9] * 5 + values)
    assert longer["momentum_20d"].value == pytest.approx(sixty["momentum_20d"].value)
    assert longer["momentum_60d"].value == pytest.approx(sixty["momentum_60d"].value)


@pytest.mark.parametrize("count, names", [(19, ("momentum_20d", "low_volatility_20d")), (59, ("momentum_60d", "low_volatility_60d"))])
def test_adjusted_return_windows_do_not_have_an_off_by_one(count, names):
    components = _return_components([0.01] * count)
    assert all(components[name].reason is ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY for name in names)


def test_adjusted_return_uses_last_contiguous_suffix_and_mixed_source_contract():
    gap = _return_components([0.01] * 25, gap_before_last=True)
    assert gap["momentum_20d"].reason is ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY

    points = list(_return_series([0.01] * 60).points)
    points[-1] = points[-1].model_copy(update={"source": "second-provider"})
    mixed = price_components(
        _stock(adjusted_return_series=AdjustedReturnSeriesInput(symbol="600519.SH", as_of=_AS_OF, points=tuple(points)))
    )
    assert mixed["momentum_20d"].source is None
    assert _return_components([0.01] * 60)["momentum_20d"].source == "fixture"


def test_adjusted_return_uses_latest_contiguous_suffix_not_an_older_longer_segment():
    old_start = _AS_OF.date() - timedelta(days=100)
    old = [
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=old_start + timedelta(days=index + 1),
            previous_trade_date=old_start + timedelta(days=index), return_fraction=0.01,
            adjustment=AdjustmentType.HFQ, observed_at=_AS_OF, source="fixture",
        )
        for index in range(60)
    ]
    latest_start = _AS_OF.date() - timedelta(days=10)
    latest = [
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=latest_start + timedelta(days=index + 1),
            previous_trade_date=latest_start + timedelta(days=index), return_fraction=0.02,
            adjustment=AdjustmentType.HFQ, observed_at=_AS_OF, source="fixture",
        )
        for index in range(10)
    ]
    components = price_components(_stock(adjusted_return_series=AdjustedReturnSeriesInput(
        symbol="600519.SH", as_of=_AS_OF, points=tuple(old + latest)
    )))
    assert all(components[name].reason is ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY for name in (
        "momentum_20d", "momentum_60d", "low_volatility_20d", "low_volatility_60d"
    ))


def test_adjusted_return_provenance_uses_each_component_window_only():
    values = [0.001 * (index % 5) for index in range(80)]
    old_twenty_new_sixty = _return_components_with_sources(
        values, ["old"] * 20 + ["new"] * 60
    )
    assert all(
        old_twenty_new_sixty[name].source == "new"
        for name in (
            "momentum_20d",
            "low_volatility_20d",
            "momentum_60d",
            "low_volatility_60d",
        )
    )

    old_fifty_new_thirty = _return_components_with_sources(
        values, ["old"] * 50 + ["new"] * 30
    )
    assert old_fifty_new_thirty["momentum_20d"].source == "new"
    assert old_fifty_new_thirty["low_volatility_20d"].source == "new"
    assert old_fifty_new_thirty["momentum_60d"].source is None
    assert old_fifty_new_thirty["low_volatility_60d"].source is None

    mixed_latest_twenty = _return_components_with_sources(
        values, ["old"] * 60 + ["new"] * 10 + ["other"] * 10
    )
    assert mixed_latest_twenty["momentum_20d"].source is None
    assert mixed_latest_twenty["low_volatility_20d"].source is None
    assert {
        name: old_twenty_new_sixty[name].value
        for name in old_twenty_new_sixty
    } == pytest.approx({name: old_fifty_new_thirty[name].value for name in old_fifty_new_thirty})
