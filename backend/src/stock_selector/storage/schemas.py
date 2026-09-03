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
        pa.field("adjustment", pa.string(), nullable=False),
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
ADJUSTED_DAILY_RETURN_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("trade_date", pa.date32(), nullable=False),
        pa.field("previous_trade_date", pa.date32(), nullable=False),
        pa.field("return_fraction", pa.float64(), nullable=False),
        pa.field("adjustment", pa.string(), nullable=False),
        pa.field("observed_at", _UTC_TIMESTAMP, nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)
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

RISK_STATE_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("as_of", pa.date32(), nullable=False),
        pa.field("is_st", pa.bool_(), nullable=True),
        pa.field("is_suspended", pa.bool_(), nullable=True),
        pa.field("is_delisting_period", pa.bool_(), nullable=True),
        pa.field("observed_at", _UTC_TIMESTAMP, nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)

FINANCIAL_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("report_period", pa.date32(), nullable=False),
        pa.field("announcement_date", pa.date32(), nullable=False),
        pa.field("available_at", _UTC_TIMESTAMP, nullable=False),
        pa.field("roe", pa.float64(), nullable=True),
        pa.field("roa", pa.float64(), nullable=True),
        pa.field("gross_margin", pa.float64(), nullable=True),
        pa.field("net_margin", pa.float64(), nullable=True),
        pa.field("revenue", pa.float64(), nullable=True),
        pa.field("net_profit", pa.float64(), nullable=True),
        pa.field("deducted_net_profit", pa.float64(), nullable=True),
        pa.field("operating_cash_flow", pa.float64(), nullable=True),
        pa.field("total_assets", pa.float64(), nullable=True),
        pa.field("total_liabilities", pa.float64(), nullable=True),
        pa.field("source", pa.string(), nullable=False),
    ]
)

VALUATION_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("as_of", _UTC_TIMESTAMP, nullable=False),
        pa.field("pe", pa.float64(), nullable=True),
        pa.field("pb", pa.float64(), nullable=True),
        pa.field("ps", pa.float64(), nullable=True),
        pa.field("pcf", pa.float64(), nullable=True),
        pa.field("dividend_yield", pa.float64(), nullable=True),
        pa.field("total_market_cap", pa.float64(), nullable=True),
        pa.field("float_market_cap", pa.float64(), nullable=True),
        pa.field("source", pa.string(), nullable=False),
    ]
)

INDUSTRY_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("industry_code", pa.string(), nullable=False),
        pa.field("industry_name", pa.string(), nullable=False),
        pa.field("classification", pa.string(), nullable=False),
        pa.field("effective_from", pa.date32(), nullable=False),
        pa.field("effective_to", pa.date32(), nullable=True),
        pa.field("source", pa.string(), nullable=False),
    ]
)
