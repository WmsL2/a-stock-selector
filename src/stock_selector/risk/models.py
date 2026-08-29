"""Immutable point-in-time risk observations and conservative decisions."""

from datetime import date, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_nonempty_string,
    validate_symbol,
)


class DatedRiskState(DomainModel):
    """Known risk fields for one security on one business date.

    ``None`` means unknown rather than false. ``observed_at`` records when this
    local record was received and never substitutes for the business ``as_of``.
    """

    symbol: str
    as_of: date
    is_st: bool | None = None
    is_suspended: bool | None = None
    is_delisting_period: bool | None = None
    observed_at: datetime
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "observed_at")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_information_value(self) -> "DatedRiskState":
        if all(
            value is None
            for value in (self.is_st, self.is_suspended, self.is_delisting_period)
        ):
            raise ValueError("dated risk state must contain at least one known risk field")
        return self


class RiskExclusionReason(str, Enum):
    """Stable reason codes for eligibility decisions."""

    ST = "st"
    SUSPENDED = "suspended"
    DELISTING_PERIOD = "delisting_period"
    MISSING_RISK_STATE = "missing_risk_state"
    UNKNOWN_RISK_FIELD = "unknown_risk_field"


class RiskEligibilityDecision(DomainModel):
    """Conservative risk eligibility outcome for one structural member."""

    symbol: str
    eligible: bool
    risk_complete: bool
    reasons: tuple[RiskExclusionReason, ...] = ()

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_decision(self) -> "RiskEligibilityDecision":
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("risk eligibility reasons must be unique")
        if tuple(sorted(self.reasons, key=_reason_rank)) != self.reasons:
            raise ValueError("risk eligibility reasons must use deterministic order")
        if self.eligible and (self.reasons or not self.risk_complete):
            raise ValueError("eligible decision requires complete risk data and no reasons")
        if not self.risk_complete and self.eligible:
            raise ValueError("incomplete risk data cannot be eligible")
        if not self.eligible and not self.reasons:
            raise ValueError("ineligible decision must contain a reason")
        return self


class RiskEligibilitySnapshot(DomainModel):
    """Auditable risk results for exactly one structural universe snapshot."""

    as_of: date
    structural_members: int = Field(ge=0)
    risk_records: int = Field(ge=0)
    risk_complete_members: int = Field(ge=0)
    eligible_members: tuple[str, ...]
    decisions: tuple[RiskEligibilityDecision, ...]

    @field_validator("eligible_members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("eligible members must be unique and sorted")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> "RiskEligibilitySnapshot":
        if self.structural_members != len(self.decisions):
            raise ValueError("structural_members must equal decision count")
        symbols = tuple(decision.symbol for decision in self.decisions)
        if len(set(symbols)) != len(symbols) or symbols != tuple(sorted(symbols)):
            raise ValueError("risk decisions must be unique and sorted")
        if self.risk_complete_members != sum(
            decision.risk_complete for decision in self.decisions
        ):
            raise ValueError("risk_complete_members must match decisions")
        if self.eligible_members != tuple(
            decision.symbol for decision in self.decisions if decision.eligible
        ):
            raise ValueError("eligible members must match eligible decisions")
        return self


def _reason_rank(reason: RiskExclusionReason) -> int:
    return tuple(RiskExclusionReason).index(reason)
