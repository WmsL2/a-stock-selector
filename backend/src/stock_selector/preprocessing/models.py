"""Immutable request, observation, and diagnostic models for preprocessing."""

from datetime import datetime
from enum import StrEnum

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)


class MissingValuePolicy(StrEnum):
    """Explicit policies for raw values that are absent from a cross-section."""

    KEEP_MISSING = "keep_missing"
    MARKET_MEDIAN = "market_median"
    INDUSTRY_MEDIAN = "industry_median"


class FactorDirection(StrEnum):
    """Whether larger or smaller raw values should receive larger scores."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class NeutralizationMode(StrEnum):
    """Ranking scopes supported by the generic first preprocessing version."""

    NONE = "none"
    INDUSTRY_PERCENTILE = "industry_percentile"


class ValueOrigin(StrEnum):
    """Auditable provenance for a prepared value."""

    OBSERVED = "observed"
    MARKET_MEDIAN_IMPUTED = "market_median_imputed"
    INDUSTRY_MEDIAN_IMPUTED = "industry_median_imputed"
    MISSING = "missing"


class UnavailableReason(StrEnum):
    """Why an observation could not receive a normalized score."""

    MISSING_VALUE = "missing_value"
    NO_IMPUTATION_SOURCE = "no_imputation_source"
    MISSING_INDUSTRY = "missing_industry"


class RawFactorObservation(DomainModel):
    """One caller-supplied raw factor value; no factor calculation occurs here."""

    symbol: str
    as_of: datetime
    factor_name: str
    factor_group: str
    raw_value: float | None
    industry_key: str | None = None
    source: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("factor_name", "factor_group")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        return ensure_nonempty_string(value, info.field_name)

    @field_validator("raw_value")
    @classmethod
    def validate_raw_value(cls, value: float | None) -> float | None:
        return ensure_finite_float(value, "raw_value")

    @field_validator("industry_key", "source")
    @classmethod
    def validate_optional_strings(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        return (
            value if value is None else ensure_nonempty_string(value, info.field_name)
        )


class PreprocessedFactorObservation(DomainModel):
    """One fully auditable preprocessing outcome for a raw observation."""

    symbol: str
    as_of: datetime
    factor_name: str
    factor_group: str
    raw_value: float | None
    prepared_value: float | None
    winsorized_value: float | None
    score: float | None
    available: bool
    imputed: bool
    winsorized: bool
    industry_key: str | None
    value_origin: ValueOrigin
    unavailable_reason: UnavailableReason | None
    source: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("factor_name", "factor_group")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        return ensure_nonempty_string(value, info.field_name)

    @field_validator("raw_value", "prepared_value", "winsorized_value", "score")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @field_validator("industry_key", "source")
    @classmethod
    def validate_optional_strings(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        return (
            value if value is None else ensure_nonempty_string(value, info.field_name)
        )

    @model_validator(mode="after")
    def validate_auditable_availability(self) -> "PreprocessedFactorObservation":
        imputed_origin = {
            ValueOrigin.MARKET_MEDIAN_IMPUTED,
            ValueOrigin.INDUSTRY_MEDIAN_IMPUTED,
        }
        if self.imputed != (self.value_origin in imputed_origin):
            raise ValueError("imputed must match value_origin")
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.available:
            if self.score is None or self.unavailable_reason is not None:
                raise ValueError("available observations require score and no reason")
        elif self.score is not None or self.unavailable_reason is None:
            raise ValueError("unavailable observations require no score and a reason")
        if self.prepared_value is None and self.winsorized_value is not None:
            raise ValueError("winsorized_value requires prepared_value")
        return self


class FactorPreprocessingRequest(DomainModel):
    """Caller-selected generic policy for exactly one factor cross-section."""

    observations: tuple[RawFactorObservation, ...]
    missing_policy: MissingValuePolicy = MissingValuePolicy.KEEP_MISSING
    direction: FactorDirection = FactorDirection.HIGHER_IS_BETTER
    neutralization: NeutralizationMode = NeutralizationMode.NONE
    mad_multiplier: float = 3.0
    winsorize: bool = True

    @field_validator("mad_multiplier")
    @classmethod
    def validate_mad_multiplier(cls, value: float) -> float:
        finite = ensure_finite_float(value, "mad_multiplier")
        if finite is None or finite <= 0:
            raise ValueError("mad_multiplier must be positive")
        return finite


class PreprocessingResult(DomainModel):
    """Sorted outcomes and counts for one deterministic factor cross-section."""

    as_of: datetime
    factor_name: str
    factor_group: str
    input_count: int
    observed_count: int
    imputed_count: int
    available_count: int
    unavailable_count: int
    winsorized_count: int
    missing_policy: MissingValuePolicy
    direction: FactorDirection
    neutralization: NeutralizationMode
    values: tuple[PreprocessedFactorObservation, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("factor_name", "factor_group")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        return ensure_nonempty_string(value, info.field_name)

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "PreprocessingResult":
        if self.input_count != len(self.values):
            raise ValueError("input_count must equal values length")
        if tuple(item.symbol for item in self.values) != tuple(
            sorted(item.symbol for item in self.values)
        ):
            raise ValueError("values must be sorted by symbol")
        if len({item.symbol for item in self.values}) != len(self.values):
            raise ValueError("values must have unique symbols")
        if any(
            item.as_of != self.as_of
            or item.factor_name != self.factor_name
            or item.factor_group != self.factor_group
            for item in self.values
        ):
            raise ValueError("values must match result cross-section identity")
        counts = {
            "observed_count": sum(item.raw_value is not None for item in self.values),
            "imputed_count": sum(item.imputed for item in self.values),
            "available_count": sum(item.available for item in self.values),
            "unavailable_count": sum(not item.available for item in self.values),
            "winsorized_count": sum(item.winsorized for item in self.values),
        }
        if any(getattr(self, name) != count for name, count in counts.items()):
            raise ValueError("diagnostic counts must match values")
        return self
