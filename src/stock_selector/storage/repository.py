"""Passive selective repository built on Parquet source files and DuckDB views."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from stock_selector.config.paths import AppPaths
from stock_selector.models import DailyBar, Instrument, RealtimeQuote
from stock_selector.models.common import validate_symbol
from stock_selector.storage.duckdb_catalog import DuckDBCatalog
from stock_selector.storage.errors import StorageDataError, StorageIOError
from stock_selector.storage.parquet_store import ParquetStore


@dataclass(frozen=True)
class StorageStats:
    """A compact description of intentionally persisted local coverage."""

    instrument_rows: int
    daily_bar_rows: int
    daily_symbols: int
    realtime_quote_rows: int
    realtime_symbols: int
    realtime_snapshots: int
    latest_realtime_at: datetime | None
    disk_usage_bytes: int


class LocalMarketRepository:
    """Persist only explicit domain batches; never fetches or selects market data."""

    def __init__(self, paths: AppPaths) -> None:
        """Store collaborators without creating directories, files, or databases."""
        self.paths = paths
        self._parquet = ParquetStore(paths)
        self._catalog = DuckDBCatalog(paths)
        self._initialized = False

    @property
    def catalog_path(self) -> Path:
        """Expose the local catalog file path for offline status reporting."""
        return self._catalog.database_path

    def initialize(self) -> None:
        """Explicitly create storage directories and the DuckDB catalog."""
        try:
            for directory in (
                self._parquet.instruments_dir,
                self._parquet.daily_bars_dir,
                self._parquet.realtime_quotes_dir,
                self.paths.metadata_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageIOError("failed to initialize storage directories") from exc
        self._catalog.initialize()
        self._initialized = True

    def save_instruments(self, instruments: tuple[Instrument, ...]) -> None:
        """Replace the complete lightweight instrument master with sorted data."""
        self._require_initialized()
        if not instruments:
            raise StorageDataError("instrument master must not be empty")
        _require_unique_symbols(instruments, "instrument master")
        self._parquet.write_instruments(tuple(sorted(instruments, key=lambda item: item.symbol)))
        self._catalog.refresh_views()

    def load_instruments(self) -> tuple[Instrument, ...]:
        """Load the full lightweight instrument master in canonical order."""
        self._require_initialized()
        instruments = self._parquet.read_instruments()
        _require_unique_symbols(instruments, "persisted instrument master")
        return tuple(sorted(instruments, key=lambda item: item.symbol))

    def upsert_daily_bars(self, bars: tuple[DailyBar, ...]) -> None:
        """Merge one explicit symbol's finite daily window, with incoming dates winning."""
        self._require_initialized()
        if not bars:
            return
        symbols = {bar.symbol for bar in bars}
        if len(symbols) != 1:
            raise StorageDataError("daily-bar upsert requires exactly one symbol")
        dates = [bar.trade_date for bar in bars]
        if len(set(dates)) != len(dates):
            raise StorageDataError("daily-bar input contains duplicate trade dates")
        symbol = bars[0].symbol
        existing = self._parquet.read_daily_bars(symbol)
        if any(bar.symbol != symbol for bar in existing):
            raise StorageDataError("persisted daily-bar file contains mixed symbols")
        merged = {bar.trade_date: bar for bar in existing}
        merged.update({bar.trade_date: bar for bar in bars})
        ordered = tuple(merged[day] for day in sorted(merged))
        self._parquet.write_daily_bars(symbol, ordered)
        self._catalog.refresh_views()

    def load_daily_bars(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[DailyBar, ...]:
        """Load one finite symbol window, optionally clipped by an inclusive date range."""
        self._require_initialized()
        _validate_storage_symbol(symbol)
        if start_date is not None and end_date is not None and end_date < start_date:
            raise StorageDataError("end_date must not precede start_date")
        bars = self._parquet.read_daily_bars(symbol)
        if any(bar.symbol != symbol for bar in bars):
            raise StorageDataError("persisted daily-bar file contains mixed symbols")
        return tuple(
            bar
            for bar in sorted(bars, key=lambda item: item.trade_date)
            if (start_date is None or bar.trade_date >= start_date)
            and (end_date is None or bar.trade_date <= end_date)
        )

    def save_realtime_snapshot(self, quotes: tuple[RealtimeQuote, ...]) -> Path:
        """Save one caller-selected, internally consistent realtime snapshot."""
        self._require_initialized()
        if not quotes:
            raise StorageDataError("realtime snapshot must not be empty")
        _require_unique_symbols(quotes, "realtime snapshot")
        if len({quote.ingested_at for quote in quotes}) != 1:
            raise StorageDataError("realtime snapshot must use one ingested_at instant")
        if len({quote.source for quote in quotes}) != 1:
            raise StorageDataError("realtime snapshot must use one source")
        path = self._parquet.write_realtime_snapshot(
            tuple(sorted(quotes, key=lambda item: item.symbol))
        )
        self._catalog.refresh_views()
        return path

    def load_latest_realtime_snapshot(self) -> tuple[RealtimeQuote, ...]:
        """Load the snapshot with the greatest stored ingested_at value, not newest mtime."""
        self._require_initialized()
        *_, latest_at = self._catalog.counts()
        if latest_at is None:
            return ()
        quotes = self._parquet.read_realtime_snapshot(latest_at)
        return tuple(sorted(quotes, key=lambda item: item.symbol))

    def get_stats(self) -> StorageStats:
        """Report actual selected coverage and storage bytes without scanning project caches."""
        self._require_initialized()
        daily_rows, daily_symbols, realtime_rows, realtime_symbols, snapshots, latest_at = (
            self._catalog.counts()
        )
        return StorageStats(
            instrument_rows=len(self.load_instruments()),
            daily_bar_rows=daily_rows,
            daily_symbols=daily_symbols,
            realtime_quote_rows=realtime_rows,
            realtime_symbols=realtime_symbols,
            realtime_snapshots=snapshots,
            latest_realtime_at=latest_at,
            disk_usage_bytes=self._disk_usage_bytes(),
        )

    def _disk_usage_bytes(self) -> int:
        """Count processed Parquet files plus the catalog database only."""
        try:
            processed_bytes = sum(
                path.stat().st_size
                for path in self.paths.processed_data_dir.rglob("*")
                if path.is_file()
            )
            catalog_bytes = self.catalog_path.stat().st_size if self.catalog_path.exists() else 0
            return processed_bytes + catalog_bytes
        except OSError as exc:
            raise StorageIOError("failed to calculate storage disk usage") from exc

    def _require_initialized(self) -> None:
        """Make local filesystem creation an explicit caller action."""
        if not self._initialized:
            raise StorageIOError("repository.initialize() must be called before storage access")


def _validate_storage_symbol(symbol: str) -> None:
    """Translate shared canonical-symbol validation into a storage data error."""
    try:
        validate_symbol(symbol)
    except ValueError as exc:
        raise StorageDataError("invalid canonical symbol") from exc


def _require_unique_symbols(
    records: tuple[Instrument, ...] | tuple[RealtimeQuote, ...], operation: str
) -> None:
    """Reject duplicate primary keys before a snapshot becomes durable."""
    symbols = [record.symbol for record in records]
    if len(set(symbols)) != len(symbols):
        raise StorageDataError(f"{operation} contains duplicate symbols")
