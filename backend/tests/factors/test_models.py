"""Domain invariants for factor calculation inputs and audit outputs."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.factors.models import (
    AdjustedClosePoint,
    FactorComponentResult,
    FactorFamily,
    PriceSeriesInput,
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
