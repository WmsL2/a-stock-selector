"""Immutable readiness diagnostics for the daily selection application layer."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.models.selection import SelectionResult


class SelectionBlocker(StrEnum):
    """Stable machine-readable reasons that official daily selection is empty."""

    RISK_STATE_COVERAGE_INCOMPLETE = "risk_state_coverage_incomplete"
    NO_STRUCTURAL_MEMBERS = "no_structural_members"
    NO_RISK_ELIGIBLE_MEMBERS = "no_risk_eligible_members"
    NO_SCOREABLE_INSTRUMENTS = "no_scoreable_instruments"


class DailySelectionDiagnostics(DomainModel):
    """Counts and readiness truth for one explicit daily selection instant."""

    as_of: datetime
    selection_ready: bool
    blockers: tuple[SelectionBlocker, ...]
    input_instruments: int = Field(ge=0)
    structural_members: int = Field(ge=0)
    risk_records: int = Field(ge=0)
    risk_complete_members: int = Field(ge=0)
    risk_coverage_ratio: float = Field(ge=0, le=1)
    risk_eligible_members: int = Field(ge=0)
    factor_input_members: int = Field(ge=0)
    scoreable_members: int = Field(ge=0)
    requested_top_n: int = Field(gt=0)
    returned_items: int = Field(ge=0)
    price_factors_operational: bool

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_counts(self) -> "DailySelectionDiagnostics":
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("selection blockers must be unique")
        if self.structural_members > self.input_instruments:
            raise ValueError("structural_members must not exceed input_instruments")
        if self.risk_complete_members > self.structural_members:
            raise ValueError("risk_complete_members must not exceed structural_members")
        if self.risk_eligible_members > self.risk_complete_members:
            raise ValueError("risk_eligible_members must not exceed complete members")
        if self.factor_input_members > self.risk_eligible_members:
            raise ValueError("factor_input_members must not exceed eligible members")
        if self.scoreable_members > self.factor_input_members:
            raise ValueError("scoreable_members must not exceed factor inputs")
        if self.returned_items > self.scoreable_members:
            raise ValueError("returned_items must not exceed scoreable members")
        expected_ratio = (
            self.risk_complete_members / self.structural_members
            if self.structural_members
            else 0.0
        )
        if self.risk_coverage_ratio != expected_ratio:
            raise ValueError("risk_coverage_ratio must match structural coverage")
        return self


class DailySelectionResult(DomainModel):
    """Read-only daily ranking plus the diagnostics that justify its availability."""

    as_of: datetime
    diagnostics: DailySelectionDiagnostics
    selection: SelectionResult

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_identity(self) -> "DailySelectionResult":
        if self.diagnostics.as_of != self.as_of or self.selection.as_of != self.as_of:
            raise ValueError("daily selection result timestamps must match")
        if self.diagnostics.selection_ready != bool(self.selection.items):
            raise ValueError("selection readiness must match official item availability")
        if self.diagnostics.returned_items != len(self.selection.items):
            raise ValueError("returned_items must match selection items")
        return self
