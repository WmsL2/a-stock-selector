"""Pure Task 21 composition of retained BaseScore and IntradayScore evidence."""

from .models import (
    RealtimeIntradayScoreItem,
    RealtimeIntradayScoreResult,
    RealtimeScoreBlocker,
    RealtimeScoreDiagnostics,
    RealtimeScoreItem,
    RealtimeScoreLayer,
    RealtimeScoreLayerContribution,
    RealtimeScorePolicy,
    RealtimeScoreResult,
)


class RealtimeScoreEngine:
    """Compose score layers without I/O, clocks, ranking, or filtering."""

    def compute(
        self,
        scores: RealtimeIntradayScoreResult,
        policy: RealtimeScorePolicy | None = None,
    ) -> RealtimeScoreResult:
        resolved = policy or RealtimeScorePolicy()
        items = (
            tuple(_item(item, resolved) for item in scores.items)
            if scores.diagnostics.score_ready
            else ()
        )
        diagnostics = RealtimeScoreDiagnostics(
            calculation_at=scores.calculation_at,
            candidate_as_of=scores.candidate_as_of,
            upstream_intraday_score_ready=scores.diagnostics.score_ready,
            upstream_blockers=scores.diagnostics.blockers,
            input_items=len(scores.items),
            output_items=len(items),
            realtime_score_ready=scores.diagnostics.score_ready,
            blockers=(
                ()
                if scores.diagnostics.score_ready
                else (RealtimeScoreBlocker.INTRADAY_SCORE_NOT_READY,)
            ),
            blended_items=sum(item.available_layers == 2 for item in items),
            base_only_items=sum(item.available_layers == 1 for item in items),
        )
        return RealtimeScoreResult(
            calculation_at=scores.calculation_at,
            candidate_as_of=scores.candidate_as_of,
            policy=resolved,
            diagnostics=diagnostics,
            items=items,
        )


def _item(
    intraday_score_item: RealtimeIntradayScoreItem,
    policy: RealtimeScorePolicy,
) -> RealtimeScoreItem:
    candidate = (
        intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate
    )
    sources = (
        (
            RealtimeScoreLayer.BASE_SCORE,
            policy.base_weight,
            candidate.base_score,
            candidate.data_completeness,
            candidate.confidence,
        ),
        (
            RealtimeScoreLayer.INTRADAY_SCORE,
            policy.intraday_weight,
            intraday_score_item.intraday_score,
            intraday_score_item.data_completeness,
            intraday_score_item.confidence,
        ),
    )
    available_weight = sum(weight for _, weight, score, _, _ in sources if score is not None)
    contributions = tuple(
        RealtimeScoreLayerContribution(
            layer=layer,
            configured_weight=weight,
            source_score=score,
            source_data_completeness=completeness,
            source_confidence=confidence,
            available=score is not None,
            renormalized_weight=weight / available_weight if score is not None else 0.0,
            weighted_contribution=(score * weight / available_weight if score is not None else None),
        )
        for layer, weight, score, completeness, confidence in sources
    )
    realtime_score = sum(item.weighted_contribution or 0.0 for item in contributions)
    data_completeness = sum(
        item.configured_weight * item.source_data_completeness for item in contributions
    )
    confidence = sum(
        item.configured_weight * item.source_confidence for item in contributions
    )
    return RealtimeScoreItem(
        intraday_score_item=intraday_score_item,
        realtime_score=realtime_score,
        data_completeness=data_completeness,
        confidence=confidence,
        confidence_adjusted_score=realtime_score * confidence,
        available_layer_weight=available_weight,
        available_layers=sum(item.available for item in contributions),
        contributions=contributions,
    )
