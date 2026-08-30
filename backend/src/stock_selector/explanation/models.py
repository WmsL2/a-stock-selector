"""Immutable input and output contracts for explanation generation."""

from datetime import datetime

from pydantic import field_validator, model_validator

from stock_selector.factors.models import FiveFactorStockResult
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.models.selection import Evidence, RiskFlag
from stock_selector.risk import RiskEligibilityDecision
from stock_selector.scoring import BaseScoreStockResult

from .errors import ExplanationDataError


class ExplanationInput(DomainModel):
    """All already-computed, identity-aligned inputs for one selected security."""

    symbol: str
    as_of: datetime
    factor_result: FiveFactorStockResult
    score_result: BaseScoreStockResult
    risk_decision: RiskEligibilityDecision | None = None
    price_factors_operational: bool

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_identity(self) -> "ExplanationInput":
        if (
            self.factor_result.symbol != self.symbol
            or self.score_result.symbol != self.symbol
            or self.factor_result.as_of != self.as_of
            or self.score_result.as_of != self.as_of
        ):
            raise ExplanationDataError("factor and score results must match explanation identity")
        if self.score_result.base_score is None:
            raise ExplanationDataError("official explanation requires a scoreable BaseScore")
        if self.risk_decision is not None:
            if self.risk_decision.symbol != self.symbol:
                raise ExplanationDataError("risk decision symbol must match explanation identity")
            if not self.risk_decision.eligible:
                raise ExplanationDataError("official explanation requires an eligible risk decision")
        return self


class ExplanationResult(DomainModel):
    """Machine-readable evidence and limitations, without free-form narration."""

    symbol: str
    as_of: datetime
    evidence: tuple[Evidence, ...]
    risks: tuple[RiskFlag, ...]
    summary_codes: tuple[str, ...]

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_codes(self) -> "ExplanationResult":
        codes = tuple(item.code for item in self.evidence) + tuple(
            item.code for item in self.risks
        )
        if self.summary_codes != codes or len(set(codes)) != len(codes):
            raise ExplanationDataError("summary codes must match unique evidence and risk codes")
        return self
