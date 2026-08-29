"""Point-in-time storage tests for fundamentals, valuation, and industry domains."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config.paths import AppPaths
from stock_selector.models import FinancialRecord, IndustryRecord, ValuationRecord
from stock_selector.storage import LocalMarketRepository, StorageDataError

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _financial(available_at: datetime, revenue: float) -> FinancialRecord:
    return FinancialRecord(
        symbol="600519.SH",
        report_period=date(2025, 12, 31),
        announcement_date=date(2026, 3, 25),
        available_at=available_at,
        revenue=revenue,
        source="test",
    )


def test_financial_pit_preserves_restatements(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    first = _financial(datetime(2026, 3, 25, 15, 30, tzinfo=_SHANGHAI), 100.0)
    revision = _financial(datetime(2026, 4, 10, 15, 30, tzinfo=_SHANGHAI), 110.0)
    repository.upsert_financial_records((first, revision))
    assert repository.load_latest_financials_as_of(
        "600519.SH", datetime(2026, 3, 25, 16, 0, tzinfo=_SHANGHAI)
    ) == (first,)
    assert repository.load_latest_financials_as_of(
        "600519.SH", datetime(2026, 4, 15, 16, 0, tzinfo=_SHANGHAI)
    ) == (revision,)
    assert not repository.load_latest_financials_as_of(
        "600519.SH", datetime(2026, 3, 25, 10, 0, tzinfo=_SHANGHAI)
    )


def test_valuation_never_falls_forward(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    first = ValuationRecord(
        symbol="600519.SH",
        as_of=datetime(2026, 1, 2, 15, 30, tzinfo=_SHANGHAI),
        pe=-8.0,
        source="test",
    )
    future = ValuationRecord(
        symbol="600519.SH",
        as_of=datetime(2026, 1, 5, 15, 30, tzinfo=_SHANGHAI),
        pe=10.0,
        source="test",
    )
    repository.upsert_valuation_records((first, future))
    assert (
        repository.load_latest_valuation_as_of(
            "600519.SH", datetime(2026, 1, 3, 16, 0, tzinfo=_SHANGHAI)
        )
        == first
    )


def test_industry_intervals_are_inclusive_and_non_overlapping(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    first = IndustryRecord(
        symbol="600519.SH",
        industry_code="A",
        industry_name="A",
        classification="CNInfo",
        effective_from=date(2020, 1, 1),
        effective_to=date(2024, 6, 30),
        source="test",
    )
    second = IndustryRecord(
        symbol="600519.SH",
        industry_code="B",
        industry_name="B",
        classification="CNInfo",
        effective_from=date(2024, 7, 1),
        source="test",
    )
    repository.upsert_industry_records((first, second))
    assert repository.load_industry_records("600519.SH", as_of=date(2024, 6, 30)) == (
        first,
    )
    assert repository.load_industry_records("600519.SH", as_of=date(2024, 7, 1)) == (
        second,
    )
    overlapping = IndustryRecord(
        symbol="600519.SH",
        industry_code="C",
        industry_name="C",
        classification="CNInfo",
        effective_from=date(2024, 6, 1),
        source="test",
    )
    with pytest.raises(StorageDataError):
        repository.upsert_industry_records((overlapping,))
