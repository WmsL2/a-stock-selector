"""Immutable requests and auditable outcomes for bounded daily collection."""

from datetime import date, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models import AdjustmentType
from stock_selector.models.common import (
    DomainModel,
    ensure_nonempty_string,
    validate_symbol,
)


class DailyCollectionRequest(DomainModel):
    """An explicit finite, RAW-only collection request with no implicit universe."""

    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    adjustment: AdjustmentType = AdjustmentType.RAW

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("symbols must not contain duplicates")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_request(self) -> "DailyCollectionRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if self.adjustment is not AdjustmentType.RAW:
            raise ValueError("daily collection currently supports RAW adjustment only")
        return self


class DailyCollectionStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


class AdjustedReturnCollectionRequest(DomainModel):
    """Explicit bounded request for separate HFQ daily-return evidence."""

    symbols: tuple[str, ...]
    start_date: date
    end_date: date

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 20:
            raise ValueError("symbols must contain between 1 and 20 entries")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("symbols must not contain duplicates")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_request(self) -> "AdjustedReturnCollectionRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if (self.end_date - self.start_date).days + 1 > 180:
            raise ValueError("requested range must not exceed 180 calendar days")
        return self


class AdjustedReturnCollectionStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


class AdjustedReturnSymbolResult(DomainModel):
    symbol: str
    status: AdjustedReturnCollectionStatus
    rows_received: int = Field(ge=0)
    rows_persisted: int = Field(ge=0)
    source: str | None = None
    observed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, value: str) -> str:
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_outcome(self) -> "AdjustedReturnSymbolResult":
        if self.status is AdjustedReturnCollectionStatus.SUCCESS:
            if not self.rows_received or self.rows_persisted != self.rows_received:
                raise ValueError("success must persist every received row")
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("success cannot contain errors")
        elif self.status is AdjustedReturnCollectionStatus.EMPTY:
            if self.rows_received or self.rows_persisted or self.error_type or self.error_message:
                raise ValueError("empty cannot contain rows or errors")
        elif self.rows_received or self.rows_persisted or self.error_type is None:
            raise ValueError("failed requires error type and no persisted rows")
        return self


class AdjustedReturnCollectionReport(DomainModel):
    requested_symbols: tuple[str, ...]
    start_date: date
    end_date: date
    success_symbols: int = Field(ge=0)
    empty_symbols: int = Field(ge=0)
    failed_symbols: int = Field(ge=0)
    rows_received: int = Field(ge=0)
    rows_persisted: int = Field(ge=0)
    results: tuple[AdjustedReturnSymbolResult, ...]

    @model_validator(mode="after")
    def validate_report(self) -> "AdjustedReturnCollectionReport":
        if tuple(item.symbol for item in self.results) != self.requested_symbols:
            raise ValueError("results must preserve requested symbol order")
        if self.success_symbols != sum(item.status is AdjustedReturnCollectionStatus.SUCCESS for item in self.results):
            raise ValueError("success count must match results")
        if self.empty_symbols != sum(item.status is AdjustedReturnCollectionStatus.EMPTY for item in self.results):
            raise ValueError("empty count must match results")
        if self.failed_symbols != sum(item.status is AdjustedReturnCollectionStatus.FAILED for item in self.results):
            raise ValueError("failure count must match results")
        if self.rows_received != sum(item.rows_received for item in self.results):
            raise ValueError("received rows must match results")
        if self.rows_persisted != sum(item.rows_persisted for item in self.results):
            raise ValueError("persisted rows must match results")
        return self


class DailySymbolCollectionResult(DomainModel):
    """One safe, compact result for a requested symbol."""

    symbol: str
    status: DailyCollectionStatus
    requested_start_date: date
    requested_end_date: date
    rows_received: int = Field(ge=0)
    rows_persisted: int = Field(ge=0)
    source: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("source", "error_type", "error_message")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return None if value is None else ensure_nonempty_string(value, "result text")

    @model_validator(mode="after")
    def validate_outcome(self) -> "DailySymbolCollectionResult":
        if self.requested_end_date < self.requested_start_date:
            raise ValueError("requested end date must not precede start date")
        if self.status is DailyCollectionStatus.SUCCESS:
            if not self.rows_received or self.rows_persisted != self.rows_received:
                raise ValueError("successful result must persist every received row")
            if self.source is None or self.error_type is not None or self.error_message is not None:
                raise ValueError("successful result requires source and no error details")
        elif self.status is DailyCollectionStatus.EMPTY:
            if self.rows_received or self.rows_persisted or self.source is not None:
                raise ValueError("empty result must not contain rows or source")
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("empty result must not contain error details")
        elif self.rows_persisted or self.source is not None:
            raise ValueError("failed result must not persist rows or claim a source")
        if self.status is DailyCollectionStatus.FAILED and (
            self.error_type is None or self.error_message is None
        ):
            raise ValueError("failed result requires concise error details")
        return self


class DailyCollectionReport(DomainModel):
    """Deterministic summary for every explicit symbol in one bounded run."""

    start_date: date
    end_date: date
    adjustment: AdjustmentType
    requested_symbols: tuple[str, ...]
    succeeded_symbols: int = Field(ge=0)
    empty_symbols: int = Field(ge=0)
    failed_symbols: int = Field(ge=0)
    total_rows_received: int = Field(ge=0)
    results: tuple[DailySymbolCollectionResult, ...]

    @model_validator(mode="after")
    def validate_report(self) -> "DailyCollectionReport":
        if self.end_date < self.start_date:
            raise ValueError("report end date must not precede start date")
        if self.adjustment is not AdjustmentType.RAW:
            raise ValueError("daily collection report adjustment must be RAW")
        if not self.requested_symbols or self.requested_symbols != tuple(sorted(self.requested_symbols)):
            raise ValueError("requested symbols must be nonempty and sorted")
        if len(set(self.requested_symbols)) != len(self.requested_symbols):
            raise ValueError("requested symbols must be unique")
        if tuple(result.symbol for result in self.results) != self.requested_symbols:
            raise ValueError("results must contain every requested symbol in order")
        if self.succeeded_symbols != sum(
            result.status is DailyCollectionStatus.SUCCESS for result in self.results
        ):
            raise ValueError("success count must match results")
        if self.empty_symbols != sum(
            result.status is DailyCollectionStatus.EMPTY for result in self.results
        ):
            raise ValueError("empty count must match results")
        if self.failed_symbols != sum(
            result.status is DailyCollectionStatus.FAILED for result in self.results
        ):
            raise ValueError("failure count must match results")
        if self.total_rows_received != sum(result.rows_received for result in self.results):
            raise ValueError("received row count must match results")
        return self
