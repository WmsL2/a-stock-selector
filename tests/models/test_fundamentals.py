"""Tests for point-in-time financial and industry records."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.models import FinancialRecord, IndustryRecord, ValuationRecord


def _aware_time(day: int = 1) -> datetime:
    """Return an explicit Shanghai timestamp for availability tests."""
    return datetime(2026, 4, day, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def _financial_record(**changes: object) -> FinancialRecord:
    """Build a valid financial record with controllable values."""
    values: dict[str, object] = {
        "symbol": "600519.SH",
        "report_period": date(2026, 3, 31),
        "announcement_date": date(2026, 4, 1),
        "available_at": _aware_time(),
        "roe": 12.0,
        "net_profit": -1.0,
        "source": "test",
    }
    values.update(changes)
    return FinancialRecord(**values)


def test_financial_record_preserves_point_in_time_semantics() -> None:
    """Financial availability is timezone-aware and not before announcement."""
    assert _financial_record().net_profit == -1.0
    for changes in (
        {"announcement_date": date(2026, 3, 30)},
        {"available_at": _naive_datetime()},
        {"available_at": datetime(2026, 3, 31, 9, tzinfo=ZoneInfo("Asia/Shanghai"))},
        {"roe": float("nan")},
    ):
        with pytest.raises(ValidationError):
            _financial_record(**changes)


def test_valuation_record_retains_negative_multiples() -> None:
    """Negative PE remains valid while caps and dividend yield cannot be negative."""
    record = ValuationRecord(
        symbol="600519.SH",
        as_of=_aware_time(),
        pe=-5,
        total_market_cap=100,
        dividend_yield=3,
        source="test",
    )
    assert record.pe == -5
    invalid_cases = (
        {"total_market_cap": -1.0},
        {"dividend_yield": -0.1},
        {"as_of": _naive_datetime()},
    )
    for changes in invalid_cases:
        values = {
            "symbol": "600519.SH",
            "as_of": _aware_time(),
            "source": "test",
        }
        values.update(changes)
        with pytest.raises(ValidationError):
            ValuationRecord(**values)


def test_industry_record_preserves_history_ranges() -> None:
    """Historical intervals are allowed only when their dates are ordered."""
    record = IndustryRecord(
        symbol="600519.SH",
        industry_code="C15",
        industry_name="白酒",
        classification="CSRC",
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        source="test",
    )
    assert record.effective_to == date(2025, 12, 31)
    with pytest.raises(ValidationError):
        IndustryRecord(
            symbol="600519.SH",
            industry_code="C15",
            industry_name="白酒",
            classification="CSRC",
            effective_from=date(2020, 1, 2),
            effective_to=date(2020, 1, 1),
            source="test",
        )


def _naive_datetime() -> datetime:
    """Return a deliberately timezone-naive value for rejection tests."""
    return datetime.fromisoformat("2026-04-01T09:00:00")
