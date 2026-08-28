"""Explicit PyArrow schemas for all persisted domain-model batches."""

import pyarrow as pa

INSTRUMENT_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("exchange", pa.string(), nullable=False),
        pa.field("board", pa.string(), nullable=False),
        pa.field("listing_date", pa.date32(), nullable=False),
        pa.field("delisting_date", pa.date32(), nullable=True),
        pa.field("status", pa.string(), nullable=False),
    ]
)

DAILY_BAR_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("trade_date", pa.date32(), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("volume", pa.float64(), nullable=False),
        pa.field("amount", pa.float64(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)

_UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")
REALTIME_QUOTE_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("open", pa.float64(), nullable=True),
        pa.field("high", pa.float64(), nullable=True),
        pa.field("low", pa.float64(), nullable=True),
        pa.field("prev_close", pa.float64(), nullable=True),
        pa.field("volume", pa.float64(), nullable=True),
        pa.field("amount", pa.float64(), nullable=True),
        pa.field("change_pct", pa.float64(), nullable=True),
        pa.field("turnover_rate", pa.float64(), nullable=True),
        pa.field("volume_ratio", pa.float64(), nullable=True),
        pa.field("source_timestamp", _UTC_TIMESTAMP, nullable=True),
        pa.field("ingested_at", _UTC_TIMESTAMP, nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)
