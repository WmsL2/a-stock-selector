"""Factories for pure explanation engine tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from stock_selector.explanation import ExplanationInput
from stock_selector.factors.models import (
    ComponentUnavailableReason,
    FactorComponentResult,
    FactorFamily,
    FactorFamilyResult,
    FiveFactorStockResult,
)
from stock_selector.risk import RiskEligibilityDecision
from stock_selector.scoring import BaseScoreStockResult, FactorWeightContribution

AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
SYMBOL = "600519.SH"


def family(
    kind: FactorFamily,
    score: float | None,
    components: tuple[tuple[str, float, float | None], ...] = (),
    total_components: int | None = None,
) -> FactorFamilyResult:
    available = (
        components
        or ((f"{kind.value}_component", score, score),)
        if score is not None
        else components
    )
    total = total_components if total_components is not None else len(available)
    results = tuple(
        FactorComponentResult(
            factor_name=name,
            family=kind,
            raw_value=raw_value,
            score=component_score,
            available=True,
            raw_unavailable_reason=None,
            preprocessing_unavailable_reason=None,
        )
        for name, component_score, raw_value in available
    ) + tuple(
        FactorComponentResult(
            factor_name=f"{kind.value}_missing_{index}",
            family=kind,
            raw_value=None,
            score=None,
            available=False,
            raw_unavailable_reason=ComponentUnavailableReason.MISSING_COMPONENT_VALUE,
            preprocessing_unavailable_reason=None,
        )
        for index in range(total - len(available))
    )
    return FactorFamilyResult(
        symbol=SYMBOL,
        as_of=AS_OF,
        family=kind,
        score=score,
        available=score is not None,
        available_components=len(available),
        total_components=total,
        component_coverage=len(available) / total if total else 0.0,
        components=results,
    )


def explanation_input(
    *,
    quality: FactorFamilyResult | None = None,
    value: FactorFamilyResult | None = None,
    growth: FactorFamilyResult | None = None,
    momentum: FactorFamilyResult | None = None,
    low_volatility: FactorFamilyResult | None = None,
    weights: dict[FactorFamily, float] | None = None,
    price_factors_operational: bool = False,
    risk_decision: RiskEligibilityDecision | None = None,
) -> ExplanationInput:
    factor_result = FiveFactorStockResult(
        symbol=SYMBOL,
        as_of=AS_OF,
        quality=quality or family(FactorFamily.QUALITY, 80),
        value=value or family(FactorFamily.VALUE, 70),
        growth=growth or family(FactorFamily.GROWTH, 60),
        momentum=momentum or family(FactorFamily.MOMENTUM, None),
        low_volatility=low_volatility or family(FactorFamily.LOW_VOLATILITY, None),
    )
    configured = weights or {
        FactorFamily.QUALITY: 0.4,
        FactorFamily.VALUE: 0.3,
        FactorFamily.GROWTH: 0.3,
        FactorFamily.MOMENTUM: 0.0,
        FactorFamily.LOW_VOLATILITY: 0.0,
    }
    enabled_weight = sum(configured.values())
    available_weight = sum(
        configured[item]
        for item in FactorFamily
        if configured[item] and getattr(factor_result, item.value).score is not None
    )
    contributions = tuple(
        FactorWeightContribution(
            family=item,
            enabled=configured[item] > 0,
            configured_weight=configured[item],
            family_score=getattr(factor_result, item.value).score,
            family_component_coverage=getattr(factor_result, item.value).component_coverage,
            available=configured[item] > 0 and getattr(factor_result, item.value).score is not None,
            renormalized_weight=(configured[item] / available_weight if configured[item] and getattr(factor_result, item.value).score is not None else 0.0),
            weighted_contribution=(getattr(factor_result, item.value).score * configured[item] / available_weight if configured[item] and getattr(factor_result, item.value).score is not None else None),
        )
        for item in FactorFamily
    )
    base_score = sum(item.weighted_contribution or 0.0 for item in contributions)
    confidence = sum(
        item.configured_weight * item.family_component_coverage
        for item in contributions
        if item.available
    ) / enabled_weight
    score_result = BaseScoreStockResult(
        symbol=SYMBOL,
        as_of=AS_OF,
        base_score=base_score,
        data_completeness=available_weight / enabled_weight,
        confidence=confidence,
        confidence_adjusted_score=base_score * confidence,
        available_family_weight=available_weight,
        enabled_family_weight=enabled_weight,
        available_families=sum(item.available for item in contributions),
        enabled_families=sum(item.enabled for item in contributions),
        contributions=contributions,
    )
    return ExplanationInput(
        symbol=SYMBOL,
        as_of=AS_OF,
        factor_result=factor_result,
        score_result=score_result,
        risk_decision=risk_decision,
        price_factors_operational=price_factors_operational,
    )
