"""Pure, read-only current official selection data-coverage audit."""

from datetime import datetime
from math import ceil

from pydantic import field_validator, model_validator

from stock_selector.collection import (
    StructuralFactorInputCoverageAuditor,
    StructuralFactorInputCoverageReport,
    StructuralFactorInputCoverageRequest,
)
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)

from .input_readiness import (
    DailySelectionInputReadinessAuditor,
    DailySelectionInputReadinessReport,
    DailySelectionInputReadinessRequest,
)


def _symbols(value: tuple[str, ...]) -> tuple[str, ...]:
    for symbol in value:
        validate_symbol(symbol)
    if len(value) != len(set(value)) or value != tuple(sorted(value)):
        raise ValueError("symbols must be canonical, unique, and sorted")
    return value


class CurrentSelectionCoverageRequest(DomainModel):
    as_of: datetime
    structural_symbols: tuple[str, ...]
    risk_record_symbols: tuple[str, ...]
    risk_complete_symbols: tuple[str, ...]
    risk_eligible_symbols: tuple[str, ...]
    financial_symbols: tuple[str, ...]
    valuation_symbols: tuple[str, ...]
    industry_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]
    adjusted_return_symbols: tuple[str, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "structural_symbols",
        "risk_record_symbols",
        "risk_complete_symbols",
        "risk_eligible_symbols",
        "financial_symbols",
        "valuation_symbols",
        "industry_symbols",
        "factor_input_symbols",
        "adjusted_return_symbols",
    )
    @classmethod
    def valid_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _symbols(value)

    @model_validator(mode="after")
    def relationships(self) -> "CurrentSelectionCoverageRequest":
        structural, records, complete, eligible = map(
            set,
            (
                self.structural_symbols,
                self.risk_record_symbols,
                self.risk_complete_symbols,
                self.risk_eligible_symbols,
            ),
        )
        if (
            not structural
            or not records <= structural
            or not complete <= records
            or not eligible <= complete
        ):
            raise ValueError("structural and risk membership subsets are invalid")
        expected = set(self.industry_symbols) & (
            set(self.financial_symbols) | set(self.valuation_symbols)
        )
        if set(self.factor_input_symbols) != expected:
            raise ValueError(
                "factor_input_symbols must equal industry AND (financial OR valuation)"
            )
        return self


class CurrentSelectionCoverageReport(DomainModel):
    as_of: datetime
    structural_factor_input_coverage: StructuralFactorInputCoverageReport
    input_readiness: DailySelectionInputReadinessReport
    structural_symbols: tuple[str, ...]
    risk_record_symbols: tuple[str, ...]
    risk_complete_symbols: tuple[str, ...]
    risk_eligible_symbols: tuple[str, ...]
    financial_symbols: tuple[str, ...]
    valuation_symbols: tuple[str, ...]
    industry_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]
    adjusted_return_symbols: tuple[str, ...]
    structural_financial_symbols: tuple[str, ...]
    structural_valuation_symbols: tuple[str, ...]
    structural_industry_symbols: tuple[str, ...]
    structural_adjusted_return_symbols: tuple[str, ...]
    eligible_financial_symbols: tuple[str, ...]
    eligible_valuation_symbols: tuple[str, ...]
    eligible_industry_symbols: tuple[str, ...]
    eligible_adjusted_return_symbols: tuple[str, ...]
    eligible_adjusted_return_missing_symbols: tuple[str, ...]
    eligible_missing_industry_symbols: tuple[str, ...]
    eligible_missing_financial_and_valuation_symbols: tuple[str, ...]
    prepare_inputs_max_limit: int = 100
    minimum_prepare_runs_at_max_limit: int

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "structural_symbols",
        "risk_record_symbols",
        "risk_complete_symbols",
        "risk_eligible_symbols",
        "financial_symbols",
        "valuation_symbols",
        "industry_symbols",
        "factor_input_symbols",
        "adjusted_return_symbols",
        "structural_financial_symbols",
        "structural_valuation_symbols",
        "structural_industry_symbols",
        "structural_adjusted_return_symbols",
        "eligible_financial_symbols",
        "eligible_valuation_symbols",
        "eligible_industry_symbols",
        "eligible_adjusted_return_symbols",
        "eligible_adjusted_return_missing_symbols",
        "eligible_missing_industry_symbols",
        "eligible_missing_financial_and_valuation_symbols",
    )
    @classmethod
    def valid_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _symbols(value)

    @model_validator(mode="after")
    def exact(self) -> "CurrentSelectionCoverageReport":
        coverage, readiness = (
            self.structural_factor_input_coverage,
            self.input_readiness,
        )
        if (
            self.as_of != coverage.as_of
            or self.as_of != readiness.as_of
            or self.structural_symbols != coverage.structural_symbols
            or self.structural_symbols != readiness.structural_symbols
            or self.factor_input_symbols != coverage.factor_input_symbols
            or self.factor_input_symbols != readiness.factor_input_symbols
            or self.risk_record_symbols != readiness.risk_record_symbols
            or self.risk_complete_symbols != readiness.risk_complete_symbols
            or self.risk_eligible_symbols != readiness.risk_eligible_symbols
        ):
            raise ValueError("retained audit reports must share exact inputs")
        structural = set(self.structural_symbols)
        eligible = set(self.risk_eligible_symbols)
        financial = set(self.financial_symbols)
        valuation = set(self.valuation_symbols)
        industry = set(self.industry_symbols)
        adjusted = set(self.adjusted_return_symbols)
        if set(self.factor_input_symbols) != industry & (financial | valuation):
            raise ValueError("factor input membership must match its authoritative rule")
        exact_tuples = {
            "structural_financial_symbols": tuple(sorted(structural & financial)),
            "structural_valuation_symbols": tuple(sorted(structural & valuation)),
            "structural_industry_symbols": tuple(sorted(structural & industry)),
            "structural_adjusted_return_symbols": tuple(sorted(structural & adjusted)),
            "eligible_financial_symbols": tuple(sorted(eligible & financial)),
            "eligible_valuation_symbols": tuple(sorted(eligible & valuation)),
            "eligible_industry_symbols": tuple(sorted(eligible & industry)),
            "eligible_adjusted_return_symbols": tuple(sorted(eligible & adjusted)),
            "eligible_adjusted_return_missing_symbols": tuple(sorted(eligible - adjusted)),
        }
        if any(getattr(self, key) != value for key, value in exact_tuples.items()):
            raise ValueError("derived coverage tuples must match retained memberships")
        missing = set(readiness.eligible_factor_input_missing_symbols)
        if self.eligible_missing_industry_symbols != tuple(sorted(missing - industry)):
            raise ValueError("eligible missing industry cause must be exact")
        if self.eligible_missing_financial_and_valuation_symbols != tuple(sorted(missing - (financial | valuation))):
            raise ValueError("eligible missing financial and valuation cause must be exact")
        if (
            set(self.eligible_missing_industry_symbols)
            | set(self.eligible_missing_financial_and_valuation_symbols)
            != missing
        ):
            raise ValueError(
                "missing causes must exactly cover eligible factor-input missing symbols"
            )
        expected_runs = (
            0 if not missing else ceil(len(missing) / self.prepare_inputs_max_limit)
        )
        if (
            self.prepare_inputs_max_limit != 100
            or self.minimum_prepare_runs_at_max_limit != expected_runs
        ):
            raise ValueError(
                "minimum preparation runs must be the exact max-limit lower bound"
            )
        return self


class CurrentSelectionCoverageAuditor:
    """Compose the authoritative Task37 and Task39 pure auditors."""

    def audit(
        self, request: CurrentSelectionCoverageRequest
    ) -> CurrentSelectionCoverageReport:
        structural, eligible = (
            set(request.structural_symbols),
            set(request.risk_eligible_symbols),
        )
        coverage = StructuralFactorInputCoverageAuditor().audit(
            StructuralFactorInputCoverageRequest(
                as_of=request.as_of,
                structural_symbols=request.structural_symbols,
                factor_input_symbols=request.factor_input_symbols,
            )
        )
        readiness = DailySelectionInputReadinessAuditor().audit(
            DailySelectionInputReadinessRequest(
                as_of=request.as_of,
                structural_symbols=request.structural_symbols,
                risk_record_symbols=request.risk_record_symbols,
                risk_complete_symbols=request.risk_complete_symbols,
                risk_eligible_symbols=request.risk_eligible_symbols,
                factor_input_symbols=request.factor_input_symbols,
            )
        )

        def overlap(left: set[str], right: set[str]) -> tuple[str, ...]:
            return tuple(sorted(left & right))

        financial, valuation, industry, adjusted = map(
            set,
            (
                request.financial_symbols,
                request.valuation_symbols,
                request.industry_symbols,
                request.adjusted_return_symbols,
            ),
        )
        missing = set(readiness.eligible_factor_input_missing_symbols)
        return CurrentSelectionCoverageReport(
            as_of=request.as_of,
            structural_factor_input_coverage=coverage,
            input_readiness=readiness,
            structural_symbols=request.structural_symbols,
            risk_record_symbols=request.risk_record_symbols,
            risk_complete_symbols=request.risk_complete_symbols,
            risk_eligible_symbols=request.risk_eligible_symbols,
            financial_symbols=request.financial_symbols,
            valuation_symbols=request.valuation_symbols,
            industry_symbols=request.industry_symbols,
            factor_input_symbols=request.factor_input_symbols,
            adjusted_return_symbols=request.adjusted_return_symbols,
            structural_financial_symbols=overlap(structural, financial),
            structural_valuation_symbols=overlap(structural, valuation),
            structural_industry_symbols=overlap(structural, industry),
            structural_adjusted_return_symbols=overlap(structural, adjusted),
            eligible_financial_symbols=overlap(eligible, financial),
            eligible_valuation_symbols=overlap(eligible, valuation),
            eligible_industry_symbols=overlap(eligible, industry),
            eligible_adjusted_return_symbols=overlap(eligible, adjusted),
            eligible_adjusted_return_missing_symbols=tuple(sorted(eligible - adjusted)),
            eligible_missing_industry_symbols=tuple(sorted(missing - industry)),
            eligible_missing_financial_and_valuation_symbols=tuple(
                sorted(missing - (financial | valuation))
            ),
            minimum_prepare_runs_at_max_limit=0
            if not missing
            else ceil(len(missing) / 100),
        )
