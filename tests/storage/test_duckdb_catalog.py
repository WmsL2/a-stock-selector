"""DuckDB external-view tests for the local Parquet catalog."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import duckdb

from stock_selector.config.paths import AppPaths
from stock_selector.models import (
    AdjustmentType,
    Board,
    DailyBar,
    Exchange,
    Instrument,
    RealtimeQuote,
)
from stock_selector.storage import LocalMarketRepository


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _instrument() -> Instrument:
    return Instrument(
        symbol="600519.SH",
        name="贵州茅台",
        exchange=Exchange.SSE,
        board=Board.SH_MAIN,
        listing_date=date(2001, 8, 27),
    )


def _bar() -> DailyBar:
    return DailyBar(
        symbol="600519.SH",
        trade_date=date(2026, 8, 3),
        adjustment=AdjustmentType.RAW,
        open=9.0,
        high=11.0,
        low=8.0,
        close=10.0,
        volume=100.0,
        amount=1_000.0,
        source="test",
    )


def _quote() -> RealtimeQuote:
    return RealtimeQuote(
        symbol="600519.SH",
        price=10.0,
        ingested_at=datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        source="test",
    )


def test_catalog_initializes_versioned_database_and_empty_views(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The catalog is created explicitly and empty views remain queryable."""
    repository = _repository(tmp_path)
    assert repository.catalog_path.exists()
    connection = duckdb.connect(str(repository.catalog_path))
    try:
        assert connection.execute("SELECT schema_version FROM storage_metadata").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM instruments").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM realtime_quotes").fetchone() == (0,)
    finally:
        connection.close()


def test_catalog_views_query_selective_parquet_and_stats(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """DuckDB sees only explicitly persisted files and reports their actual coverage."""
    repository = _repository(tmp_path)
    repository.save_instruments((_instrument(),))
    repository.upsert_daily_bars((_bar(),))
    repository.save_realtime_snapshot((_quote(),))
    connection = duckdb.connect(str(repository.catalog_path))
    try:
        assert connection.execute("SELECT COUNT(*) FROM instruments").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(DISTINCT symbol) FROM daily_bars").fetchone() == (1,)
        assert connection.execute("SELECT adjustment FROM daily_bars").fetchone() == ("raw",)
        assert connection.execute("SELECT COUNT(DISTINCT symbol) FROM realtime_quotes").fetchone() == (1,)
    finally:
        connection.close()
    stats = repository.get_stats()
    assert stats.daily_bar_rows == 1
    assert stats.daily_symbols == 1
    assert stats.realtime_quote_rows == 1
    assert stats.realtime_snapshots == 1
    assert stats.latest_realtime_at == _quote().ingested_at
    assert stats.disk_usage_bytes > 0
