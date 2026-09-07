"""Bounded sequential multi-batch orchestration over Task35 slow-input refreshes."""

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)

from .structural_slow_inputs import (
    StructuralSlowInputCollectionReport,
    StructuralSlowInputCollectionRequest,
    StructuralSlowInputCollector,
)


class StructuralSlowInputSweepRequest(DomainModel):
    symbols: tuple[str, ...]
    as_of: datetime
    has_more_structural_members: bool

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 100:
            raise ValueError("symbols must contain between 1 and 100 entries")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("symbols must be canonical, unique, and sorted")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")


class StructuralSlowInputSweepReport(DomainModel):
    as_of: datetime
    requested_symbols: tuple[str, ...]
    batch_reports: tuple[StructuralSlowInputCollectionReport, ...]
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
    def validate_requested_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return StructuralSlowInputSweepRequest.validate_symbols(value)

    @model_validator(mode="after")
    def validate_report(self) -> "StructuralSlowInputSweepReport":
        if not self.batch_reports or self.factor_input_covered_after_run > len(self.requested_symbols):
            raise ValueError("sweep reports and coverage must be valid")
        if (self.batch_first_symbol, self.batch_last_symbol) != (self.requested_symbols[0], self.requested_symbols[-1]):
            raise ValueError("batch boundary symbols must match requested symbols")
        if self.next_start_after != (self.batch_last_symbol if self.has_more_structural_members else None):
            raise ValueError("next cursor must match continuation")
        if tuple(symbol for report in self.batch_reports for symbol in report.requested_symbols) != self.requested_symbols:
            raise ValueError("nested reports must exactly partition requested symbols")
        for index, report in enumerate(self.batch_reports):
            if report.as_of != self.as_of or not 1 <= len(report.requested_symbols) <= 20:
                raise ValueError("nested report must match sweep as_of and bound")
            if (
                report.batch_first_symbol != report.requested_symbols[0]
                or report.batch_last_symbol != report.requested_symbols[-1]
            ):
                raise ValueError("nested report batch boundaries must match requested symbols")
            expected_more = index < len(self.batch_reports) - 1 or self.has_more_structural_members
            if report.has_more_structural_members != expected_more or report.next_start_after != (report.requested_symbols[-1] if expected_more else None):
                raise ValueError("nested continuation must match sweep partition")
        if self.factor_input_covered_after_run != sum(
            report.factor_input_covered_after_run for report in self.batch_reports
        ):
            raise ValueError("sweep coverage must equal nested report coverage")
        return self


class StructuralSlowInputSweepCollector:
    def __init__(self, collector: StructuralSlowInputCollector) -> None:
        self._collector = collector

    def collect(self, request: StructuralSlowInputSweepRequest) -> StructuralSlowInputSweepReport:
        chunks = tuple(
            request.symbols[index : index + 20]
            for index in range(0, len(request.symbols), 20)
        )
        reports = tuple(
            self._collector.collect(
                StructuralSlowInputCollectionRequest(
                    symbols=chunk,
                    as_of=request.as_of,
                    has_more_structural_members=(
                        index < len(chunks) - 1 or request.has_more_structural_members
                    ),
                )
            )
            for index, chunk in enumerate(chunks)
        )
        return StructuralSlowInputSweepReport(
            as_of=request.as_of, requested_symbols=request.symbols, batch_reports=reports,
            factor_input_covered_after_run=sum(report.factor_input_covered_after_run for report in reports),
            batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=request.symbols[-1] if request.has_more_structural_members else None,
        )
