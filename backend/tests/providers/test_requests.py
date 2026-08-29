"""Tests for immutable provider request validation."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.models import AdjustmentType
from stock_selector.providers import (
    DailyBarsRequest,
    FinancialRecordsRequest,
    IndustryRecordsRequest,
    MinuteBarsRequest,
    RealtimeQuotesRequest,
    ValuationRecordsRequest,
)


def _aware_time() -> datetime:
    """Return an explicit timezone-aware request timestamp."""
    return datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _naive_time() -> datetime:
    """Return a deliberately naive time for rejection tests."""
    return datetime.fromisoformat("2026-01-02T09:30:00")


def test_daily_bars_request_validates_symbol_and_date_range() -> None:
    """Daily-bar requests require a canonical symbol and ordered dates."""
    request = DailyBarsRequest(
        symbol="600519.SH", start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
    )
    assert request.symbol == "600519.SH"
    assert request.adjustment is AdjustmentType.RAW
    with pytest.raises(ValidationError):
        DailyBarsRequest(
            symbol="600519", start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
        )
    with pytest.raises(ValidationError):
        DailyBarsRequest(
            symbol="600519.SH", start_date=date(2026, 1, 2), end_date=date(2026, 1, 1)
        )


def test_minute_bars_request_requires_aware_ordered_datetimes() -> None:
    """Minute requests require timezone-aware start and end boundaries."""
    request = MinuteBarsRequest(
        symbol="600519.SH", start_at=_aware_time(), end_at=_aware_time()
    )
    assert request.start_at == _aware_time()
    for start_at, end_at in (
        (_naive_time(), _aware_time()),
        (_aware_time(), _naive_time()),
        (_aware_time(), datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai"))),
    ):
        with pytest.raises(ValidationError):
            MinuteBarsRequest(symbol="600519.SH", start_at=start_at, end_at=end_at)


def test_realtime_quotes_request_distinguishes_none_from_empty_batch() -> None:
    """All-market mode is None; explicit symbol batches are nonempty and unique."""
    assert RealtimeQuotesRequest().symbols is None
    assert RealtimeQuotesRequest(symbols=("600519.SH",)).symbols == ("600519.SH",)
    assert RealtimeQuotesRequest(symbols=("600519.SH", "000001.SZ")).symbols == (
        "600519.SH",
        "000001.SZ",
    )
    for symbols in ((), ("600519",), ("600519.SH", "600519.SH")):
        with pytest.raises(ValidationError):
            RealtimeQuotesRequest(symbols=symbols)


def test_financial_records_request_validates_batch_and_period_range() -> None:
    """Financial requests require unique symbols and ordered optional periods."""
    request = FinancialRecordsRequest(symbols=("600519.SH", "000001.SZ"))
    assert request.symbols == ("600519.SH", "000001.SZ")
    for symbols in ((), ("600519.SH", "600519.SH"), ("invalid",)):
        with pytest.raises(ValidationError):
            FinancialRecordsRequest(symbols=symbols)
    with pytest.raises(ValidationError):
        FinancialRecordsRequest(
            symbols=("600519.SH",),
            start_period=date(2026, 1, 2),
            end_period=date(2026, 1, 1),
        )


def test_valuation_and_industry_requests_validate_optional_as_of() -> None:
    """Valuation time is timezone-aware and industry history supports no cutoff."""
    valuation = ValuationRecordsRequest(symbols=("600519.SH",), as_of=_aware_time())
    assert valuation.as_of == _aware_time()
    with pytest.raises(ValidationError):
        ValuationRecordsRequest(symbols=("600519.SH",), as_of=_naive_time())
    industry = IndustryRecordsRequest(symbols=("600519.SH",), as_of=None)
    assert industry.as_of is None
