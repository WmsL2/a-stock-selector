"""Tests for shared domain-model conventions."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_selector.models.common import (
    ensure_aware_datetime,
    ensure_finite_float,
    validate_symbol,
)


@pytest.mark.parametrize("symbol", ["600519.SH", "000001.SZ", "430047.BJ"])
def test_valid_canonical_symbols(symbol: str) -> None:
    """Canonical six-digit symbols and suffixes are accepted."""
    assert validate_symbol(symbol) == symbol


@pytest.mark.parametrize(
    "symbol",
    ["600519", "sh600519", "600519.SSE", "600519.sh", "60051.SH", "ABC519.SH"],
)
def test_invalid_symbols_are_rejected(symbol: str) -> None:
    """Provider-specific and malformed symbol formats are rejected."""
    with pytest.raises(ValueError):
        validate_symbol(symbol)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_floats_are_rejected(value: float) -> None:
    """Core numeric values cannot be NaN or infinite."""
    with pytest.raises(ValueError):
        ensure_finite_float(value, "value")


def test_aware_datetime_is_accepted_and_naive_datetime_is_rejected() -> None:
    """Timestamp helpers require callers to supply a timezone."""
    aware = datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert ensure_aware_datetime(aware, "timestamp") == aware
    with pytest.raises(ValueError):
        ensure_aware_datetime(_naive_datetime(), "timestamp")


def _naive_datetime() -> datetime:
    """Return a deliberately timezone-naive value for rejection tests."""
    return datetime.fromisoformat("2026-01-01T00:00:00")


def test_domain_model_serializes_json_values() -> None:
    """Pydantic JSON mode serializes dates, datetimes, and enums by default."""
    from datetime import date

    from stock_selector.models import Board, Exchange, Instrument

    instrument = Instrument(
        symbol="600519.SH",
        name="贵州茅台",
        exchange=Exchange.SSE,
        board=Board.SH_MAIN,
        listing_date=date(2001, 8, 27),
    )
    dumped = instrument.model_dump(mode="json")
    assert dumped["exchange"] == "SH"
    assert dumped["listing_date"] == "2001-08-27"
