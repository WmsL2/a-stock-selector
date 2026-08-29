"""Tests for market-data domain validation."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.models import AdjustmentType, DailyBar, MinuteBar, RealtimeQuote


def _aware_time() -> datetime:
    """Return a stable timezone-aware test timestamp."""
    return datetime(2026, 1, 2, 9, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


def _daily_bar(**changes: object) -> DailyBar:
    """Build a valid daily bar with selective numeric overrides."""
    values = {
        "symbol": "600519.SH",
        "trade_date": date(2026, 1, 2),
        "adjustment": AdjustmentType.RAW,
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "volume": 100.0,
        "amount": 1100.0,
        "source": "test",
    }
    values.update(changes)
    return DailyBar(**values)


def test_daily_bar_validates_ohlcv_ranges() -> None:
    """Daily bars accept valid OHLCV and reject invalid relationships."""
    assert _daily_bar().close == 11.0
    for changes in (
        {"high": 10.0},
        {"low": 11.0},
        {"open": 0.0},
        {"volume": -1.0},
        {"amount": -1.0},
        {"close": float("nan")},
    ):
        with pytest.raises(ValidationError):
            _daily_bar(**changes)


def test_daily_bar_requires_and_serializes_explicit_adjustment() -> None:
    """Persistent daily prices always carry a non-default adjustment basis."""
    values = _daily_bar().model_dump()
    values.pop("adjustment")
    with pytest.raises(ValidationError):
        DailyBar(**values)
    assert _daily_bar().model_dump(mode="json")["adjustment"] == "raw"


def test_minute_bar_requires_aware_time_and_valid_vwap() -> None:
    """Minute bars preserve timestamp and optional-VWAP semantics."""
    bar = MinuteBar(
        symbol="600519.SH",
        timestamp=_aware_time(),
        open=10,
        high=12,
        low=9,
        close=11,
        volume=100,
        amount=1100,
        vwap=10.5,
        source="test",
    )
    assert bar.vwap == 10.5
    invalid_cases = (
        (_naive_time(), 10.5),
        (_aware_time(), 0.0),
        (_aware_time(), float("nan")),
    )
    for timestamp, vwap in invalid_cases:
        with pytest.raises(ValidationError):
            MinuteBar(
                symbol="600519.SH",
                timestamp=timestamp,
                open=10,
                high=12,
                low=9,
                close=11,
                volume=100,
                amount=1100,
                vwap=vwap,
                source="test",
            )


def test_realtime_quote_validates_partial_snapshot_fields() -> None:
    """Quotes accept valid partial data and reject invalid domain values."""
    quote = RealtimeQuote(
        symbol="600519.SH",
        price=10,
        change_pct=-2.5,
        source_timestamp=None,
        ingested_at=_aware_time(),
        source="test",
    )
    assert quote.change_pct == -2.5
    for changes in (
        {"ingested_at": _naive_time()},
        {"source_timestamp": _naive_time()},
        {"price": 0.0},
        {"volume": -1.0},
        {"turnover_rate": -1.0},
        {"change_pct": float("nan")},
    ):
        values = {
            "symbol": "600519.SH",
            "price": 10.0,
            "ingested_at": _aware_time(),
            "source": "test",
        }
        values.update(changes)
        with pytest.raises(ValidationError):
            RealtimeQuote(**values)


def _naive_time() -> datetime:
    """Return a deliberately timezone-naive value for rejection tests."""
    return datetime.fromisoformat("2026-01-02T09:31:00")
