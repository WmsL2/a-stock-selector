"""Repository tests for instrument snapshots and selective daily persistence."""

from datetime import date

import pytest

from stock_selector.config.paths import AppPaths
from stock_selector.models import AdjustmentType, Board, DailyBar, Exchange, Instrument
from stock_selector.storage import (
    LocalMarketRepository,
    StorageDataError,
    StorageIOError,
)


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    paths = AppPaths.from_project_root(tmp_path)
    repository = LocalMarketRepository(paths)
    assert not paths.processed_data_dir.exists()
    assert not paths.metadata_dir.exists()
    repository.initialize()
    return repository


def _instrument(symbol: str, name: str, exchange: Exchange, board: Board) -> Instrument:
    return Instrument(
        symbol=symbol,
        name=name,
        exchange=exchange,
        board=board,
        listing_date=date(2020, 1, 1),
    )


def _bar(day: int, close: float = 10.0) -> DailyBar:
    return DailyBar(
        symbol="600519.SH",
        trade_date=date(2026, 8, day),
        adjustment=AdjustmentType.RAW,
        open=9.0,
        high=max(11.0, close),
        low=8.0,
        close=close,
        volume=100.0,
        amount=1_000.0,
        source="test",
    )


def test_instruments_initially_empty_then_sorted_replaced_and_atomic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Instrument master is explicit, sorted, replace-only, and leaves no temp files."""
    repository = _repository(tmp_path)
    assert repository.load_instruments() == ()
    instruments = (
        _instrument("600519.SH", "贵州茅台", Exchange.SSE, Board.SH_MAIN),
        _instrument("000001.SZ", "平安银行", Exchange.SZSE, Board.SZ_MAIN),
    )
    repository.save_instruments(instruments)
    assert [item.symbol for item in repository.load_instruments()] == ["000001.SZ", "600519.SH"]
    repository.save_instruments((instruments[0],))
    assert repository.load_instruments() == (instruments[0],)
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.partial"))


def test_instrument_snapshot_rejects_empty_and_duplicate_symbols(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Empty and duplicate master snapshots are storage data errors."""
    repository = _repository(tmp_path)
    item = _instrument("600519.SH", "贵州茅台", Exchange.SSE, Board.SH_MAIN)
    with pytest.raises(StorageDataError):
        repository.save_instruments(())
    with pytest.raises(StorageDataError):
        repository.save_instruments((item, item))


def test_daily_persistence_is_single_symbol_upsert_with_filters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Incoming overlap wins and only its explicitly named daily file is created."""
    repository = _repository(tmp_path)
    assert repository.load_daily_bars("600519.SH") == ()
    repository.upsert_daily_bars((_bar(4, 10.0), _bar(3, 9.0)))
    repository.upsert_daily_bars((_bar(5, 12.0), _bar(4, 11.0)))
    loaded = repository.load_daily_bars("600519.SH")
    assert [(bar.trade_date.day, bar.close) for bar in loaded] == [(3, 9.0), (4, 11.0), (5, 12.0)]
    assert repository.load_daily_bars(
        "600519.SH", date(2026, 8, 4), date(2026, 8, 4)
    ) == (_bar(4, 11.0),)
    daily_files = list(
        (tmp_path / "runtime" / "data" / "processed" / "daily_bars").glob("*.parquet")
    )
    assert [path.name for path in daily_files] == ["600519.SH.parquet"]


def test_daily_persistence_rejects_invalid_batches_and_noops_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Mixed symbols, duplicate dates, and inverted ranges cannot be silently persisted."""
    repository = _repository(tmp_path)
    repository.upsert_daily_bars(())
    other = _bar(3).model_copy(update={"symbol": "000001.SZ"})
    with pytest.raises(StorageDataError):
        repository.upsert_daily_bars((_bar(3), other))
    with pytest.raises(StorageDataError):
        repository.upsert_daily_bars((_bar(3), _bar(3, 11.0)))
    with pytest.raises(StorageDataError):
        repository.load_daily_bars("600519.SH", date(2026, 8, 5), date(2026, 8, 4))
    with pytest.raises(StorageDataError):
        repository.load_daily_bars("invalid")


def test_daily_persistence_rejects_mixed_adjustment_bases(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """One per-symbol daily file cannot silently mix RAW and QFQ prices."""
    repository = _repository(tmp_path)
    qfq = _bar(4).model_copy(update={"adjustment": AdjustmentType.QFQ})
    with pytest.raises(StorageDataError):
        repository.upsert_daily_bars((_bar(3), qfq))
    repository.upsert_daily_bars((_bar(3),))
    with pytest.raises(StorageDataError):
        repository.upsert_daily_bars((qfq,))


def test_storage_access_requires_explicit_initialization(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Constructing a repository neither initializes storage nor permits access."""
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    with pytest.raises(StorageIOError):
        repository.load_instruments()
