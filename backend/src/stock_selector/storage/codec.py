"""Validated conversion between domain models and explicit Arrow tables."""

from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
from pydantic import ValidationError

from stock_selector.models import DailyBar, Instrument, RealtimeQuote
from stock_selector.risk.models import DatedRiskState
from stock_selector.storage.errors import StorageDataError
from stock_selector.storage.schemas import (
    DAILY_BAR_SCHEMA,
    INSTRUMENT_SCHEMA,
    REALTIME_QUOTE_SCHEMA,
    RISK_STATE_SCHEMA,
)


def instruments_to_table(instruments: tuple[Instrument, ...]) -> pa.Table:
    """Encode instruments with their enum values and explicit Arrow schema."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "name": item.name,
                "exchange": item.exchange.value,
                "board": item.board.value,
                "listing_date": item.listing_date,
                "delisting_date": item.delisting_date,
                "status": item.status.value,
            }
            for item in instruments
        ],
        INSTRUMENT_SCHEMA,
        "instrument encoding",
    )


def table_to_instruments(table: pa.Table) -> tuple[Instrument, ...]:
    """Decode an instrument table through the domain model validators."""
    _require_schema(table, INSTRUMENT_SCHEMA, "instrument decoding")
    try:
        return tuple(Instrument(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("instrument domain reconstruction failed") from exc


def daily_bars_to_table(bars: tuple[DailyBar, ...]) -> pa.Table:
    """Encode daily bars using their stable date and numeric schema."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "trade_date": item.trade_date,
                "adjustment": item.adjustment.value,
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "volume": item.volume,
                "amount": item.amount,
                "source": item.source,
            }
            for item in bars
        ],
        DAILY_BAR_SCHEMA,
        "daily-bar encoding",
    )


def table_to_daily_bars(table: pa.Table) -> tuple[DailyBar, ...]:
    """Decode daily bars through the domain model validators."""
    _require_schema(table, DAILY_BAR_SCHEMA, "daily-bar decoding")
    try:
        return tuple(DailyBar(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("daily-bar domain reconstruction failed") from exc


def realtime_quotes_to_table(quotes: tuple[RealtimeQuote, ...]) -> pa.Table:
    """Encode real-time quotes, normalizing every instant to UTC."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "price": item.price,
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "prev_close": item.prev_close,
                "volume": item.volume,
                "amount": item.amount,
                "change_pct": item.change_pct,
                "turnover_rate": item.turnover_rate,
                "volume_ratio": item.volume_ratio,
                "source_timestamp": _to_utc(item.source_timestamp),
                "ingested_at": _to_utc(item.ingested_at),
                "source": item.source,
            }
            for item in quotes
        ],
        REALTIME_QUOTE_SCHEMA,
        "realtime-quote encoding",
    )


def table_to_realtime_quotes(table: pa.Table) -> tuple[RealtimeQuote, ...]:
    """Decode UTC Arrow instants through the domain model validators."""
    _require_schema(table, REALTIME_QUOTE_SCHEMA, "realtime-quote decoding")
    try:
        return tuple(RealtimeQuote(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("realtime-quote domain reconstruction failed") from exc


def risk_states_to_table(states: tuple[DatedRiskState, ...]) -> pa.Table:
    """Encode dated tri-state risk records, retaining unknown fields as null."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "as_of": item.as_of,
                "is_st": item.is_st,
                "is_suspended": item.is_suspended,
                "is_delisting_period": item.is_delisting_period,
                "observed_at": _to_utc(item.observed_at),
                "source": item.source,
            }
            for item in states
        ],
        RISK_STATE_SCHEMA,
        "risk-state encoding",
    )


def table_to_risk_states(table: pa.Table) -> tuple[DatedRiskState, ...]:
    """Decode dated risk records through strict domain validation."""
    _require_schema(table, RISK_STATE_SCHEMA, "risk-state decoding")
    try:
        return tuple(DatedRiskState(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("risk-state domain reconstruction failed") from exc


def _table_from_rows(rows: list[dict[str, Any]], schema: pa.Schema, operation: str) -> pa.Table:
    """Build a schema-bound Arrow table and turn conversion failures into data errors."""
    try:
        return pa.Table.from_pylist(rows, schema=schema)
    except (TypeError, ValueError, pa.ArrowException) as exc:
        raise StorageDataError(f"{operation} failed") from exc


def _require_schema(table: pa.Table, schema: pa.Schema, operation: str) -> None:
    """Reject missing, reordered, or mistyped columns despite Parquet nullability loss."""
    actual_fields = list(table.schema)
    expected_fields = list(schema)
    if len(actual_fields) != len(expected_fields) or any(
        actual.name != expected.name or actual.type != expected.type
        for actual, expected in zip(actual_fields, expected_fields, strict=True)
    ):
        raise StorageDataError(f"{operation} received an incompatible Arrow schema")


def _to_utc(value: datetime | None) -> datetime | None:
    """Convert an already validated aware instant to the storage timezone."""
    return None if value is None else value.astimezone(UTC)
