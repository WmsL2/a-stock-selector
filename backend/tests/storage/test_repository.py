"""Realtime snapshot and architecture-boundary tests for the repository."""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config.paths import AppPaths
from stock_selector.models import AdjustedDailyReturn, AdjustmentType, RealtimeQuote
from stock_selector.storage import LocalMarketRepository, StorageDataError


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _quote(
    symbol: str = "600519.SH",
    at: datetime | None = None,
    source: str = "test",
) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=10.0,
        ingested_at=at or datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        source=source,
    )


def test_realtime_snapshots_are_selected_sorted_and_latest_by_ingested_at(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Latest selection depends on stored instants, not mutable filesystem timestamps."""
    repository = _repository(tmp_path)
    assert repository.load_latest_realtime_snapshot() == ()
    old_at = datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    new_at = old_at + timedelta(minutes=1)
    old_path = repository.save_realtime_snapshot((_quote("600519.SH", old_at),))
    repository.save_realtime_snapshot(
        (_quote("600519.SH", new_at), _quote("000001.SZ", new_at))
    )
    os.utime(old_path, (new_at.timestamp() + 60, new_at.timestamp() + 60))
    latest = repository.load_latest_realtime_snapshot()
    assert [quote.symbol for quote in latest] == ["000001.SZ", "600519.SH"]
    assert {quote.ingested_at for quote in latest} == {new_at}


def test_realtime_snapshot_rejects_inconsistent_batches_and_replaces_same_timestamp(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Snapshot key, source, and ingestion time remain batch-wide invariants."""
    repository = _repository(tmp_path)
    at = datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    with pytest.raises(StorageDataError):
        repository.save_realtime_snapshot(())
    with pytest.raises(StorageDataError):
        repository.save_realtime_snapshot((_quote("600519.SH", at), _quote("600519.SH", at)))
    with pytest.raises(StorageDataError):
        repository.save_realtime_snapshot((_quote("600519.SH", at), _quote("000001.SZ", at + timedelta(seconds=1))))
    with pytest.raises(StorageDataError):
        repository.save_realtime_snapshot((_quote("600519.SH", at), _quote("000001.SZ", at, "other")))
    path = repository.save_realtime_snapshot((_quote("600519.SH", at),))
    replacement = _quote("600519.SH", at).model_copy(update={"price": 11.0})
    assert repository.save_realtime_snapshot((replacement,)) == path
    assert repository.load_latest_realtime_snapshot() == (replacement,)


def test_storage_package_never_imports_network_or_ui_clients() -> None:
    """Storage remains a passive local boundary without provider/network/UI imports."""
    storage_root = Path(__file__).parents[2] / "src" / "stock_selector" / "storage"
    forbidden = ("import akshare", "import requests", "import streamlit", "import plotly")
    for path in storage_root.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden), path


def test_adjusted_returns_are_revision_safe_and_pit_selected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    at = datetime(2026, 8, 30, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original = AdjustedDailyReturn(
        symbol="600519.SH", trade_date=date(2026, 8, 28), previous_trade_date=date(2026, 8, 27),
        return_fraction=0.01, adjustment=AdjustmentType.HFQ, observed_at=at, source="test"
    )
    revision = original.model_copy(update={"return_fraction": 0.02, "observed_at": at + timedelta(days=1)})
    repository.upsert_adjusted_daily_returns((original, revision))
    assert repository.load_latest_adjusted_daily_returns_as_of("600519.SH", at) == (original,)
    assert repository.load_latest_adjusted_daily_returns_as_of("600519.SH", at + timedelta(days=1)) == (revision,)
    assert repository.get_adjusted_return_stats().rows == 2


def test_adjusted_return_pit_blocks_future_backfill_and_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    observed = datetime(2026, 9, 3, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    historical = AdjustedDailyReturn(
        symbol="600519.SH", trade_date=date(2025, 1, 2), previous_trade_date=date(2025, 1, 1),
        return_fraction=0.01, adjustment=AdjustmentType.HFQ, observed_at=observed, source="test"
    )
    repository.upsert_adjusted_daily_returns((historical,))
    repository.upsert_adjusted_daily_returns((historical,))
    assert repository.load_latest_adjusted_daily_returns_as_of("600519.SH", datetime(2025, 1, 3, 16, tzinfo=ZoneInfo("Asia/Shanghai"))) == ()
    assert len(repository.load_adjusted_daily_returns("600519.SH")) == 1
