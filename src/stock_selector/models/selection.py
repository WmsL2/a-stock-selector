"""Selection, explanation, and risk records for future ranking workflows."""

from datetime import datetime
from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)


class Evidence(DomainModel):
    """A concise, serializable explanation item for a future selection."""

    code: str
    message: str
    factor_name: str | None = None
    value: float | None = None
    percentile: float | None = None
    contribution: float | None = None

    @field_validator("code", "message")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        """Require a stable explanation code and visible message."""
        return ensure_nonempty_string(value, info.field_name)

    @field_validator("value", "percentile", "contribution")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject non-finite explanation measurements."""
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_percentile(self) -> "Evidence":
        """Constrain any percentile to the conventional 0-100 scale."""
        if self.percentile is not None and not 0 <= self.percentile <= 100:
            raise ValueError("percentile must be between 0 and 100")
        return self


class RiskSeverity(str, Enum):
    """Severity levels for selection risk flags."""

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"


class RiskFlag(DomainModel):
    """A concise future risk label attached to one selection item."""

    code: str
    message: str
    severity: RiskSeverity

    @field_validator("code", "message")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        """Require a stable risk code and visible message."""
        return ensure_nonempty_string(value, info.field_name)


class StockScore(DomainModel):
    """A score record using 0-100 scores and 0-1 confidence proportions.

    ``data_completeness`` and ``confidence`` are proportions, so ``0.97``
    denotes 97%; scores are on the 0-100 scale.
    """

    symbol: str
    as_of: datetime
    base_score: float
    quality_score: float | None = None
    value_score: float | None = None
    growth_score: float | None = None
    momentum_score: float | None = None
    low_volatility_score: float | None = None
    data_completeness: float
    confidence: float
    confidence_adjusted_score: float | None = None
    market_rank: int | None = Field(default=None, gt=0)
    industry_rank: int | None = Field(default=None, gt=0)
    evidence: tuple[Evidence, ...] = ()
    risks: tuple[RiskFlag, ...] = ()

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        """Require an explicit score timestamp timezone."""
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "base_score",
        "quality_score",
        "value_score",
        "growth_score",
        "momentum_score",
        "low_volatility_score",
        "data_completeness",
        "confidence",
        "confidence_adjusted_score",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject NaN and infinities before applying score bounds."""
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_score_ranges(self) -> "StockScore":
        """Enforce score and proportion ranges without calculating scores."""
        for field_name in (
            "base_score",
            "quality_score",
            "value_score",
            "growth_score",
            "momentum_score",
            "low_volatility_score",
            "confidence_adjusted_score",
        ):
            value = getattr(self, field_name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")
        for field_name in ("data_completeness", "confidence"):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")
        return self


class SelectionResult(DomainModel):
    """A same-time, unique-symbol collection of future selection scores."""

    as_of: datetime
    strategy_name: str
    items: tuple[StockScore, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        """Require an explicit result timestamp timezone."""
        return ensure_aware_datetime(value, "as_of")

    @field_validator("strategy_name")
    @classmethod
    def validate_strategy_name(cls, value: str) -> str:
        """Require a visible strategy identifier."""
        return ensure_nonempty_string(value, "strategy_name")

    @model_validator(mode="after")
    def validate_items(self) -> "SelectionResult":
        """Require matching timestamps and unique symbols in a result set."""
        symbols: set[str] = set()
        for item in self.items:
            if item.as_of != self.as_of:
                raise ValueError("stock score as_of must match selection result as_of")
            if item.symbol in symbols:
                raise ValueError("selection result symbols must be unique")
            symbols.add(item.symbol)
        return self
