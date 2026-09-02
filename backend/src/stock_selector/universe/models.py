"""Immutable structural-universe decisions independent of risk filtering."""

from datetime import date
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, validate_symbol


class UniverseExclusionReason(str, Enum):
    """Deterministic structural reasons an instrument is outside the universe."""

    NON_A_SHARE_SECURITY = "non_a_share_security"
    BOARD_DISABLED = "board_disabled"
    NOT_YET_LISTED = "not_yet_listed"
    DELISTED = "delisted"
    MIN_LISTING_DAYS = "min_listing_days"


class UniverseDecision(DomainModel):
    """One instrument's structural membership result at an explicit date."""

    symbol: str
    included: bool
    reasons: tuple[UniverseExclusionReason, ...] = ()

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Keep the shared canonical security identifier contract."""
        return validate_symbol(value)

    @model_validator(mode="after")
    def validate_membership_reasons(self) -> "UniverseDecision":
        """Require reasons to agree with the binary membership decision."""
        if self.included and self.reasons:
            raise ValueError("included universe decision must not contain reasons")
        if not self.included and not self.reasons:
            raise ValueError("excluded universe decision must contain a reason")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("universe decision reasons must be unique")
        return self


class UniverseSnapshot(DomainModel):
    """Auditable structural universe output for one point-in-time date."""

    as_of: date
    input_count: int = Field(ge=0)
    members: tuple[str, ...]
    decisions: tuple[UniverseDecision, ...]

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require canonical, unique, ascending included symbols."""
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("universe members must be unique")
        if value != tuple(sorted(value)):
            raise ValueError("universe members must be sorted by symbol")
        return value

    @model_validator(mode="after")
    def validate_snapshot_consistency(self) -> "UniverseSnapshot":
        """Ensure decisions preserve the complete, ordered input audit trail."""
        if self.input_count != len(self.decisions):
            raise ValueError("input_count must equal the number of decisions")
        symbols = tuple(decision.symbol for decision in self.decisions)
        if len(set(symbols)) != len(symbols):
            raise ValueError("universe decisions must have unique symbols")
        if symbols != tuple(sorted(symbols)):
            raise ValueError("universe decisions must be sorted by symbol")
        included = tuple(decision.symbol for decision in self.decisions if decision.included)
        if self.members != included:
            raise ValueError("universe members must match included decisions")
        return self
