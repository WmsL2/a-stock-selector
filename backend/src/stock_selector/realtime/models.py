from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from stock_selector.models import RealtimeQuote
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.quality.models import RealtimeFreshness


class RealtimeCaptureScope(StrEnum):
    ALL_MARKET = "all_market"
    EXPLICIT_SYMBOLS = "explicit_symbols"


class RealtimeCaptureRequest(DomainModel):
    symbols: tuple[str, ...] | None = None
    persist_symbols: tuple[str, ...] = ()

    @field_validator("symbols")
    @classmethod
    def requested_symbols_valid(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("explicit symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("symbols must be unique")
        return tuple(sorted(value))

    @field_validator("persist_symbols")
    @classmethod
    def persist_symbols_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("persist symbols must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def persist_symbols_must_be_explicitly_requested(
        self,
    ) -> "RealtimeCaptureRequest":
        """Reject an explicit request that tries to persist an unrequested symbol."""
        if self.symbols is not None and not set(self.persist_symbols).issubset(
            self.symbols
        ):
            raise ValueError("persist symbols must be included in explicit symbols")
        return self


class RealtimeCaptureResult(DomainModel):
    scope: RealtimeCaptureScope
    requested_symbols: tuple[str, ...] | None
    received_quotes: int = Field(ge=0)
    received_symbols: tuple[str, ...]
    source: str
    ingested_at: datetime
    source_timestamp_available_quotes: int = Field(ge=0)
    persist_requested_symbols: tuple[str, ...]
    persisted_quotes: int = Field(ge=0)
    persisted_symbols: tuple[str, ...]
    persistence_performed: bool
    quotes: tuple[RealtimeQuote, ...]

    @field_validator("ingested_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "ingested_at")


class RealtimeMarketStatus(DomainModel):
    calculation_at: datetime
    latest_ingested_at: datetime | None
    source: str | None
    stored_quotes: int = Field(ge=0)
    source_timestamp_available_quotes: int = Field(ge=0)
    freshness: RealtimeFreshness
    age_seconds: float | None
    ranking_allowed: bool
    normal_max_seconds: int
    warning_max_seconds: int
    snapshot_scope: str = "selective_persisted"

    @field_validator("calculation_at", "latest_ingested_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_aware_datetime(value, "timestamp")
