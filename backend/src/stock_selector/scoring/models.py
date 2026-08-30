"""Immutable, auditable outputs for pure BaseScore composition."""

import math
from datetime import datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.config.models import FactorsConfig
from stock_selector.factors.models import FactorFamily, FiveFactorCrossSectionResult
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    validate_symbol,
)


class BaseScoreRequest(DomainModel):
    """Explicit factor cross-section and configured weights for scoring."""

    factors: FiveFactorCrossSectionResult
    config: FactorsConfig


class FactorWeightContribution(DomainModel):
    """Configured and renormalized evidence for one fixed factor family."""

    family: FactorFamily
    enabled: bool
    configured_weight: float
    family_score: float | None
    family_component_coverage: float
    available: bool
    renormalized_weight: float
    weighted_contribution: float | None

    @field_validator(
        "configured_weight",
        "family_score",
        "family_component_coverage",
        "renormalized_weight",
        "weighted_contribution",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_audit_contract(self) -> "FactorWeightContribution":
        if not 0 <= self.configured_weight <= 1:
            raise ValueError("configured_weight must be between 0 and 1")
        if self.family_score is not None and not 0 <= self.family_score <= 100:
            raise ValueError("family_score must be between 0 and 100")
        if not 0 <= self.family_component_coverage <= 1:
            raise ValueError("family_component_coverage must be between 0 and 1")
        if not 0 <= self.renormalized_weight <= 1:
            raise ValueError("renormalized_weight must be between 0 and 1")
        if self.weighted_contribution is not None and not 0 <= self.weighted_contribution <= 100:
            raise ValueError("weighted_contribution must be between 0 and 100")
        if self.available != (self.enabled and self.family_score is not None):
            raise ValueError("availability must match enabled family score")
        if not self.available and (
            self.renormalized_weight != 0 or self.weighted_contribution is not None
        ):
            raise ValueError("unavailable contribution must be empty and unweighted")
        if self.available and self.weighted_contribution is None:
            raise ValueError("available contribution requires a weighted value")
        if self.weighted_contribution is not None and self.family_score is not None:
            expected = self.family_score * self.renormalized_weight
            if not math.isclose(
                self.weighted_contribution, expected, rel_tol=1e-9, abs_tol=1e-9
            ):
                raise ValueError("weighted_contribution must match score and weight")
        return self


class BaseScoreStockResult(DomainModel):
    """One security's BaseScore, uncertainty measures and factor audit trail."""

    symbol: str
    as_of: datetime
    base_score: float | None
    data_completeness: float
    confidence: float
    confidence_adjusted_score: float | None
    available_family_weight: float
    enabled_family_weight: float
    available_families: int
    enabled_families: int
    contributions: tuple[FactorWeightContribution, ...]

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "base_score",
        "data_completeness",
        "confidence",
        "confidence_adjusted_score",
        "available_family_weight",
        "enabled_family_weight",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_score_contract(self) -> "BaseScoreStockResult":
        for field_name in (
            "base_score",
            "confidence_adjusted_score",
        ):
            value = getattr(self, field_name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")
        for field_name in (
            "data_completeness",
            "confidence",
            "available_family_weight",
            "enabled_family_weight",
        ):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")
        if not 0 <= self.available_families <= len(FactorFamily):
            raise ValueError("available_families must be within the factor family count")
        if not 0 <= self.enabled_families <= len(FactorFamily):
            raise ValueError("enabled_families must be within the factor family count")
        if self.confidence > self.data_completeness:
            raise ValueError("confidence must not exceed data_completeness")
        if self.base_score is None and self.confidence_adjusted_score is not None:
            raise ValueError("missing base_score requires missing confidence_adjusted_score")
        if self.base_score is not None:
            expected_adjusted = self.base_score * self.confidence
            if not math.isclose(
                self.confidence_adjusted_score or 0,
                expected_adjusted,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError("confidence_adjusted_score must match base_score")
        expected_families = tuple(FactorFamily)
        if tuple(item.family for item in self.contributions) != expected_families:
            raise ValueError("contributions must use the fixed five-family order")
        if self.enabled_families != sum(item.enabled for item in self.contributions):
            raise ValueError("enabled_families must match contributions")
        if self.available_families != sum(item.available for item in self.contributions):
            raise ValueError("available_families must match contributions")
        enabled_weight = sum(
            item.configured_weight for item in self.contributions if item.enabled
        )
        available_weight = sum(
            item.configured_weight for item in self.contributions if item.available
        )
        if not math.isclose(
            self.enabled_family_weight, enabled_weight, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("enabled_family_weight must match contributions")
        if not math.isclose(
            self.available_family_weight, available_weight, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("available_family_weight must match contributions")
        expected_completeness = (
            available_weight / enabled_weight if enabled_weight else 0.0
        )
        if not math.isclose(
            self.data_completeness,
            expected_completeness,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("data_completeness must match family weights")
        expected_confidence = (
            sum(
                item.configured_weight * item.family_component_coverage
                for item in self.contributions
                if item.available
            )
            / enabled_weight
            if enabled_weight
            else 0.0
        )
        if not math.isclose(
            self.confidence, expected_confidence, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("confidence must match available family coverage")
        renormalized_sum = sum(item.renormalized_weight for item in self.contributions)
        if available_weight and not math.isclose(
            renormalized_sum, 1.0, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("available contribution weights must sum to one")
        contribution_sum = sum(
            item.weighted_contribution or 0 for item in self.contributions
        )
        if self.base_score is None and available_weight:
            raise ValueError("available family weight requires a base_score")
        if self.base_score is not None and not math.isclose(
            self.base_score, contribution_sum, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("base_score must match contribution sum")
        return self


class BaseScoreCrossSectionResult(DomainModel):
    """Symbol-sorted BaseScore results without any selection or ranking policy."""

    as_of: datetime
    input_count: int
    stocks: tuple[BaseScoreStockResult, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_stocks(self) -> "BaseScoreCrossSectionResult":
        if self.input_count != len(self.stocks):
            raise ValueError("input_count must equal stock count")
        symbols = tuple(item.symbol for item in self.stocks)
        if symbols != tuple(sorted(symbols)) or len(set(symbols)) != len(symbols):
            raise ValueError("stocks must be sorted and unique")
        if any(item.as_of != self.as_of for item in self.stocks):
            raise ValueError("stocks must match cross-section as_of")
        return self
