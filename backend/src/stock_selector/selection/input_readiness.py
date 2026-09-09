"""Pure current daily-selection upstream-input readiness audit."""

from datetime import datetime
from enum import Enum

from pydantic import field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)


class DailySelectionInputReadinessBlocker(str, Enum):
    """Stable reasons why current upstream inputs are not ready."""

    RISK_STATE_COVERAGE_INCOMPLETE = "risk_state_coverage_incomplete"
    NO_RISK_ELIGIBLE_MEMBERS = "no_risk_eligible_members"
    ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE = "eligible_factor_input_coverage_incomplete"


class DailySelectionInputReadinessRequest(DomainModel):
    """Already-read current tuples for the pure upstream-input audit."""

    as_of: datetime
    structural_symbols: tuple[str, ...]
    risk_record_symbols: tuple[str, ...]
    risk_complete_symbols: tuple[str, ...]
    risk_eligible_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "structural_symbols",
        "risk_record_symbols",
        "risk_complete_symbols",
        "risk_eligible_symbols",
        "factor_input_symbols",
    )
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value)

    @model_validator(mode="after")
    def validate_relationships(self) -> "DailySelectionInputReadinessRequest":
        if not self.structural_symbols:
            raise ValueError("structural_symbols must not be empty")
        structural = set(self.structural_symbols)
        records = set(self.risk_record_symbols)
        complete = set(self.risk_complete_symbols)
        if not records <= structural:
            raise ValueError("risk_record_symbols must be a structural subset")
        if not complete <= records:
            raise ValueError("risk_complete_symbols must be a risk-record subset")
        if not set(self.risk_eligible_symbols) <= complete:
            raise ValueError("risk_eligible_symbols must be a risk-complete subset")
        return self


class DailySelectionInputReadinessReport(DomainModel):
    """Defensively validated deterministic readiness result."""

    as_of: datetime
    structural_symbols: tuple[str, ...]
    risk_record_symbols: tuple[str, ...]
    risk_complete_symbols: tuple[str, ...]
    risk_eligible_symbols: tuple[str, ...]
    factor_input_symbols: tuple[str, ...]
    risk_incomplete_symbols: tuple[str, ...]
    eligible_factor_input_covered_symbols: tuple[str, ...]
    eligible_factor_input_missing_symbols: tuple[str, ...]
    structural_members: int
    risk_records: int
    risk_complete_members: int
    risk_incomplete_members: int
    risk_eligible_members: int
    stored_factor_input_symbols: int
    eligible_factor_input_covered: int
    eligible_factor_input_missing: int
    risk_incomplete_first_symbol: str | None
    risk_incomplete_last_symbol: str | None
    eligible_factor_input_missing_first_symbol: str | None
    eligible_factor_input_missing_last_symbol: str | None
    upstream_inputs_ready: bool
    blockers: tuple[DailySelectionInputReadinessBlocker, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "structural_symbols",
        "risk_record_symbols",
        "risk_complete_symbols",
        "risk_eligible_symbols",
        "factor_input_symbols",
        "risk_incomplete_symbols",
        "eligible_factor_input_covered_symbols",
        "eligible_factor_input_missing_symbols",
    )
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_symbols(value)

    @field_validator(
        "risk_incomplete_first_symbol",
        "risk_incomplete_last_symbol",
        "eligible_factor_input_missing_first_symbol",
        "eligible_factor_input_missing_last_symbol",
    )
    @classmethod
    def validate_optional_symbol(cls, value: str | None) -> str | None:
        return None if value is None else validate_symbol(value)

    @model_validator(mode="after")
    def validate_report(self) -> "DailySelectionInputReadinessReport":
        expected = _semantics(
            self.structural_symbols,
            self.risk_record_symbols,
            self.risk_complete_symbols,
            self.risk_eligible_symbols,
            self.factor_input_symbols,
        )
        if not self.structural_symbols:
            raise ValueError("structural_symbols must not be empty")
        structural = set(self.structural_symbols)
        records = set(self.risk_record_symbols)
        complete = set(self.risk_complete_symbols)
        if not records <= structural or not complete <= records or not set(self.risk_eligible_symbols) <= complete:
            raise ValueError("report input subsets are invalid")
        fields = (
            "risk_incomplete_symbols", "eligible_factor_input_covered_symbols",
            "eligible_factor_input_missing_symbols", "structural_members", "risk_records",
            "risk_complete_members", "risk_incomplete_members", "risk_eligible_members",
            "stored_factor_input_symbols", "eligible_factor_input_covered",
            "eligible_factor_input_missing", "risk_incomplete_first_symbol",
            "risk_incomplete_last_symbol", "eligible_factor_input_missing_first_symbol",
            "eligible_factor_input_missing_last_symbol", "upstream_inputs_ready", "blockers",
        )
        if any(getattr(self, field) != expected[field] for field in fields):
            raise ValueError("readiness report must match exact audit semantics")
        return self


class DailySelectionInputReadinessAuditor:
    """Compute readiness from already-loaded tuples only."""

    def audit(self, request: DailySelectionInputReadinessRequest) -> DailySelectionInputReadinessReport:
        values = _semantics(
            request.structural_symbols,
            request.risk_record_symbols,
            request.risk_complete_symbols,
            request.risk_eligible_symbols,
            request.factor_input_symbols,
        )
        return DailySelectionInputReadinessReport.model_validate(
            {
                "as_of": request.as_of,
                "structural_symbols": request.structural_symbols,
                "risk_record_symbols": request.risk_record_symbols,
                "risk_complete_symbols": request.risk_complete_symbols,
                "risk_eligible_symbols": request.risk_eligible_symbols,
                "factor_input_symbols": request.factor_input_symbols,
                **values,
            }
        )


def _validate_symbols(value: tuple[str, ...]) -> tuple[str, ...]:
    for symbol in value:
        validate_symbol(symbol)
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise ValueError("symbols must be canonical, unique, and sorted")
    return value


def _semantics(
    structural_symbols: tuple[str, ...],
    risk_record_symbols: tuple[str, ...],
    risk_complete_symbols: tuple[str, ...],
    risk_eligible_symbols: tuple[str, ...],
    factor_input_symbols: tuple[str, ...],
) -> dict[str, object]:
    complete = set(risk_complete_symbols)
    eligible = set(risk_eligible_symbols)
    factor = set(factor_input_symbols)
    incomplete = tuple(symbol for symbol in structural_symbols if symbol not in complete)
    covered = tuple(symbol for symbol in structural_symbols if symbol in eligible and symbol in factor)
    missing = tuple(symbol for symbol in structural_symbols if symbol in eligible and symbol not in factor)
    blockers: tuple[DailySelectionInputReadinessBlocker, ...]
    if incomplete:
        blockers = (DailySelectionInputReadinessBlocker.RISK_STATE_COVERAGE_INCOMPLETE,)
    elif not eligible:
        blockers = (DailySelectionInputReadinessBlocker.NO_RISK_ELIGIBLE_MEMBERS,)
    elif missing:
        blockers = (DailySelectionInputReadinessBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,)
    else:
        blockers = ()
    return {
        "risk_incomplete_symbols": incomplete,
        "eligible_factor_input_covered_symbols": covered,
        "eligible_factor_input_missing_symbols": missing,
        "structural_members": len(structural_symbols),
        "risk_records": len(risk_record_symbols),
        "risk_complete_members": len(risk_complete_symbols),
        "risk_incomplete_members": len(incomplete),
        "risk_eligible_members": len(risk_eligible_symbols),
        "stored_factor_input_symbols": len(factor_input_symbols),
        "eligible_factor_input_covered": len(covered),
        "eligible_factor_input_missing": len(missing),
        "risk_incomplete_first_symbol": incomplete[0] if incomplete else None,
        "risk_incomplete_last_symbol": incomplete[-1] if incomplete else None,
        "eligible_factor_input_missing_first_symbol": missing[0] if missing else None,
        "eligible_factor_input_missing_last_symbol": missing[-1] if missing else None,
        "upstream_inputs_ready": not blockers,
        "blockers": blockers,
    }
