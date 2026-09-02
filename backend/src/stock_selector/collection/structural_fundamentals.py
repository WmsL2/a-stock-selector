"""Bounded sequential refresh of financial and industry core factor inputs."""

from datetime import date
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, validate_symbol
from stock_selector.storage import LocalMarketRepository

from .errors import CollectionDataError
from .fundamentals import (
    FinancialCollector,
    FundamentalsCollectionReport,
    IndustryCollector,
)


class StructuralCoreCollectionRequest(DomainModel):
    """One already-selected finite structural batch for current core coverage."""

    symbols: tuple[str, ...]
    as_of: date
    has_more_structural_members: bool

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


class StructuralCoreDomainStatus(str, Enum):
    """One collector-domain outcome for one requested structural member."""

    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


class StructuralCoreSymbolResult(DomainModel):
    """Compact financial and industry evidence outcome for one symbol."""

    symbol: str
    financial_status: StructuralCoreDomainStatus
    financial_rows_persisted: int = Field(ge=0)
    industry_status: StructuralCoreDomainStatus
    industry_rows_persisted: int = Field(ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, value: str) -> str:
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_domain_rows(self) -> "StructuralCoreSymbolResult":
        for status, rows in (
            (self.financial_status, self.financial_rows_persisted),
            (self.industry_status, self.industry_rows_persisted),
        ):
            if status is StructuralCoreDomainStatus.SUCCESS and rows == 0:
                raise ValueError("successful domain outcome requires persisted rows")
            if status is not StructuralCoreDomainStatus.SUCCESS and rows != 0:
                raise ValueError("empty or failed domain outcome cannot persist rows")
        return self


class StructuralCoreCollectionReport(DomainModel):
    """Auditable result for a sequential current structural-core refresh batch."""

    as_of: date
    requested_symbols: tuple[str, ...]
    financial_start_period: date
    financial_end_period: date
    financial_success: int = Field(ge=0)
    financial_empty: int = Field(ge=0)
    financial_failed: int = Field(ge=0)
    financial_rows_persisted: int = Field(ge=0)
    industry_success: int = Field(ge=0)
    industry_empty: int = Field(ge=0)
    industry_failed: int = Field(ge=0)
    industry_rows_persisted: int = Field(ge=0)
    fully_successful_symbols: int = Field(ge=0)
    core_covered_after_run: int = Field(ge=0)
    results: tuple[StructuralCoreSymbolResult, ...]
    batch_first_symbol: str
    batch_last_symbol: str
    has_more_structural_members: bool
    next_start_after: str | None = None

    @field_validator("requested_symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("requested_symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("requested_symbols must be unique and sorted")
        return value

    @field_validator("batch_first_symbol", "batch_last_symbol", "next_start_after")
    @classmethod
    def validate_optional_symbol(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_report(self) -> "StructuralCoreCollectionReport":
        if self.financial_start_period > self.financial_end_period:
            raise ValueError("financial period window must be ordered")
        if self.financial_end_period != self.as_of:
            raise ValueError("financial end period must equal batch as_of")
        if tuple(result.symbol for result in self.results) != self.requested_symbols:
            raise ValueError("results must retain requested symbol order")
        expected = len(self.requested_symbols)
        if (
            self.financial_success + self.financial_empty + self.financial_failed != expected
            or self.industry_success + self.industry_empty + self.industry_failed != expected
        ):
            raise ValueError("domain outcome counts must equal requested symbols")
        if self.financial_success != sum(
            result.financial_status is StructuralCoreDomainStatus.SUCCESS
            for result in self.results
        ):
            raise ValueError("financial success count must match results")
        if self.financial_empty != sum(
            result.financial_status is StructuralCoreDomainStatus.EMPTY
            for result in self.results
        ):
            raise ValueError("financial empty count must match results")
        if self.financial_failed != sum(
            result.financial_status is StructuralCoreDomainStatus.FAILED
            for result in self.results
        ):
            raise ValueError("financial failed count must match results")
        if self.industry_success != sum(
            result.industry_status is StructuralCoreDomainStatus.SUCCESS
            for result in self.results
        ):
            raise ValueError("industry success count must match results")
        if self.industry_empty != sum(
            result.industry_status is StructuralCoreDomainStatus.EMPTY
            for result in self.results
        ):
            raise ValueError("industry empty count must match results")
        if self.industry_failed != sum(
            result.industry_status is StructuralCoreDomainStatus.FAILED
            for result in self.results
        ):
            raise ValueError("industry failed count must match results")
        if self.financial_rows_persisted != sum(
            result.financial_rows_persisted for result in self.results
        ):
            raise ValueError("financial rows must match results")
        if self.industry_rows_persisted != sum(
            result.industry_rows_persisted for result in self.results
        ):
            raise ValueError("industry rows must match results")
        if self.fully_successful_symbols != sum(
            result.financial_status is StructuralCoreDomainStatus.SUCCESS
            and result.industry_status is StructuralCoreDomainStatus.SUCCESS
            for result in self.results
        ):
            raise ValueError("fully successful count must match results")
        if self.core_covered_after_run > expected:
            raise ValueError("core coverage cannot exceed requested symbols")
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


class StructuralCoreFundamentalsCollector:
    """Run existing financial then industry collectors sequentially per symbol."""

    def __init__(
        self,
        financial_collector: FinancialCollector,
        industry_collector: IndustryCollector,
        repository: LocalMarketRepository,
    ) -> None:
        self._financial_collector = financial_collector
        self._industry_collector = industry_collector
        self._repository = repository

    def collect(
        self, request: StructuralCoreCollectionRequest
    ) -> StructuralCoreCollectionReport:
        """Refresh each selected symbol in stable financial-then-industry order."""
        start_period = date(request.as_of.year - 2, 1, 1)
        results = tuple(
            self._collect_symbol(symbol, start_period, request.as_of)
            for symbol in request.symbols
        )
        covered_symbols = set(self._repository.load_factor_input_symbols())
        return StructuralCoreCollectionReport(
            as_of=request.as_of,
            requested_symbols=request.symbols,
            financial_start_period=start_period,
            financial_end_period=request.as_of,
            financial_success=sum(
                result.financial_status is StructuralCoreDomainStatus.SUCCESS
                for result in results
            ),
            financial_empty=sum(
                result.financial_status is StructuralCoreDomainStatus.EMPTY
                for result in results
            ),
            financial_failed=sum(
                result.financial_status is StructuralCoreDomainStatus.FAILED
                for result in results
            ),
            financial_rows_persisted=sum(
                result.financial_rows_persisted for result in results
            ),
            industry_success=sum(
                result.industry_status is StructuralCoreDomainStatus.SUCCESS
                for result in results
            ),
            industry_empty=sum(
                result.industry_status is StructuralCoreDomainStatus.EMPTY
                for result in results
            ),
            industry_failed=sum(
                result.industry_status is StructuralCoreDomainStatus.FAILED
                for result in results
            ),
            industry_rows_persisted=sum(
                result.industry_rows_persisted for result in results
            ),
            fully_successful_symbols=sum(
                result.financial_status is StructuralCoreDomainStatus.SUCCESS
                and result.industry_status is StructuralCoreDomainStatus.SUCCESS
                for result in results
            ),
            core_covered_after_run=sum(
                symbol in covered_symbols for symbol in request.symbols
            ),
            results=results,
            batch_first_symbol=request.symbols[0],
            batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=(
                request.symbols[-1] if request.has_more_structural_members else None
            ),
        )

    def _collect_symbol(
        self, symbol: str, start_period: date, as_of: date
    ) -> StructuralCoreSymbolResult:
        financial = self._financial_collector.collect((symbol,), start_period, as_of)
        industry = self._industry_collector.collect((symbol,), as_of)
        financial_status = _domain_status(financial, symbol, "financial")
        industry_status = _domain_status(industry, symbol, "industry")
        return StructuralCoreSymbolResult(
            symbol=symbol,
            financial_status=financial_status,
            financial_rows_persisted=financial.rows_persisted,
            industry_status=industry_status,
            industry_rows_persisted=industry.rows_persisted,
        )


def _domain_status(
    report: FundamentalsCollectionReport, symbol: str, domain: str
) -> StructuralCoreDomainStatus:
    """Translate one existing one-symbol collector report into one stable outcome."""
    if report.requested_symbols != (symbol,):
        raise CollectionDataError(f"{domain} collector returned a different requested symbol")
    outcomes = (
        (StructuralCoreDomainStatus.SUCCESS, report.succeeded_symbols),
        (StructuralCoreDomainStatus.EMPTY, report.empty_symbols),
        (StructuralCoreDomainStatus.FAILED, report.failed_symbols),
    )
    if sum(count for _, count in outcomes) != 1:
        raise CollectionDataError(f"{domain} collector returned an impossible one-symbol report")
    status = next(status for status, count in outcomes if count == 1)
    if status is StructuralCoreDomainStatus.SUCCESS and report.rows_persisted == 0:
        raise CollectionDataError(f"{domain} collector succeeded without persisted rows")
    if status is not StructuralCoreDomainStatus.SUCCESS and report.rows_persisted != 0:
        raise CollectionDataError(f"{domain} collector persisted rows without success")
    return status
