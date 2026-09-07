"""One bounded orchestration pass for all current structural slow inputs."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.storage import LocalMarketRepository

from .errors import CollectionDataError
from .structural_adjusted_returns import (
    StructuralAdjustedReturnCollectionReport,
    StructuralAdjustedReturnCollectionRequest,
    StructuralAdjustedReturnCollector,
)
from .structural_fundamentals import (
    StructuralCoreCollectionReport,
    StructuralCoreCollectionRequest,
    StructuralCoreFundamentalsCollector,
)
from .structural_valuation import (
    StructuralValuationCollectionReport,
    StructuralValuationCollectionRequest,
    StructuralValuationCollector,
)


class StructuralSlowInputCollectionRequest(DomainModel):
    """One already-selected, finite structural batch for all slow inputs."""

    symbols: tuple[str, ...]
    as_of: datetime
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


class StructuralSlowInputCollectionReport(DomainModel):
    """Typed audit trail retaining all three structural subreports."""

    as_of: datetime
    requested_symbols: tuple[str, ...]
    core_report: StructuralCoreCollectionReport
    valuation_report: StructuralValuationCollectionReport
    adjusted_return_report: StructuralAdjustedReturnCollectionReport
    factor_input_covered_after_run: int = Field(ge=0)
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
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 20:
            raise ValueError("requested_symbols must contain between 1 and 20 entries")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("requested_symbols must be canonical, unique, and sorted")
        return value

    @model_validator(mode="after")
    def validate_report(self) -> "StructuralSlowInputCollectionReport":
        expected = self.requested_symbols
        if self.factor_input_covered_after_run > len(expected):
            raise ValueError("factor input coverage cannot exceed requested symbols")
        if (self.batch_first_symbol, self.batch_last_symbol) != (expected[0], expected[-1]):
            raise ValueError("batch boundary symbols must match requested symbols")
        if self.next_start_after != (expected[-1] if self.has_more_structural_members else None):
            raise ValueError("next cursor must match batch continuation")
        for report in (self.core_report, self.valuation_report, self.adjusted_return_report):
            if (report.requested_symbols, report.batch_first_symbol, report.batch_last_symbol,
                report.has_more_structural_members, report.next_start_after) != (
                expected, self.batch_first_symbol, self.batch_last_symbol,
                self.has_more_structural_members, self.next_start_after,
            ):
                raise ValueError("nested report metadata must match the structural batch")
        if self.core_report.as_of != self.as_of.date() or self.valuation_report.as_of != self.as_of:
            raise ValueError("nested report as_of must match the structural batch")
        adjusted = self.adjusted_return_report
        if (adjusted.as_of != self.as_of or adjusted.end_date != self.as_of.date()
                or adjusted.start_date != self.as_of.date() - timedelta(days=179)):
            raise ValueError("adjusted-return report window must match the structural batch")
        return self


class StructuralSlowInputCollector:
    """Call the three existing wrappers once, sequentially, then audit final membership."""

    def __init__(self, core: StructuralCoreFundamentalsCollector, valuation: StructuralValuationCollector,
                 adjusted_returns: StructuralAdjustedReturnCollector, repository: LocalMarketRepository) -> None:
        self._core = core
        self._valuation = valuation
        self._adjusted_returns = adjusted_returns
        self._repository = repository

    def collect(self, request: StructuralSlowInputCollectionRequest) -> StructuralSlowInputCollectionReport:
        core = self._core.collect(StructuralCoreCollectionRequest(
            symbols=request.symbols, as_of=request.as_of.date(), has_more_structural_members=request.has_more_structural_members))
        _validate_subreport(core, request, "core")
        valuation = self._valuation.collect(StructuralValuationCollectionRequest(
            symbols=request.symbols, as_of=request.as_of, has_more_structural_members=request.has_more_structural_members))
        _validate_subreport(valuation, request, "valuation")
        end_date = request.as_of.date()
        adjusted = self._adjusted_returns.collect(StructuralAdjustedReturnCollectionRequest(
            symbols=request.symbols, as_of=request.as_of, start_date=end_date - timedelta(days=179),
            end_date=end_date, has_more_structural_members=request.has_more_structural_members))
        _validate_subreport(adjusted, request, "adjusted")
        covered = set(self._repository.load_factor_input_symbols())
        return StructuralSlowInputCollectionReport(
            as_of=request.as_of, requested_symbols=request.symbols, core_report=core,
            valuation_report=valuation, adjusted_return_report=adjusted,
            factor_input_covered_after_run=sum(symbol in covered for symbol in request.symbols),
            batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=request.symbols[-1] if request.has_more_structural_members else None,
        )


def _validate_subreport(report: Any, request: StructuralSlowInputCollectionRequest, domain: str) -> None:
    expected_cursor = request.symbols[-1] if request.has_more_structural_members else None
    if (report.requested_symbols != request.symbols or report.batch_first_symbol != request.symbols[0]
            or report.batch_last_symbol != request.symbols[-1]
            or report.has_more_structural_members != request.has_more_structural_members
            or report.next_start_after != expected_cursor):
        raise CollectionDataError(f"{domain} collector returned mismatched batch metadata")
    if domain == "core" and report.as_of != request.as_of.date():
        raise CollectionDataError("core collector returned mismatched as_of")
    if domain in ("valuation", "adjusted") and report.as_of != request.as_of:
        raise CollectionDataError(f"{domain} collector returned mismatched as_of")
    if domain == "adjusted" and (report.end_date != request.as_of.date()
            or report.start_date != request.as_of.date() - timedelta(days=179)):
        raise CollectionDataError("adjusted collector returned mismatched date window")
