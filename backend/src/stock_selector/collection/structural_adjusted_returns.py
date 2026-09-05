"""Bounded current-structural refresh orchestration for HFQ return evidence."""

from datetime import date, datetime

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.storage import LocalMarketRepository

from .adjusted_returns import AdjustedDailyReturnCollector
from .errors import CollectionDataError
from .models import (
    AdjustedReturnCollectionReport,
    AdjustedReturnCollectionRequest,
    AdjustedReturnCollectionStatus,
    AdjustedReturnSymbolResult,
)


class StructuralAdjustedReturnCollectionRequest(DomainModel):
    """One finite, selected current structural batch of HFQ-return collection."""

    symbols: tuple[str, ...]
    as_of: datetime
    start_date: date
    end_date: date
    has_more_structural_members: bool

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 20:
            raise ValueError("symbols must contain between 1 and 20 entries")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("symbols must be canonical, unique, and sorted")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_window(self) -> "StructuralAdjustedReturnCollectionRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if self.end_date > self.as_of.date() or self.end_date != self.as_of.date():
            raise ValueError("end_date must equal as_of date")
        if (self.end_date - self.start_date).days + 1 > 180:
            raise ValueError("requested range must not exceed 180 calendar days")
        return self


class StructuralAdjustedReturnCollectionReport(DomainModel):
    """Audit report for one sequential structural adjusted-return batch."""

    as_of: datetime
    availability_as_of: datetime
    start_date: date
    end_date: date
    requested_symbols: tuple[str, ...]
    success_symbols: int = Field(ge=0)
    empty_symbols: int = Field(ge=0)
    failed_symbols: int = Field(ge=0)
    rows_received: int = Field(ge=0)
    rows_persisted: int = Field(ge=0)
    adjusted_return_available_after_run: int = Field(ge=0)
    results: tuple[AdjustedReturnSymbolResult, ...]
    batch_first_symbol: str
    batch_last_symbol: str
    has_more_structural_members: bool
    next_start_after: str | None = None

    @field_validator("as_of", "availability_as_of")
    @classmethod
    def validate_timestamp(cls, value: datetime, info: ValidationInfo) -> datetime:
        return ensure_aware_datetime(value, info.field_name)

    @field_validator("requested_symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("requested_symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("requested_symbols must be canonical, unique, and sorted")
        return value

    @field_validator("batch_first_symbol", "batch_last_symbol", "next_start_after")
    @classmethod
    def validate_optional_symbol(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_report(self) -> "StructuralAdjustedReturnCollectionReport":
        if self.end_date < self.start_date or self.end_date > self.as_of.date():
            raise ValueError("report date range must be valid for as_of")
        observed_at = tuple(
            item.observed_at for item in self.results if item.observed_at is not None
        )
        expected_availability_as_of = max((self.as_of, *observed_at))
        if self.availability_as_of != expected_availability_as_of:
            raise ValueError("availability_as_of must match the deterministic result cutoff")
        if tuple(item.symbol for item in self.results) != self.requested_symbols:
            raise ValueError("results must retain requested symbol order")
        expected = len(self.requested_symbols)
        if self.success_symbols + self.empty_symbols + self.failed_symbols != expected:
            raise ValueError("outcome counts must equal requested symbols")
        for status, count in (
            (AdjustedReturnCollectionStatus.SUCCESS, self.success_symbols),
            (AdjustedReturnCollectionStatus.EMPTY, self.empty_symbols),
            (AdjustedReturnCollectionStatus.FAILED, self.failed_symbols),
        ):
            if count != sum(item.status is status for item in self.results):
                raise ValueError("outcome count must match results")
        if self.rows_received != sum(item.rows_received for item in self.results):
            raise ValueError("received rows must match results")
        if self.rows_persisted != sum(item.rows_persisted for item in self.results):
            raise ValueError("persisted rows must match results")
        if self.adjusted_return_available_after_run > expected:
            raise ValueError("availability cannot exceed requested symbols")
        if (self.batch_first_symbol, self.batch_last_symbol) != (
            self.requested_symbols[0], self.requested_symbols[-1]
        ):
            raise ValueError("batch boundary symbols must match requested symbols")
        if self.has_more_structural_members:
            if self.next_start_after != self.batch_last_symbol:
                raise ValueError("next cursor must be the batch last symbol")
        elif self.next_start_after is not None:
            raise ValueError("completed structural batch cannot expose a next cursor")
        return self


class StructuralAdjustedReturnCollector:
    """Wrap the existing batch collector and audit only local PIT-visible evidence."""

    def __init__(
        self,
        adjusted_return_collector: AdjustedDailyReturnCollector,
        repository: LocalMarketRepository,
    ) -> None:
        self._adjusted_return_collector = adjusted_return_collector
        self._repository = repository

    def collect(
        self, request: StructuralAdjustedReturnCollectionRequest
    ) -> StructuralAdjustedReturnCollectionReport:
        base = self._adjusted_return_collector.collect(
            AdjustedReturnCollectionRequest(
                symbols=request.symbols,
                start_date=request.start_date,
                end_date=request.end_date,
            )
        )
        _validate_base_report(base, request)
        availability_as_of = max(
            (request.as_of, *(item.observed_at for item in base.results if item.observed_at is not None))
        )
        available = sum(
            bool(
                self._repository.load_latest_adjusted_daily_returns_as_of(
                    symbol, availability_as_of
                )
            )
            for symbol in request.symbols
        )
        return StructuralAdjustedReturnCollectionReport(
            as_of=request.as_of,
            availability_as_of=availability_as_of,
            start_date=request.start_date,
            end_date=request.end_date,
            requested_symbols=request.symbols,
            success_symbols=base.success_symbols,
            empty_symbols=base.empty_symbols,
            failed_symbols=base.failed_symbols,
            rows_received=base.rows_received,
            rows_persisted=base.rows_persisted,
            adjusted_return_available_after_run=available,
            results=base.results,
            batch_first_symbol=request.symbols[0],
            batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=(request.symbols[-1] if request.has_more_structural_members else None),
        )


def _validate_base_report(
    report: AdjustedReturnCollectionReport,
    request: StructuralAdjustedReturnCollectionRequest,
) -> None:
    if (
        report.requested_symbols != request.symbols
        or report.start_date != request.start_date
        or report.end_date != request.end_date
    ):
        raise CollectionDataError("adjusted-return collector returned mismatched batch metadata")
