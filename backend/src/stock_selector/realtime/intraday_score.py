"""Pure Task 20 intraday score composition from already-built factor families."""

from .models import (
    RealtimeIntradayFactorFamily,
    RealtimeIntradayFactorItem,
    RealtimeIntradayFactorResult,
    RealtimeIntradayFamilyWeightContribution,
    RealtimeIntradayScoreBlocker,
    RealtimeIntradayScoreDiagnostics,
    RealtimeIntradayScoreItem,
    RealtimeIntradayScorePolicy,
    RealtimeIntradayScoreResult,
)


class RealtimeIntradayScoreEngine:
    def compute(self, factors: RealtimeIntradayFactorResult, policy: RealtimeIntradayScorePolicy | None = None) -> RealtimeIntradayScoreResult:
        resolved = policy or RealtimeIntradayScorePolicy()
        items = tuple(_item(item, resolved) for item in factors.items) if factors.diagnostics.factor_ready else ()
        diagnostics = RealtimeIntradayScoreDiagnostics(
            calculation_at=factors.calculation_at,
            candidate_as_of=factors.candidate_as_of,
            upstream_factor_ready=factors.diagnostics.factor_ready,
            upstream_blockers=factors.diagnostics.blockers,
            input_items=len(factors.items), output_items=len(items), score_ready=factors.diagnostics.factor_ready,
            blockers=() if factors.diagnostics.factor_ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,),
            intraday_score_available_items=sum(item.intraday_score is not None for item in items),
            intraday_score_unavailable_items=sum(item.intraday_score is None for item in items),
        )
        return RealtimeIntradayScoreResult(calculation_at=factors.calculation_at, candidate_as_of=factors.candidate_as_of, policy=resolved, diagnostics=diagnostics, items=items)


def _item(factor_item: RealtimeIntradayFactorItem, policy: RealtimeIntradayScorePolicy) -> RealtimeIntradayScoreItem:
    inputs = tuple((family, getattr(policy, family.value), getattr(factor_item, family.value)) for family in RealtimeIntradayFactorFamily)
    enabled_weight = sum(group.weight for _, group, _ in inputs if group.enabled)
    available_weight = sum(group.weight for _, group, result in inputs if group.enabled and result.score is not None)
    contributions = tuple(
        RealtimeIntradayFamilyWeightContribution(
            family=family, enabled=group.enabled, configured_weight=group.weight,
            family_score=result.score, family_component_coverage=result.component_coverage,
            available=group.enabled and result.score is not None,
            renormalized_weight=(group.weight / available_weight if group.enabled and result.score is not None else 0.0),
            weighted_contribution=(result.score * group.weight / available_weight if group.enabled and result.score is not None else None),
        ) for family, group, result in inputs
    )
    score = sum(item.weighted_contribution or 0 for item in contributions) if available_weight else None
    confidence = sum(item.configured_weight * item.family_component_coverage for item in contributions if item.available) / enabled_weight
    return RealtimeIntradayScoreItem(
        factor_item=factor_item, intraday_score=score, data_completeness=available_weight / enabled_weight,
        confidence=confidence, confidence_adjusted_score=score * confidence if score is not None else None,
        available_family_weight=available_weight, enabled_family_weight=enabled_weight,
        available_families=sum(item.available for item in contributions), enabled_families=sum(item.enabled for item in contributions), contributions=contributions,
    )
