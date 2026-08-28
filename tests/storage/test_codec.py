"""Round-trip tests for strict Arrow codecs."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pyarrow as pa
import pytest

from stock_selector.models import Board, DailyBar, Exchange, Instrument, RealtimeQuote
from stock_selector.storage.codec import (
    daily_bars_to_table,
    instruments_to_table,
    realtime_quotes_to_table,
    table_to_daily_bars,
    table_to_instruments,
    table_to_realtime_quotes,
)
from stock_selector.storage.errors import StorageDataError
from stock_selector.storage.schemas import REALTIME_QUOTE_SCHEMA


def _instrument(symbol: str = "600519.SH") -> Instrument:
    return Instrument(
        symbol=symbol,
        name="贵州茅台",
        exchange=Exchange.SSE,
        board=Board.SH_MAIN,
        listing_date=date(2001, 8, 27),
    )


def _daily_bar(day: int = 3, close: float = 10.0) -> DailyBar:
    return DailyBar(
        symbol="600519.SH",
        trade_date=date(2026, 8, day),
        open=9.0,
        high=11.0,
        low=8.0,
        close=close,
        volume=100.0,
        amount=1_000.0,
        source="test",
    )


def _quote() -> RealtimeQuote:
    return RealtimeQuote(
        symbol="600519.SH",
        price=10.0,
        open=None,
        high=11.0,
        low=9.0,
        prev_close=None,
        volume=None,
        amount=None,
        change_pct=None,
        turnover_rate=None,
        volume_ratio=None,
        source_timestamp=None,
        ingested_at=datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        source="test",
    )


def test_instrument_round_trip_preserves_enums_and_dates() -> None:
    """Instrument Arrow rows use enum values and reconstruct validated models."""
    instrument = _instrument()
    assert table_to_instruments(instruments_to_table((instrument,))) == (instrument,)


def test_daily_bar_round_trip_preserves_domain_values() -> None:
    """Daily rows retain date32 data and validated OHLCV values."""
    bar = _daily_bar()
    assert table_to_daily_bars(daily_bars_to_table((bar,))) == (bar,)


def test_realtime_round_trip_preserves_utc_instant_and_nulls() -> None:
    """Aware instants become UTC while nullable quote fields stay null."""
    quote = _quote()
    restored = table_to_realtime_quotes(realtime_quotes_to_table((quote,)))[0]
    assert restored.ingested_at.isoformat() == "2026-08-28T08:00:00+00:00"
    assert restored.ingested_at == quote.ingested_at
    assert restored.open is None
    assert restored.source_timestamp is None


def test_illegal_arrow_data_is_revalidated_as_storage_data_error() -> None:
    """A schema-compatible but invalid persisted price cannot bypass Pydantic validation."""
    invalid = pa.Table.from_pylist(
        [
            {
                "symbol": "600519.SH",
                "price": 0.0,
                "open": None,
                "high": None,
                "low": None,
                "prev_close": None,
                "volume": None,
                "amount": None,
                "change_pct": None,
                "turnover_rate": None,
                "volume_ratio": None,
                "source_timestamp": None,
                "ingested_at": datetime(2026, 8, 28, tzinfo=ZoneInfo("UTC")),
                "source": "test",
            }
        ],
        schema=REALTIME_QUOTE_SCHEMA,
    )
    with pytest.raises(StorageDataError):
        table_to_realtime_quotes(invalid)
