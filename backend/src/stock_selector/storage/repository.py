"""Passive selective repository built on Parquet source files and DuckDB views."""

from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

from stock_selector.config.paths import AppPaths
from stock_selector.models import (
    DailyBar,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.models.common import validate_symbol
from stock_selector.risk.models import DatedRiskState
from stock_selector.storage.duckdb_catalog import DuckDBCatalog
from stock_selector.storage.errors import StorageDataError, StorageIOError
from stock_selector.storage.parquet_store import ParquetStore


@dataclass(frozen=True)
class StorageStats:
    """A compact description of intentionally persisted local coverage."""

    instrument_rows: int
    daily_bar_rows: int
    daily_symbols: int
    earliest_daily_trade_date: date | None
    latest_daily_trade_date: date | None
    realtime_quote_rows: int
    realtime_symbols: int
    realtime_snapshots: int
    latest_realtime_at: datetime | None
    risk_state_rows: int
    risk_state_dates: int
    latest_risk_state_date: date | None
    financial_rows: int
    financial_symbols: int
    latest_financial_available_at: datetime | None
    valuation_rows: int
    valuation_symbols: int
    latest_valuation_at: datetime | None
    industry_rows: int
    industry_symbols: int
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
                self._parquet.risk_states_dir,
                self._parquet.financials_dir,
                self._parquet.valuations_dir,
                self._parquet.industries_dir,
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
        if len({bar.adjustment for bar in bars}) != 1:
            raise StorageDataError("daily-bar upsert requires one adjustment basis")
        dates = [bar.trade_date for bar in bars]
        if len(set(dates)) != len(dates):
            raise StorageDataError("daily-bar input contains duplicate trade dates")
        symbol = bars[0].symbol
        existing = self._parquet.read_daily_bars(symbol)
        if any(bar.symbol != symbol for bar in existing):
            raise StorageDataError("persisted daily-bar file contains mixed symbols")
        if existing and existing[0].adjustment != bars[0].adjustment:
            raise StorageDataError("daily-bar adjustment must match existing persisted data")
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
        if len({bar.adjustment for bar in bars}) > 1:
            raise StorageDataError("persisted daily-bar file contains mixed adjustments")
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
        (
            _daily_rows,
            _daily_symbols,
            _earliest_daily,
            _latest_daily,
            _realtime_rows,
            _realtime_symbols,
            _snapshots,
            latest_at,
            _risk_rows,
            _risk_dates,
            _latest_risk_date,
        ) = self._catalog.counts()
        if latest_at is None:
            return ()
        quotes = self._parquet.read_realtime_snapshot(latest_at)
        return tuple(sorted(quotes, key=lambda item: item.symbol))

    def upsert_risk_states(self, states: tuple[DatedRiskState, ...]) -> None:
        """Merge one exact-date risk batch, with incoming records explicitly winning."""
        self._require_initialized()
        if not states:
            return
        as_of_values = {state.as_of for state in states}
        if len(as_of_values) != 1:
            raise StorageDataError("risk-state upsert requires exactly one as_of date")
        _require_unique_risk_symbols(states, "risk-state upsert")
        as_of = states[0].as_of
        existing = self._parquet.read_risk_states(as_of)
        if any(state.as_of != as_of for state in existing):
            raise StorageDataError("persisted risk-state file contains mixed as_of dates")
        _require_unique_risk_symbols(existing, "persisted risk states")
        merged = {state.symbol: state for state in existing}
        merged.update({state.symbol: state for state in states})
        self._parquet.write_risk_states(tuple(merged[symbol] for symbol in sorted(merged)))
        self._catalog.refresh_views()

    def load_risk_states(
        self, as_of: date, symbols: tuple[str, ...] | None = None
    ) -> tuple[DatedRiskState, ...]:
        """Load only one exact-date dated-risk dataset, optionally by canonical symbols."""
        self._require_initialized()
        states = self._parquet.read_risk_states(as_of)
        if any(state.as_of != as_of for state in states):
            raise StorageDataError("persisted risk-state file contains mixed as_of dates")
        _require_unique_risk_symbols(states, "persisted risk states")
        if symbols is not None:
            for symbol in symbols:
                _validate_storage_symbol(symbol)
            if len(set(symbols)) != len(symbols):
                raise StorageDataError("risk-state symbol filter contains duplicates")
            wanted = set(symbols)
            states = tuple(state for state in states if state.symbol in wanted)
        return tuple(sorted(states, key=lambda item: item.symbol))

    def upsert_financial_records(self, records: tuple[FinancialRecord, ...]) -> None:
        """Merge one symbol's revision-safe financial records by full PIT key."""
        self._require_initialized()
        if not records:
            return
        _require_one_symbol(records, "financial-record upsert")
        _require_unique_financial_keys(records, "financial-record input")
        symbol = records[0].symbol
        existing = self._parquet.read_financial_records(symbol)
        _require_one_symbol(existing, "persisted financial records", allow_empty=True)
        _require_unique_financial_keys(existing, "persisted financial records")
        merged = {
            (item.report_period, item.available_at): item
            for item in existing
        }
        merged.update({(item.report_period, item.available_at): item for item in records})
        ordered = tuple(
            sorted(merged.values(), key=lambda item: (item.report_period, item.available_at))
        )
        self._parquet.write_financial_records(symbol, ordered)
        self._catalog.refresh_views()

    def load_financial_records(
        self, symbol: str, *, available_at_or_before: datetime | None = None
    ) -> tuple[FinancialRecord, ...]:
        """Load all known revisions visible no later than an explicit instant."""
        self._require_initialized()
        _validate_storage_symbol(symbol)
        records = self._parquet.read_financial_records(symbol)
        _require_one_symbol(records, "persisted financial records", allow_empty=True)
        _require_unique_financial_keys(records, "persisted financial records")
        return tuple(
            item
            for item in sorted(records, key=lambda value: (value.report_period, value.available_at))
            if available_at_or_before is None or item.available_at <= available_at_or_before
        )

    def load_latest_financials_as_of(
        self, symbol: str, available_at_or_before: datetime
    ) -> tuple[FinancialRecord, ...]:
        """Select the newest visible revision for each report period at one PIT instant."""
        visible = self.load_financial_records(
            symbol, available_at_or_before=available_at_or_before
        )
        latest_by_period: dict[date, FinancialRecord] = {}
        for item in visible:
            previous = latest_by_period.get(item.report_period)
            if previous is None or item.available_at > previous.available_at:
                latest_by_period[item.report_period] = item
        return tuple(latest_by_period[period] for period in sorted(latest_by_period))

    def upsert_valuation_records(self, records: tuple[ValuationRecord, ...]) -> None:
        """Merge one symbol's dated valuation observations; incoming exact instants win."""
        self._require_initialized()
        if not records:
            return
        _require_one_symbol(records, "valuation-record upsert")
        _require_unique_valuation_keys(records, "valuation-record input")
        symbol = records[0].symbol
        existing = self._parquet.read_valuation_records(symbol)
        _require_one_symbol(existing, "persisted valuation records", allow_empty=True)
        _require_unique_valuation_keys(existing, "persisted valuation records")
        merged = {item.as_of: item for item in existing}
        merged.update({item.as_of: item for item in records})
        self._parquet.write_valuation_records(
            symbol, tuple(sorted(merged.values(), key=lambda item: item.as_of))
        )
        self._catalog.refresh_views()

    def load_valuation_records(
        self, symbol: str, *, as_of_or_before: datetime | None = None
    ) -> tuple[ValuationRecord, ...]:
        """Load only valuation observations no later than the requested instant."""
        self._require_initialized()
        _validate_storage_symbol(symbol)
        records = self._parquet.read_valuation_records(symbol)
        _require_one_symbol(records, "persisted valuation records", allow_empty=True)
        _require_unique_valuation_keys(records, "persisted valuation records")
        return tuple(
            item
            for item in sorted(records, key=lambda value: value.as_of)
            if as_of_or_before is None or item.as_of <= as_of_or_before
        )

    def load_latest_valuation_as_of(
        self, symbol: str, as_of_or_before: datetime
    ) -> ValuationRecord | None:
        """Return the latest available valuation at-or-before a requested instant."""
        records = self.load_valuation_records(symbol, as_of_or_before=as_of_or_before)
        return records[-1] if records else None

    def load_factor_input_symbols(self) -> tuple[str, ...]:
        """Return deterministic local symbols with industry plus financial or valuation data."""
        self._require_initialized()
        financials = _symbols_from_parquet_directory(self._parquet.financials_dir)
        valuations = _symbols_from_parquet_directory(self._parquet.valuations_dir)
        industries = _symbols_from_parquet_directory(self._parquet.industries_dir)
        return tuple(sorted(industries & (financials | valuations)))

    def upsert_industry_records(self, records: tuple[IndustryRecord, ...]) -> None:
        """Merge one symbol's reliable industry intervals without overlap ambiguity."""
        self._require_initialized()
        if not records:
            return
        _require_one_symbol(records, "industry-record upsert")
        _require_unique_industry_keys(records, "industry-record input")
        symbol = records[0].symbol
        existing = self._parquet.read_industry_records(symbol)
        _require_one_symbol(existing, "persisted industry records", allow_empty=True)
        _require_unique_industry_keys(existing, "persisted industry records")
        merged = {
            (item.classification, item.effective_from): item
            for item in existing
        }
        merged.update({(item.classification, item.effective_from): item for item in records})
        ordered = tuple(sorted(merged.values(), key=lambda item: (item.classification, item.effective_from)))
        _require_non_overlapping_industry_intervals(ordered)
        self._parquet.write_industry_records(symbol, ordered)
        self._catalog.refresh_views()

    def load_industry_records(
        self, symbol: str, *, as_of: date | None = None
    ) -> tuple[IndustryRecord, ...]:
        """Read exact industry intervals, optionally retaining only those covering a date."""
        self._require_initialized()
        _validate_storage_symbol(symbol)
        records = self._parquet.read_industry_records(symbol)
        _require_one_symbol(records, "persisted industry records", allow_empty=True)
        _require_unique_industry_keys(records, "persisted industry records")
        _require_non_overlapping_industry_intervals(records)
        ordered = tuple(sorted(records, key=lambda item: (item.classification, item.effective_from)))
        if as_of is None:
            return ordered
        return tuple(
            item
            for item in ordered
            if item.effective_from <= as_of
            and (item.effective_to is None or as_of <= item.effective_to)
        )

    def get_stats(self) -> StorageStats:
        """Report actual selected coverage and storage bytes without scanning project caches."""
        self._require_initialized()
        (
            daily_rows,
            daily_symbols,
            earliest_daily,
            latest_daily,
            realtime_rows,
            realtime_symbols,
            snapshots,
            latest_at,
            risk_rows,
            risk_dates,
            latest_risk_date,
        ) = self._catalog.counts()
        (
            financial_rows,
            financial_symbols,
            latest_financial_available_at,
            valuation_rows,
            valuation_symbols,
            latest_valuation_at,
            industry_rows,
            industry_symbols,
        ) = self._catalog.fundamental_counts()
        return StorageStats(
            instrument_rows=len(self.load_instruments()),
            daily_bar_rows=daily_rows,
            daily_symbols=daily_symbols,
            earliest_daily_trade_date=earliest_daily,
            latest_daily_trade_date=latest_daily,
            realtime_quote_rows=realtime_rows,
            realtime_symbols=realtime_symbols,
            realtime_snapshots=snapshots,
            latest_realtime_at=latest_at,
            risk_state_rows=risk_rows,
            risk_state_dates=risk_dates,
            latest_risk_state_date=latest_risk_date,
            financial_rows=financial_rows,
            financial_symbols=financial_symbols,
            latest_financial_available_at=latest_financial_available_at,
            valuation_rows=valuation_rows,
            valuation_symbols=valuation_symbols,
            latest_valuation_at=latest_valuation_at,
            industry_rows=industry_rows,
            industry_symbols=industry_symbols,
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


def _symbols_from_parquet_directory(directory: Path) -> set[str]:
    try:
        symbols = {path.stem for path in directory.glob("*.parquet")}
    except OSError as exc:
        raise StorageIOError("failed to inspect local factor-input coverage") from exc
    for symbol in symbols:
        _validate_storage_symbol(symbol)
    return symbols


def _require_unique_symbols(
    records: tuple[Instrument, ...] | tuple[RealtimeQuote, ...], operation: str
) -> None:
    """Reject duplicate primary keys before a snapshot becomes durable."""
    symbols = [record.symbol for record in records]
    if len(set(symbols)) != len(symbols):
        raise StorageDataError(f"{operation} contains duplicate symbols")


def _require_unique_risk_symbols(
    records: tuple[DatedRiskState, ...], operation: str
) -> None:
    if len({record.symbol for record in records}) != len(records):
        raise StorageDataError(f"{operation} contains duplicate symbols")


def _require_one_symbol(
    records: tuple[FinancialRecord, ...] | tuple[ValuationRecord, ...] | tuple[IndustryRecord, ...],
    operation: str,
    *,
    allow_empty: bool = False,
) -> None:
    if not records:
        if allow_empty:
            return
        raise StorageDataError(f"{operation} must not be empty")
    if len({item.symbol for item in records}) != 1:
        raise StorageDataError(f"{operation} requires exactly one symbol")


def _require_unique_financial_keys(records: tuple[FinancialRecord, ...], operation: str) -> None:
    if len({(item.report_period, item.available_at) for item in records}) != len(records):
        raise StorageDataError(f"{operation} contains duplicate logical keys")


def _require_unique_valuation_keys(records: tuple[ValuationRecord, ...], operation: str) -> None:
    if len({item.as_of for item in records}) != len(records):
        raise StorageDataError(f"{operation} contains duplicate logical keys")


def _require_unique_industry_keys(records: tuple[IndustryRecord, ...], operation: str) -> None:
    if len({(item.classification, item.effective_from) for item in records}) != len(records):
        raise StorageDataError(f"{operation} contains duplicate logical keys")


def _require_non_overlapping_industry_intervals(records: tuple[IndustryRecord, ...]) -> None:
    by_classification: dict[str, list[IndustryRecord]] = {}
    for item in records:
        by_classification.setdefault(item.classification, []).append(item)
    for classification_records in by_classification.values():
        ordered = sorted(classification_records, key=lambda item: item.effective_from)
        for previous, current in pairwise(ordered):
            if previous.effective_to is None or current.effective_from <= previous.effective_to:
                raise StorageDataError("industry intervals must not overlap within a classification")
