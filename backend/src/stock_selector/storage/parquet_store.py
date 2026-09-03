"""Atomic, schema-bound Parquet persistence without provider knowledge."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from stock_selector.config.paths import AppPaths
from stock_selector.models import (
    AdjustedDailyReturn,
    DailyBar,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.risk.models import DatedRiskState
from stock_selector.storage import codec
from stock_selector.storage.errors import StorageIOError

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class ParquetStore:
    """Read and atomically replace narrow Parquet datasets at known paths."""

    def __init__(self, paths: AppPaths) -> None:
        """Keep path references only; construction intentionally has no side effects."""
        self._paths = paths

    @property
    def instruments_dir(self) -> Path:
        """Return the instrument master directory."""
        return self._paths.processed_data_dir / "instruments"

    @property
    def daily_bars_dir(self) -> Path:
        """Return the selective per-symbol daily-bar directory."""
        return self._paths.processed_data_dir / "daily_bars"

    @property
    def adjusted_returns_dir(self) -> Path:
        """Return the separate per-symbol HFQ return-evidence directory."""
        return self._paths.processed_data_dir / "adjusted_returns"

    @property
    def realtime_quotes_dir(self) -> Path:
        """Return the partitioned selective realtime snapshot directory."""
        return self._paths.processed_data_dir / "realtime_quotes"

    @property
    def risk_states_dir(self) -> Path:
        """Return the business-date-partitioned dated-risk state directory."""
        return self._paths.processed_data_dir / "risk_states"

    @property
    def financials_dir(self) -> Path:
        """Return point-in-time financial history directory."""
        return self._paths.processed_data_dir / "fundamentals"

    @property
    def valuations_dir(self) -> Path:
        """Return per-symbol daily valuation history directory."""
        return self._paths.processed_data_dir / "valuations"

    @property
    def industries_dir(self) -> Path:
        """Return per-symbol industry effective-interval directory."""
        return self._paths.processed_data_dir / "industries"

    @property
    def instruments_path(self) -> Path:
        """Return the sole full-market lightweight instrument snapshot path."""
        return self.instruments_dir / "instruments.parquet"

    def daily_bars_path(self, symbol: str) -> Path:
        """Return the one-file-per-symbol daily path after prior symbol validation."""
        return self.daily_bars_dir / f"{symbol}.parquet"

    def adjusted_returns_path(self, symbol: str) -> Path:
        return self.adjusted_returns_dir / f"{symbol}.parquet"

    def realtime_snapshot_path(self, ingested_at: datetime) -> Path:
        """Return a Shanghai-date partition and Windows-safe UTC timestamp filename."""
        local_date = ingested_at.astimezone(_SHANGHAI).date().isoformat()
        utc_stamp = ingested_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return self.realtime_quotes_dir / f"date={local_date}" / f"snapshot_{utc_stamp}.parquet"

    def risk_states_path(self, as_of: date) -> Path:
        """Return one deterministic source-of-truth path for an exact business date."""
        return self.risk_states_dir / f"date={as_of.isoformat()}" / "risk_states.parquet"

    def financials_path(self, symbol: str) -> Path:
        return self.financials_dir / f"{symbol}.parquet"

    def valuations_path(self, symbol: str) -> Path:
        return self.valuations_dir / f"{symbol}.parquet"

    def industries_path(self, symbol: str) -> Path:
        return self.industries_dir / f"{symbol}.parquet"

    def write_instruments(self, instruments: tuple[Instrument, ...]) -> None:
        """Atomically replace the complete instrument master snapshot."""
        self._write_table(codec.instruments_to_table(instruments), self.instruments_path)

    def read_instruments(self) -> tuple[Instrument, ...]:
        """Read the instrument snapshot or return an empty batch when absent."""
        if not self.instruments_path.exists():
            return ()
        return codec.table_to_instruments(self._read_table(self.instruments_path))

    def write_daily_bars(self, symbol: str, bars: tuple[DailyBar, ...]) -> None:
        """Atomically replace one symbol's finite daily-bar window."""
        self._write_table(codec.daily_bars_to_table(bars), self.daily_bars_path(symbol))

    def read_daily_bars(self, symbol: str) -> tuple[DailyBar, ...]:
        """Read one persisted symbol window without consulting any provider."""
        path = self.daily_bars_path(symbol)
        if not path.exists():
            return ()
        return codec.table_to_daily_bars(self._read_table(path))

    def write_adjusted_daily_returns(
        self, symbol: str, records: tuple[AdjustedDailyReturn, ...]
    ) -> None:
        self._write_table(
            codec.adjusted_daily_returns_to_table(records), self.adjusted_returns_path(symbol)
        )

    def read_adjusted_daily_returns(self, symbol: str) -> tuple[AdjustedDailyReturn, ...]:
        path = self.adjusted_returns_path(symbol)
        return () if not path.exists() else codec.table_to_adjusted_daily_returns(self._read_table(path))

    def write_realtime_snapshot(self, quotes: tuple[RealtimeQuote, ...]) -> Path:
        """Atomically save one selected snapshot at its deterministic timestamp path."""
        path = self.realtime_snapshot_path(quotes[0].ingested_at)
        self._write_table(codec.realtime_quotes_to_table(quotes), path)
        return path

    def read_realtime_snapshot(self, ingested_at: datetime) -> tuple[RealtimeQuote, ...]:
        """Read the deterministic snapshot for one ingestion instant, if present."""
        path = self.realtime_snapshot_path(ingested_at)
        if not path.exists():
            return ()
        return codec.table_to_realtime_quotes(self._read_table(path))

    def write_risk_states(self, states: tuple[DatedRiskState, ...]) -> None:
        """Atomically replace one exact-date risk dataset."""
        self._write_table(codec.risk_states_to_table(states), self.risk_states_path(states[0].as_of))

    def read_risk_states(self, as_of: date) -> tuple[DatedRiskState, ...]:
        """Read only the requested business-date dataset; never fall back in time."""
        path = self.risk_states_path(as_of)
        if not path.exists():
            return ()
        return codec.table_to_risk_states(self._read_table(path))

    def write_financial_records(self, symbol: str, records: tuple[FinancialRecord, ...]) -> None:
        self._write_table(codec.financial_records_to_table(records), self.financials_path(symbol))

    def read_financial_records(self, symbol: str) -> tuple[FinancialRecord, ...]:
        path = self.financials_path(symbol)
        return () if not path.exists() else codec.table_to_financial_records(self._read_table(path))

    def write_valuation_records(self, symbol: str, records: tuple[ValuationRecord, ...]) -> None:
        self._write_table(codec.valuation_records_to_table(records), self.valuations_path(symbol))

    def read_valuation_records(self, symbol: str) -> tuple[ValuationRecord, ...]:
        path = self.valuations_path(symbol)
        return () if not path.exists() else codec.table_to_valuation_records(self._read_table(path))

    def write_industry_records(self, symbol: str, records: tuple[IndustryRecord, ...]) -> None:
        self._write_table(codec.industry_records_to_table(records), self.industries_path(symbol))

    def read_industry_records(self, symbol: str) -> tuple[IndustryRecord, ...]:
        path = self.industries_path(symbol)
        return () if not path.exists() else codec.table_to_industry_records(self._read_table(path))

    def _read_table(self, path: Path) -> pa.Table:
        """Read Parquet bytes while preserving data-decoding errors for the codec."""
        try:
            return pq.ParquetFile(path).read()  # type: ignore[no-untyped-call]
        except (OSError, pa.ArrowException) as exc:
            raise StorageIOError(f"failed to read Parquet file: {path}") from exc

    def _write_table(self, table: pa.Table, path: Path) -> None:
        """Write a temporary sibling then atomically replace the target file."""
        temporary_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, temporary_path)  # type: ignore[no-untyped-call]
            os.replace(temporary_path, path)
        except (OSError, pa.ArrowException) as exc:
            raise StorageIOError(f"failed to write Parquet file: {path}") from exc
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
