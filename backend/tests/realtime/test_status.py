from datetime import UTC, datetime, timedelta

import pytest

from stock_selector.config import Settings
from stock_selector.models import RealtimeQuote
from stock_selector.realtime import RealtimeDataError, RealtimeStatusService


@pytest.mark.parametrize(
    ("age", "freshness", "ranking_allowed"),
    [
        (60, "fresh", True),
        (61, "warning", True),
        (120, "warning", True),
        (121, "stale", False),
    ],
)
def test_status_evaluates_freshness_from_explicit_calculation_time(
    age: int, freshness: str, ranking_allowed: bool
) -> None:
    calculation_at = datetime(2026, 8, 30, 10, 5, tzinfo=UTC)
    status = RealtimeStatusService(
        FakeRepository((_quote(calculation_at - timedelta(seconds=age)),)), Settings()
    ).build(calculation_at)
    assert status.freshness.value == freshness
    assert status.age_seconds == age
    assert status.ranking_allowed is ranking_allowed
    assert status.snapshot_scope == "selective_persisted"


def test_status_reports_unavailable_without_fabricating_snapshot_metadata() -> None:
    status = RealtimeStatusService(FakeRepository(()), Settings()).build(
        datetime(2026, 8, 30, 10, tzinfo=UTC)
    )
    assert (status.freshness.value, status.latest_ingested_at, status.age_seconds) == (
        "unavailable",
        None,
        None,
    )
    assert not status.ranking_allowed


def test_status_rejects_future_ingestion() -> None:
    calculation_at = datetime(2026, 8, 30, 10, tzinfo=UTC)
    with pytest.raises(RealtimeDataError):
        RealtimeStatusService(
            FakeRepository((_quote(calculation_at + timedelta(seconds=1)),)), Settings()
        ).build(calculation_at)


class FakeRepository:
    def __init__(self, quotes: tuple[RealtimeQuote, ...]) -> None:
        self.quotes = quotes

    def load_latest_realtime_snapshot(self) -> tuple[RealtimeQuote, ...]:
        return self.quotes


def _quote(at: datetime) -> RealtimeQuote:
    return RealtimeQuote(
        symbol="600519.SH",
        price=10,
        ingested_at=at,
        source="fake:realtime",
    )
