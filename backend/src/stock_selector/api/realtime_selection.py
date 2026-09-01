"""Compact HTTP projection for the retained Task25 realtime runtime result."""

from datetime import datetime

from fastapi import HTTPException, status

from stock_selector.api.schemas import (
    RealtimeQuoteResponse,
    RealtimeSelectionDiagnosticsResponse,
    RealtimeSelectionFamilyPolicyResponse,
    RealtimeSelectionItemResponse,
    RealtimeSelectionPolicyResponse,
    RealtimeSelectionResponse,
)
from stock_selector.config import Settings
from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.realtime import RealtimeError, RealtimeSelectionRuntimeService
from stock_selector.storage import LocalMarketRepository


class RealtimeSelectionAPIService:
    """Execute Task25 once and expose only its compact selected-item audit trail."""

    def __init__(
        self,
        repository: LocalMarketRepository,
        settings: Settings,
        provider: RealtimeMarketDataProvider,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._provider = provider

    def build(self, as_of: datetime) -> RealtimeSelectionResponse:
        """Run the canonical runtime once, translating only expected realtime failures."""
        try:
            runtime = RealtimeSelectionRuntimeService(
                self._repository, self._settings, self._provider
            ).run(as_of, calculation_at=None, policy=None)
        except RealtimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="realtime selection unavailable",
            ) from exc

        pipeline = runtime.pipeline
        selection = pipeline.selection
        snapshot = pipeline.snapshot.diagnostics
        slow = runtime.slow_inputs.diagnostics
        instruments = {item.symbol: item for item in self._repository.load_instruments()}
        industries = {
            item.symbol: item.industry_key for item in runtime.slow_inputs.factor_inputs
        }
        return RealtimeSelectionResponse(
            as_of=runtime.as_of,
            calculation_at=runtime.calculation_at,
            selection_ready=selection.diagnostics.selection_ready,
            blockers=[item.value for item in selection.diagnostics.blockers],
            policy=self._policy(runtime.pipeline_policy),
            diagnostics=RealtimeSelectionDiagnosticsResponse(
                structural_members=slow.structural_members,
                risk_records=slow.risk_records,
                risk_complete_members=slow.risk_complete_members,
                risk_coverage_ratio=slow.risk_coverage_ratio,
                risk_eligible_members=slow.risk_eligible_members,
                factor_input_members=slow.factor_input_members,
                base_score_available_members=slow.base_score_available_members,
                price_factors_operational=slow.price_factors_operational,
                capture_scope=(snapshot.capture_scope.value if snapshot.capture_scope else None),
                capture_source=snapshot.capture_source,
                capture_ingested_at=snapshot.capture_ingested_at,
                received_quotes=snapshot.received_quotes,
                source_timestamp_available_quotes=runtime.capture.source_timestamp_available_quotes,
                persisted_quotes=runtime.capture.persisted_quotes,
                freshness=snapshot.freshness.value,
                age_seconds=snapshot.age_seconds,
                freshness_allowed=snapshot.freshness_allowed,
                candidate_ready=pipeline.candidates.diagnostics.candidate_ready,
                candidate_blockers=[item.value for item in pipeline.candidates.diagnostics.blockers],
                candidate_members=snapshot.candidate_members,
                snapshot_ready=snapshot.snapshot_ready,
                snapshot_blockers=[item.value for item in snapshot.blockers],
                scan_ready=pipeline.scan.diagnostics.scan_ready,
                scan_blockers=[item.value for item in pipeline.scan.diagnostics.blockers],
                normalization_ready=pipeline.normalization.diagnostics.normalization_ready,
                normalization_blockers=[item.value for item in pipeline.normalization.diagnostics.blockers],
                factor_ready=pipeline.factors.diagnostics.factor_ready,
                factor_blockers=[item.value for item in pipeline.factors.diagnostics.blockers],
                intraday_score_ready=pipeline.intraday_score.diagnostics.score_ready,
                intraday_score_blockers=[item.value for item in pipeline.intraday_score.diagnostics.blockers],
                realtime_score_ready=pipeline.realtime_score.diagnostics.realtime_score_ready,
                realtime_score_blockers=[item.value for item in pipeline.realtime_score.diagnostics.blockers],
                selection_ready=selection.diagnostics.selection_ready,
                selection_blockers=[item.value for item in selection.diagnostics.blockers],
                intraday_score_available_items=selection.diagnostics.intraday_score_available_items,
                ranking_universe_items=selection.diagnostics.ranking_universe_items,
                selected_items=selection.diagnostics.selected_items,
            ),
            items=[self._item(item, instruments, industries) for item in selection.items],
        )

    @staticmethod
    def _policy(policy) -> RealtimeSelectionPolicyResponse:  # type: ignore[no-untyped-def]
        intraday = policy.intraday_score_policy
        return RealtimeSelectionPolicyResponse(
            candidate_min_base_score=policy.candidate_policy.min_base_score,
            candidate_top_fraction=policy.candidate_policy.top_fraction,
            freshness_normal_max_seconds=policy.freshness_normal_max_seconds,
            freshness_warning_max_seconds=policy.freshness_warning_max_seconds,
            strong_move_pct=policy.light_scan_policy.strong_move_pct,
            high_turnover_rate_pct=policy.light_scan_policy.high_turnover_rate_pct,
            high_volume_ratio=policy.light_scan_policy.high_volume_ratio,
            relative_strength=RealtimeSelectionFamilyPolicyResponse.model_validate(
                intraday.relative_strength.model_dump()
            ),
            activity_liquidity=RealtimeSelectionFamilyPolicyResponse.model_validate(
                intraday.activity_liquidity.model_dump()
            ),
            vwap_trend=RealtimeSelectionFamilyPolicyResponse.model_validate(
                intraday.vwap_trend.model_dump()
            ),
            short_momentum=RealtimeSelectionFamilyPolicyResponse.model_validate(
                intraday.short_momentum.model_dump()
            ),
            risk_stability=RealtimeSelectionFamilyPolicyResponse.model_validate(
                intraday.risk_stability.model_dump()
            ),
            realtime_base_weight=policy.realtime_score_policy.base_weight,
            realtime_intraday_weight=policy.realtime_score_policy.intraday_weight,
            min_intraday_score=policy.selection_policy.min_intraday_score,
            top_n=policy.selection_policy.top_n,
        )

    @staticmethod
    def _item(item, instruments, industries) -> RealtimeSelectionItemResponse:  # type: ignore[no-untyped-def]
        score = item.score_item
        intraday = score.intraday_score_item
        factor = intraday.factor_item
        snapshot = factor.normalization_item.scan_item.snapshot_item
        candidate = snapshot.candidate
        quote = snapshot.quote
        instrument = instruments[candidate.symbol]
        return RealtimeSelectionItemResponse(
            realtime_rank=item.realtime_rank,
            market_rank=candidate.market_rank,
            symbol=candidate.symbol,
            name=instrument.name,
            board=instrument.board.value,
            industry_key=industries.get(candidate.symbol),
            quote=RealtimeQuoteResponse.model_validate(quote.model_dump()),
            base_score=candidate.base_score,
            base_data_completeness=candidate.data_completeness,
            base_confidence=candidate.confidence,
            intraday_score=intraday.intraday_score,
            intraday_data_completeness=intraday.data_completeness,
            intraday_confidence=intraday.confidence,
            intraday_confidence_adjusted_score=intraday.confidence_adjusted_score,
            relative_strength_score=factor.relative_strength.score,
            activity_liquidity_score=factor.activity_liquidity.score,
            vwap_trend_score=factor.vwap_trend.score,
            short_momentum_score=factor.short_momentum.score,
            risk_stability_score=factor.risk_stability.score,
            realtime_score=score.realtime_score,
            realtime_data_completeness=score.data_completeness,
            realtime_confidence=score.confidence,
            realtime_confidence_adjusted_score=score.confidence_adjusted_score,
        )
