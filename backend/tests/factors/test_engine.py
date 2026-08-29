"""Essential factor-family and adjusted-price boundary checks."""

from datetime import date, datetime
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

_AS_OF = datetime(2026, 3, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


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
