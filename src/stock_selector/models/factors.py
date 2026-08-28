"""Serializable factor observations without factor-computation behavior."""

from datetime import datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)


class FactorValue(DomainModel):
    """One available or unavailable factor observation for a security."""

    symbol: str
    as_of: datetime
    factor_name: str
    factor_group: str
    raw_value: float | None
    score: float | None
    available: bool
    source: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        """Require a timezone-aware factor observation timestamp."""
        return ensure_aware_datetime(value, "as_of")

    @field_validator("factor_name", "factor_group")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        """Require stable factor identifiers."""
        return ensure_nonempty_string(value, info.field_name)

    @field_validator("raw_value", "score")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject NaN and infinities in stored factor values."""
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_availability(self) -> "FactorValue":
        """Keep factor availability and score presence consistent."""
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if not self.available and self.score is not None:
            raise ValueError("unavailable factors must not have a score")
        if self.available and self.score is None:
            raise ValueError("available factors must have a score")
        return self


class FactorSnapshot(DomainModel):
    """A complete, same-time set of unique factor observations for one symbol."""

    symbol: str
    as_of: datetime
    values: tuple[FactorValue, ...]

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        """Require a timezone-aware snapshot timestamp."""
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_values(self) -> "FactorSnapshot":
        """Require matching snapshot identity and unique factor names."""
        names: set[str] = set()
        for value in self.values:
            if value.symbol != self.symbol:
                raise ValueError("factor value symbol must match snapshot symbol")
            if value.as_of != self.as_of:
                raise ValueError("factor value as_of must match snapshot as_of")
            if value.factor_name in names:
                raise ValueError("factor names must be unique within a snapshot")
            names.add(value.factor_name)
        return self
