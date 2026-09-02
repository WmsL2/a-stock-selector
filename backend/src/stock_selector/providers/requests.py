"""Immutable, validated request models for provider capabilities."""

from datetime import date, datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models import AdjustmentType
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)


def _validate_symbols(symbols: tuple[str, ...], *, allow_empty: bool) -> tuple[str, ...]:
    """Require a unique batch of canonical symbols with explicit empty semantics."""
    if not allow_empty and not symbols:
        raise ValueError("symbols must not be empty")
    for symbol in symbols:
        validate_symbol(symbol)
    if len(set(symbols)) != len(symbols):
        raise ValueError("symbols must not contain duplicates")
    return symbols


class DailyBarsRequest(DomainModel):
    """Request one symbol's daily bars over an inclusive date range."""

    symbol: str
    start_date: date
    end_date: date
    adjustment: AdjustmentType = AdjustmentType.RAW

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the canonical internal symbol format."""
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_date_range(self) -> "DailyBarsRequest":
        """Require the requested end date to follow or equal the start date."""
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class MinuteBarsRequest(DomainModel):
    """Request one symbol's timezone-aware minute bars over a time range."""

    symbol: str
    start_at: datetime
    end_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the canonical internal symbol format."""
        return validate_symbol(value)

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_aware_timestamp(
        cls, value: datetime, info: ValidationInfo
    ) -> datetime:
        """Require explicit timezones for minute-bar boundaries."""
        return ensure_aware_datetime(value, info.field_name)

    @model_validator(mode="after")
    def validate_time_range(self) -> "MinuteBarsRequest":
        """Require the requested end time to follow or equal the start time."""
        if self.end_at < self.start_at:
            raise ValueError("end_at must not precede start_at")
        return self


class RealtimeQuotesRequest(DomainModel):
    """Request all supported quotes or one explicit unique symbol batch."""

    symbols: tuple[str, ...] | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbol_batch(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        """Keep all-market ``None`` distinct from an invalid empty tuple."""
        if value is None:
            return None
        return _validate_symbols(value, allow_empty=False)


class CurrentRiskStatesRequest(DomainModel):
    """Request one current-date complete risk batch for structural symbols only."""

    symbols: tuple[str, ...]
    as_of: date

    @field_validator("symbols")
    @classmethod
    def validate_symbol_batch(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_validate_symbols(value, allow_empty=False)))


class FinancialRecordsRequest(DomainModel):
    """Request financial records for one or more symbols and optional periods."""

    symbols: tuple[str, ...]
    start_period: date | None = None
    end_period: date | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbol_batch(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a nonempty unique canonical symbol batch."""
        return _validate_symbols(value, allow_empty=False)

    @model_validator(mode="after")
    def validate_period_range(self) -> "FinancialRecordsRequest":
        """Require ordered periods whenever both endpoints are supplied."""
        if (
            self.start_period is not None
            and self.end_period is not None
            and self.end_period < self.start_period
        ):
            raise ValueError("end_period must not precede start_period")
        return self


class ValuationRecordsRequest(DomainModel):
    """Request valuation records for a nonempty symbol batch at an optional time."""

    symbols: tuple[str, ...]
    as_of: datetime | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbol_batch(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a nonempty unique canonical symbol batch."""
        return _validate_symbols(value, allow_empty=False)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        """Require an explicit timezone whenever an as-of timestamp is supplied."""
        if value is None:
            return None
        return ensure_aware_datetime(value, "as_of")


class IndustryRecordsRequest(DomainModel):
    """Request current or historical industry records for a symbol batch."""

    symbols: tuple[str, ...]
    as_of: date | None = None

    @field_validator("symbols")
    @classmethod
    def validate_symbol_batch(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a nonempty unique canonical symbol batch."""
        return _validate_symbols(value, allow_empty=False)
