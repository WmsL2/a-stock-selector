"""Bounded sequential refresh of current structural valuation evidence."""

from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.storage import LocalMarketRepository

from .errors import CollectionDataError
from .fundamentals import FundamentalsCollectionReport, ValuationCollector


class StructuralValuationCollectionRequest(DomainModel):
    """One already-selected finite structural batch for valuation refresh."""

    symbols: tuple[str, ...]
    as_of: datetime
    has_more_structural_members: bool

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("symbols must be canonical, unique, and sorted")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")


class StructuralValuationStatus(str, Enum):
    """One valuation collector outcome for one requested structural member."""

    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


class StructuralValuationSymbolResult(DomainModel):
    """Compact valuation evidence outcome for one symbol."""

    symbol: str
    status: StructuralValuationStatus
    rows_persisted: int = Field(ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, value: str) -> str:
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_status_rows(self) -> "StructuralValuationSymbolResult":
        if self.status is StructuralValuationStatus.SUCCESS and self.rows_persisted == 0:
            raise ValueError("successful valuation outcome requires persisted rows")
        if self.status is not StructuralValuationStatus.SUCCESS and self.rows_persisted != 0:
            raise ValueError("empty or failed valuation outcome cannot persist rows")
        return self


class StructuralValuationCollectionReport(DomainModel):
    """Auditable result for a sequential current structural valuation batch."""

    as_of: datetime
    requested_symbols: tuple[str, ...]
    success_symbols: int = Field(ge=0)
    empty_symbols: int = Field(ge=0)
    failed_symbols: int = Field(ge=0)
    rows_persisted: int = Field(ge=0)
    valuation_available_after_run: int = Field(ge=0)
    results: tuple[StructuralValuationSymbolResult, ...]
    batch_first_symbol: str
    batch_last_symbol: str
    has_more_structural_members: bool
    next_start_after: str | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("requested_symbols")
    @classmethod
    def validate_requested_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
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
    def validate_report(self) -> "StructuralValuationCollectionReport":
        if tuple(result.symbol for result in self.results) != self.requested_symbols:
            raise ValueError("results must retain requested symbol order")
        expected = len(self.requested_symbols)
        if self.success_symbols + self.empty_symbols + self.failed_symbols != expected:
            raise ValueError("valuation outcome counts must equal requested symbols")
        if self.success_symbols != sum(
            result.status is StructuralValuationStatus.SUCCESS for result in self.results
        ):
            raise ValueError("valuation success count must match results")
        if self.empty_symbols != sum(
            result.status is StructuralValuationStatus.EMPTY for result in self.results
        ):
            raise ValueError("valuation empty count must match results")
        if self.failed_symbols != sum(
            result.status is StructuralValuationStatus.FAILED for result in self.results
        ):
            raise ValueError("valuation failed count must match results")
        if self.rows_persisted != sum(result.rows_persisted for result in self.results):
            raise ValueError("valuation rows must match results")
        if self.valuation_available_after_run > expected:
            raise ValueError("valuation availability cannot exceed requested symbols")
        if (
            self.batch_first_symbol != self.requested_symbols[0]
            or self.batch_last_symbol != self.requested_symbols[-1]
        ):
            raise ValueError("batch boundary symbols must match requested symbols")
        if self.has_more_structural_members:
            if self.next_start_after != self.batch_last_symbol:
                raise ValueError("next cursor must be the batch last symbol")
        elif self.next_start_after is not None:
            raise ValueError("completed structural batch cannot expose a next cursor")
        return self


class StructuralValuationCollector:
    """Run the existing valuation collector once per structural member in order."""

    def __init__(
        self, valuation_collector: ValuationCollector, repository: LocalMarketRepository
    ) -> None:
        self._valuation_collector = valuation_collector
        self._repository = repository

    def collect(
        self, request: StructuralValuationCollectionRequest
    ) -> StructuralValuationCollectionReport:
        """Refresh every selected symbol, then audit usable local valuation evidence."""
        results = tuple(self._collect_symbol(symbol, request.as_of) for symbol in request.symbols)
        valuation_available_after_run = sum(
            self._repository.load_latest_valuation_as_of(symbol, request.as_of) is not None
            for symbol in request.symbols
        )
        return StructuralValuationCollectionReport(
            as_of=request.as_of,
            requested_symbols=request.symbols,
            success_symbols=sum(
                result.status is StructuralValuationStatus.SUCCESS for result in results
            ),
            empty_symbols=sum(
                result.status is StructuralValuationStatus.EMPTY for result in results
            ),
            failed_symbols=sum(
                result.status is StructuralValuationStatus.FAILED for result in results
            ),
            rows_persisted=sum(result.rows_persisted for result in results),
            valuation_available_after_run=valuation_available_after_run,
            results=results,
            batch_first_symbol=request.symbols[0],
            batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=(
                request.symbols[-1] if request.has_more_structural_members else None
            ),
        )

    def _collect_symbol(
        self, symbol: str, as_of: datetime
    ) -> StructuralValuationSymbolResult:
        report = self._valuation_collector.collect((symbol,), as_of)
        status = _valuation_status(report, symbol)
        return StructuralValuationSymbolResult(
            symbol=symbol,
            status=status,
            rows_persisted=report.rows_persisted,
        )


def _valuation_status(
    report: FundamentalsCollectionReport, symbol: str
) -> StructuralValuationStatus:
    """Translate one existing one-symbol report into one stable outcome."""
    if report.requested_symbols != (symbol,):
        raise CollectionDataError("valuation collector returned a different requested symbol")
    outcomes = (
        (StructuralValuationStatus.SUCCESS, report.succeeded_symbols),
        (StructuralValuationStatus.EMPTY, report.empty_symbols),
        (StructuralValuationStatus.FAILED, report.failed_symbols),
    )
    if sum(count for _, count in outcomes) != 1:
        raise CollectionDataError("valuation collector returned an impossible one-symbol report")
    status = next(status for status, count in outcomes if count == 1)
    if status is StructuralValuationStatus.SUCCESS and report.rows_persisted == 0:
        raise CollectionDataError("valuation collector succeeded without persisted rows")
    if status is not StructuralValuationStatus.SUCCESS and report.rows_persisted != 0:
        raise CollectionDataError("valuation collector persisted rows without success")
    return status
