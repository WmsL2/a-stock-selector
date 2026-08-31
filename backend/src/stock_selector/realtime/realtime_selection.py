"""Pure Task 22 realtime selection policy over an existing RealtimeScoreResult."""

from .models import (
    RealtimeScoreResult,
    RealtimeSelectionBlocker,
    RealtimeSelectionDiagnostics,
    RealtimeSelectionItem,
    RealtimeSelectionPolicy,
    RealtimeSelectionResult,
)


class RealtimeSelectionEngine:
    """Filter on retained IntradayScore, then deterministically rank retained RealTimeScore."""

    def select(
        self,
        scores: RealtimeScoreResult,
        policy: RealtimeSelectionPolicy | None = None,
    ) -> RealtimeSelectionResult:
        resolved = policy or RealtimeSelectionPolicy()
        qualified = (
            tuple(
                item
                for item in scores.items
                if item.intraday_score_item.intraday_score is not None
                and item.intraday_score_item.intraday_score >= resolved.min_intraday_score
            )
            if scores.diagnostics.realtime_score_ready
            else ()
        )
        ranked = tuple(
            sorted(
                qualified,
                key=lambda item: (
                    -item.realtime_score,
                    item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol,
                ),
            )
        )
        selected = ranked[: resolved.top_n]
        items = tuple(
            RealtimeSelectionItem(score_item=item, realtime_rank=index)
            for index, item in enumerate(selected, start=1)
        )
        intraday_scores = tuple(item.intraday_score_item.intraday_score for item in scores.items)
        available = sum(score is not None for score in intraday_scores)
        qualified_count = len(qualified)
        diagnostics = RealtimeSelectionDiagnostics(
            calculation_at=scores.calculation_at,
            candidate_as_of=scores.candidate_as_of,
            upstream_realtime_score_ready=scores.diagnostics.realtime_score_ready,
            upstream_blockers=scores.diagnostics.blockers,
            input_items=len(scores.items),
            intraday_score_available_items=available,
            intraday_score_missing_items=len(scores.items) - available,
            intraday_threshold_qualified_items=qualified_count,
            intraday_threshold_rejected_items=available - qualified_count,
            ranking_universe_items=qualified_count,
            selected_items=len(items),
            selection_ready=scores.diagnostics.realtime_score_ready,
            blockers=(
                ()
                if scores.diagnostics.realtime_score_ready
                else (RealtimeSelectionBlocker.REALTIME_SCORE_NOT_READY,)
            ),
        )
        return RealtimeSelectionResult(
            calculation_at=scores.calculation_at,
            candidate_as_of=scores.candidate_as_of,
            policy=resolved,
            diagnostics=diagnostics,
            items=items,
        )
