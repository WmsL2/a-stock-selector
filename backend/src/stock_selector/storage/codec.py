"""Validated conversion between domain models and explicit Arrow tables."""

from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
from pydantic import ValidationError

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
from stock_selector.storage.errors import StorageDataError
from stock_selector.storage.schemas import (
    ADJUSTED_DAILY_RETURN_SCHEMA,
    DAILY_BAR_SCHEMA,
    FINANCIAL_SCHEMA,
    INDUSTRY_SCHEMA,
    INSTRUMENT_SCHEMA,
    REALTIME_QUOTE_SCHEMA,
    RISK_STATE_SCHEMA,
    VALUATION_SCHEMA,
)


def adjusted_daily_returns_to_table(records: tuple[AdjustedDailyReturn, ...]) -> pa.Table:
    """Encode HFQ return evidence while retaining every observed revision."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "trade_date": item.trade_date,
                "previous_trade_date": item.previous_trade_date,
                "return_fraction": item.return_fraction,
                "adjustment": item.adjustment.value,
                "observed_at": _to_utc(item.observed_at),
                "source": item.source,
            }
            for item in records
        ],
        ADJUSTED_DAILY_RETURN_SCHEMA,
        "adjusted-daily-return encoding",
    )


def table_to_adjusted_daily_returns(table: pa.Table) -> tuple[AdjustedDailyReturn, ...]:
    """Decode persisted HFQ return evidence through the domain contract."""
    _require_schema(table, ADJUSTED_DAILY_RETURN_SCHEMA, "adjusted-daily-return decoding")
    try:
        return tuple(AdjustedDailyReturn(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("adjusted-daily-return domain reconstruction failed") from exc


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


def financial_records_to_table(records: tuple[FinancialRecord, ...]) -> pa.Table:
    """Encode announcement-aware financial records using UTC availability instants."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "report_period": item.report_period,
                "announcement_date": item.announcement_date,
                "available_at": _to_utc(item.available_at),
                "roe": item.roe,
                "roa": item.roa,
                "gross_margin": item.gross_margin,
                "net_margin": item.net_margin,
                "revenue": item.revenue,
                "net_profit": item.net_profit,
                "deducted_net_profit": item.deducted_net_profit,
                "operating_cash_flow": item.operating_cash_flow,
                "total_assets": item.total_assets,
                "total_liabilities": item.total_liabilities,
                "source": item.source,
            }
            for item in records
        ],
        FINANCIAL_SCHEMA,
        "financial-record encoding",
    )


def table_to_financial_records(table: pa.Table) -> tuple[FinancialRecord, ...]:
    """Decode financial records through the point-in-time domain model."""
    _require_schema(table, FINANCIAL_SCHEMA, "financial-record decoding")
    try:
        return tuple(FinancialRecord(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("financial-record domain reconstruction failed") from exc


def valuation_records_to_table(records: tuple[ValuationRecord, ...]) -> pa.Table:
    """Encode daily valuation observations using UTC market-close instants."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "as_of": _to_utc(item.as_of),
                "pe": item.pe,
                "pb": item.pb,
                "ps": item.ps,
                "pcf": item.pcf,
                "dividend_yield": item.dividend_yield,
                "total_market_cap": item.total_market_cap,
                "float_market_cap": item.float_market_cap,
                "source": item.source,
            }
            for item in records
        ],
        VALUATION_SCHEMA,
        "valuation-record encoding",
    )


def table_to_valuation_records(table: pa.Table) -> tuple[ValuationRecord, ...]:
    """Decode valuation records through the point-in-time domain model."""
    _require_schema(table, VALUATION_SCHEMA, "valuation-record decoding")
    try:
        return tuple(ValuationRecord(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("valuation-record domain reconstruction failed") from exc


def industry_records_to_table(records: tuple[IndustryRecord, ...]) -> pa.Table:
    """Encode exact industry effective intervals without manufacturing history."""
    return _table_from_rows(
        [
            {
                "symbol": item.symbol,
                "industry_code": item.industry_code,
                "industry_name": item.industry_name,
                "classification": item.classification,
                "effective_from": item.effective_from,
                "effective_to": item.effective_to,
                "source": item.source,
            }
            for item in records
        ],
        INDUSTRY_SCHEMA,
        "industry-record encoding",
    )


def table_to_industry_records(table: pa.Table) -> tuple[IndustryRecord, ...]:
    """Decode industry intervals through strict domain validation."""
    _require_schema(table, INDUSTRY_SCHEMA, "industry-record decoding")
    try:
        return tuple(IndustryRecord(**row) for row in table.to_pylist())
    except (TypeError, ValueError, ValidationError, pa.ArrowException) as exc:
        raise StorageDataError("industry-record domain reconstruction failed") from exc


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
