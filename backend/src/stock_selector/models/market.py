"""Canonical daily, minute, and real-time market data records."""

from datetime import date, datetime
from enum import Enum

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)


def _validate_ohlc(
    open_price: float, high: float, low: float, close: float
) -> None:
    """Validate the fundamental high-low relationships of a price bar."""
    if high < open_price or high < close or high < low:
        raise ValueError("high must not be below open, close, or low")
    if low > open_price or low > close or low > high:
        raise ValueError("low must not exceed open, close, or high")


class AdjustmentType(str, Enum):
    """Explicit price-adjustment basis for persisted historical market data."""

    RAW = "raw"
    QFQ = "qfq"
    HFQ = "hfq"


class DailyBar(DomainModel):
    """One end-of-day OHLCV record; volume uses shares and amount uses RMB."""

    symbol: str
    trade_date: date
    adjustment: AdjustmentType
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require a canonical internal symbol."""
        return validate_symbol(value)

    @field_validator("open", "high", "low", "close", "volume", "amount")
    @classmethod
    def validate_finite_values(cls, value: float, info: ValidationInfo) -> float:
        """Reject NaN and infinities in bar numeric fields."""
        finite_value = ensure_finite_float(value, info.field_name)
        assert finite_value is not None
        return finite_value

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Require provider provenance without provider-specific fields."""
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_market_values(self) -> "DailyBar":
        """Check bar ranges and relationships."""
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be greater than zero")
        if self.volume < 0 or self.amount < 0:
            raise ValueError("volume and amount must not be negative")
        _validate_ohlc(self.open, self.high, self.low, self.close)
        return self


class AdjustedDailyReturn(DomainModel):
    """One HFQ-derived daily return revision observed at a concrete provider instant."""

    symbol: str
    trade_date: date
    previous_trade_date: date
    return_fraction: float
    adjustment: AdjustmentType
    observed_at: datetime
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("return_fraction")
    @classmethod
    def validate_return_fraction(cls, value: float) -> float:
        finite = ensure_finite_float(value, "return_fraction")
        assert finite is not None
        if finite <= -1:
            raise ValueError("return_fraction must be greater than -1")
        return finite

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "observed_at")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_return_evidence(self) -> "AdjustedDailyReturn":
        if self.previous_trade_date >= self.trade_date:
            raise ValueError("previous_trade_date must precede trade_date")
        if self.adjustment is not AdjustmentType.HFQ:
            raise ValueError("adjusted daily returns require HFQ adjustment")
        return self


class MinuteBar(DomainModel):
    """One timezone-aware intraday OHLCV record."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    vwap: float | None = None
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require a canonical internal symbol."""
        return validate_symbol(value)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        """Require an explicit timestamp timezone."""
        return ensure_aware_datetime(value, "timestamp")

    @field_validator("open", "high", "low", "close", "volume", "amount", "vwap")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject non-finite intraday numbers."""
        return ensure_finite_float(value, info.field_name)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Require provider provenance."""
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_market_values(self) -> "MinuteBar":
        """Check minute-bar numeric ranges and OHLC relationships."""
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be greater than zero")
        if self.volume < 0 or self.amount < 0:
            raise ValueError("volume and amount must not be negative")
        if self.vwap is not None and self.vwap <= 0:
            raise ValueError("vwap must be greater than zero")
        _validate_ohlc(self.open, self.high, self.low, self.close)
        return self


class RealtimeQuote(DomainModel):
    """A timezone-aware, possibly partial real-time quote snapshot.

    ``change_pct`` and ``turnover_rate`` use percentage units (for example,
    ``3.25`` denotes 3.25%), rather than fractional units. Volume uses shares
    and amount uses RMB.
    """

    symbol: str
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    change_pct: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None
    source_timestamp: datetime | None = None
    ingested_at: datetime
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require a canonical internal symbol."""
        return validate_symbol(value)

    @field_validator(
        "price",
        "open",
        "high",
        "low",
        "prev_close",
        "volume",
        "amount",
        "change_pct",
        "turnover_rate",
        "volume_ratio",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject NaN and infinities in quote numerics."""
        return ensure_finite_float(value, info.field_name)

    @field_validator("source_timestamp", "ingested_at")
    @classmethod
    def validate_timestamps(
        cls, value: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        """Require timezones whenever a quote timestamp is present."""
        if value is None:
            return None
        return ensure_aware_datetime(value, info.field_name)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Require provider provenance."""
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_quote_values(self) -> "RealtimeQuote":
        """Check quote ranges while allowing incomplete intraday snapshots."""
        if self.price <= 0:
            raise ValueError("price must be greater than zero")
        for field_name in ("open", "high", "low", "prev_close"):
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                raise ValueError(f"{field_name} must be greater than zero")
        for field_name in ("volume", "amount", "turnover_rate", "volume_ratio"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high must not be below low")
        return self
