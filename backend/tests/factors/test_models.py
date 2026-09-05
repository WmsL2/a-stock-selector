"""Domain invariants for factor calculation inputs and audit outputs."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.factors.models import (
    AdjustedClosePoint,
    AdjustedReturnSeriesInput,
    FactorComponentResult,
    FactorFamily,
    FactorFamilyResult,
    FiveFactorCrossSectionResult,
    FiveFactorStockResult,
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


def test_adjusted_close_and_price_series_safety():
    for value in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            AdjustedClosePoint(trade_date=date(2026, 3, 30), close=value)
    point = AdjustedClosePoint(trade_date=date(2026, 3, 30), close=1)
    assert PriceSeriesInput(
        symbol="600519.SH",
        as_of=_AS_OF,
        points=(point,),
        corporate_action_adjusted=True,
    ).points == (point,)
    with pytest.raises(ValidationError):
        PriceSeriesInput(
            symbol="600519",
            as_of=_AS_OF,
            points=(point,),
            corporate_action_adjusted=True,
        )
    with pytest.raises(ValidationError):
        PriceSeriesInput(
            symbol="600519.SH",
            as_of=_AS_OF,
            points=(point, point),
            corporate_action_adjusted=True,
        )
    with pytest.raises(ValidationError):
        PriceSeriesInput(
            symbol="600519.SH",
            as_of=_AS_OF,
            points=(AdjustedClosePoint(trade_date=date(2026, 4, 1), close=1),),
            corporate_action_adjusted=True,
        )


def test_component_audit_invariants():
    base = {
        "factor_name": "quality_roe",
        "family": FactorFamily.QUALITY,
        "raw_value": 1.0,
        "score": 50.0,
        "available": True,
        "raw_unavailable_reason": None,
        "preprocessing_unavailable_reason": None,
    }
    assert FactorComponentResult(**base).available
    for changes in (
        {"raw_unavailable_reason": "missing_financial"},
        {"raw_value": None},
        {"available": False, "score": None},
    ):
        with pytest.raises(ValidationError):
            FactorComponentResult(**{**base, **changes})


def _financial(symbol: str) -> FinancialRecord:
    return FinancialRecord(
        symbol=symbol,
        report_period=date(2025, 12, 31),
        announcement_date=date(2026, 2, 1),
        available_at=datetime(2026, 2, 1, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        roe=1,
        source="fixture",
    )


def _valuation(symbol: str) -> ValuationRecord:
    return ValuationRecord(symbol=symbol, as_of=_AS_OF, pe=10, source="fixture")


def _component(
    name: str = "quality_roe", family: FactorFamily = FactorFamily.QUALITY
) -> FactorComponentResult:
    return FactorComponentResult(
        factor_name=name,
        family=family,
        raw_value=1,
        score=50,
        available=True,
        raw_unavailable_reason=None,
        preprocessing_unavailable_reason=None,
    )


def _family(
    family: FactorFamily = FactorFamily.QUALITY,
    symbol: str = "600519.SH",
    as_of: datetime = _AS_OF,
) -> FactorFamilyResult:
    component = _component(f"{family.value}_component", family)
    return FactorFamilyResult(
        symbol=symbol,
        as_of=as_of,
        family=family,
        score=50,
        available=True,
        available_components=1,
        total_components=1,
        component_coverage=1,
        components=(component,),
    )


def _stock_result(
    symbol: str = "600519.SH", as_of: datetime = _AS_OF
) -> FiveFactorStockResult:
    return FiveFactorStockResult(
        symbol=symbol,
        as_of=as_of,
        quality=_family(FactorFamily.QUALITY, symbol, as_of),
        value=_family(FactorFamily.VALUE, symbol, as_of),
        growth=_family(FactorFamily.GROWTH, symbol, as_of),
        momentum=_family(FactorFamily.MOMENTUM, symbol, as_of),
        low_volatility=_family(FactorFamily.LOW_VOLATILITY, symbol, as_of),
    )


def test_stock_factor_input_child_symbols_and_price_as_of_contracts():
    for field, child in (
        ("financial_current", _financial("000001.SZ")),
        ("financial_prior_year", _financial("000001.SZ")),
        ("valuation", _valuation("000001.SZ")),
        (
            "price_series",
            PriceSeriesInput(
                symbol="000001.SZ",
                as_of=_AS_OF,
                points=(AdjustedClosePoint(trade_date=date(2026, 3, 30), close=1),),
                corporate_action_adjusted=True,
            ),
        ),
    ):
        with pytest.raises(ValidationError):
            StockFactorInput(symbol="600519.SH", as_of=_AS_OF, **{field: child})

    prior_as_of = _AS_OF.replace(day=30)
    price_series = PriceSeriesInput(
        symbol="600519.SH",
        as_of=prior_as_of,
        points=(AdjustedClosePoint(trade_date=date(2026, 3, 29), close=1),),
        corporate_action_adjusted=True,
    )
    with pytest.raises(ValidationError):
        StockFactorInput(
            symbol="600519.SH", as_of=_AS_OF, price_series=price_series
        )


def _return_point(**changes) -> AdjustedDailyReturn:
    values = {
        "symbol": "600519.SH",
        "trade_date": date(2026, 3, 30),
        "previous_trade_date": date(2026, 3, 29),
        "return_fraction": 0.01,
        "adjustment": AdjustmentType.HFQ,
        "observed_at": _AS_OF,
        "source": "fixture",
    }
    values.update(changes)
    return AdjustedDailyReturn(**values)


def test_adjusted_return_series_and_stock_input_contracts():
    point = _return_point()
    series = AdjustedReturnSeriesInput(symbol="600519.SH", as_of=_AS_OF, points=(point,))
    assert series.points == (point,)
    invalid_series = (
        {"symbol": "600519"},
        {"as_of": _AS_OF.replace(tzinfo=None)},
        {"points": (_return_point(symbol="000001.SZ"),)},
        {"points": (_return_point(observed_at=_AS_OF.replace(day=31) + timedelta(days=1)),)},
        {"points": (_return_point(trade_date=date(2026, 4, 1)),)},
        {"points": (point, point)},
    )
    for changes in invalid_series:
        with pytest.raises(ValidationError):
            AdjustedReturnSeriesInput(**({"symbol": "600519.SH", "as_of": _AS_OF, "points": (point,)} | changes))
    with pytest.raises(ValidationError):
        _return_point(adjustment=AdjustmentType.RAW)

    mismatched = AdjustedReturnSeriesInput(
        symbol="000001.SZ", as_of=_AS_OF, points=(_return_point(symbol="000001.SZ"),)
    )
    with pytest.raises(ValidationError):
        StockFactorInput(symbol="600519.SH", as_of=_AS_OF, adjusted_return_series=mismatched)
    stale_as_of = _AS_OF.replace(day=30)
    stale = AdjustedReturnSeriesInput(
        symbol="600519.SH",
        as_of=stale_as_of,
        points=(_return_point(trade_date=date(2026, 3, 29), previous_trade_date=date(2026, 3, 28), observed_at=stale_as_of),),
    )
    with pytest.raises(ValidationError):
        StockFactorInput(symbol="600519.SH", as_of=_AS_OF, adjusted_return_series=stale)
    legacy = PriceSeriesInput(
        symbol="600519.SH", as_of=_AS_OF,
        points=(AdjustedClosePoint(trade_date=date(2026, 3, 30), close=1),),
        corporate_action_adjusted=True,
    )
    with pytest.raises(ValidationError):
        StockFactorInput(symbol="600519.SH", as_of=_AS_OF, price_series=legacy, adjusted_return_series=series)


def test_price_series_naive_empty_source_and_unordered_points_contracts():
    point = AdjustedClosePoint(trade_date=date(2026, 3, 30), close=1)
    with pytest.raises(ValidationError):
        PriceSeriesInput(
            symbol="600519.SH",
            as_of=_AS_OF.replace(tzinfo=None),
            points=(point,),
            corporate_action_adjusted=True,
        )
    with pytest.raises(ValidationError):
        PriceSeriesInput(
            symbol="600519.SH",
            as_of=_AS_OF,
            points=(point,),
            corporate_action_adjusted=True,
            source="",
        )
    unordered = PriceSeriesInput(
        symbol="600519.SH",
        as_of=_AS_OF,
        points=(
            point,
            AdjustedClosePoint(trade_date=date(2026, 3, 29), close=0.9),
        ),
        corporate_action_adjusted=True,
    )
    assert unordered.points[0].trade_date > unordered.points[1].trade_date


def test_factor_family_result_invariants():
    base = {
        "symbol": "600519.SH",
        "as_of": _AS_OF,
        "family": FactorFamily.QUALITY,
        "score": 50,
        "available": True,
        "available_components": 1,
        "total_components": 1,
        "component_coverage": 1,
        "components": (_component(),),
    }
    invalid = (
        {
            "components": (_component(), _component()),
            "available_components": 2,
            "total_components": 2,
        },
        {"components": (_component(family=FactorFamily.VALUE),)},
        {"available_components": 0},
        {"total_components": 2},
        {"component_coverage": 0.5},
    )
    for changes in invalid:
        with pytest.raises(ValidationError):
            FactorFamilyResult(**{**base, **changes})


def test_cross_section_result_invariants():
    first = _stock_result("000001.SZ")
    second = _stock_result("600519.SH")
    base = {"as_of": _AS_OF, "input_count": 2, "stocks": (first, second)}
    invalid = (
        {"input_count": 1},
        {"stocks": (second, first)},
        {"stocks": (first, first)},
        {
            "stocks": (
                first,
                _stock_result("600519.SH", _AS_OF.replace(day=30)),
            )
        },
    )
    for changes in invalid:
        with pytest.raises(ValidationError):
            FiveFactorCrossSectionResult(**{**base, **changes})
