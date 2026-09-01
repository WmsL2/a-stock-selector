"""Task 23 application orchestration over immutable Task15-to-Task22 inputs."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from stock_selector.factors import FactorFamily
from stock_selector.models import RealtimeQuote
from stock_selector.realtime import (
    RealtimeCandidatePolicy,
    RealtimeCandidateSnapshotBlocker,
    RealtimeCaptureResult,
    RealtimeCaptureScope,
    RealtimeDataError,
    RealtimeIntradayFamilyWeight,
    RealtimeIntradayScorePolicy,
    RealtimeLightScanPolicy,
    RealtimeScorePolicy,
    RealtimeSelectionApplicationService,
    RealtimeSelectionPipelinePolicy,
    RealtimeSelectionPipelineResult,
    RealtimeSelectionPolicy,
)
from stock_selector.risk import (
    RiskEligibilityDecision,
    RiskEligibilitySnapshot,
    RiskExclusionReason,
)
from stock_selector.scoring import (
    BaseScoreCrossSectionResult,
    BaseScoreStockResult,
    FactorWeightContribution,
)

AS_OF = datetime(2026, 8, 31, 9, tzinfo=UTC)
CALCULATION_AT = AS_OF + timedelta(seconds=10)
_WEIGHTS = {
    FactorFamily.QUALITY: .30,
    FactorFamily.VALUE: .25,
    FactorFamily.GROWTH: .20,
    FactorFamily.MOMENTUM: .15,
    FactorFamily.LOW_VOLATILITY: .10,
}


def test_pipeline_policy_defaults_and_freshness_validation() -> None:
    policy = RealtimeSelectionPipelinePolicy()
    assert (policy.freshness_normal_max_seconds, policy.freshness_warning_max_seconds) == (60, 120)
    for values in (
        {"freshness_normal_max_seconds": 0},
        {"freshness_warning_max_seconds": 0},
        {"freshness_normal_max_seconds": -1},
        {"freshness_normal_max_seconds": 121, "freshness_warning_max_seconds": 120},
    ):
        with pytest.raises(ValidationError):
            RealtimeSelectionPipelinePolicy(**values)
    assert RealtimeSelectionPipelinePolicy(
        freshness_normal_max_seconds=60, freshness_warning_max_seconds=60
    )


def test_complete_pipeline_retains_every_stage_and_custom_policies() -> None:
    policy = _custom_policy()
    result = _run(
        _scores(_score("000001.SZ", 90), _score("000002.SZ", 80)),
        _risk("000001.SZ", "000002.SZ"),
        _capture(_quote("000001.SZ", 1), _quote("000002.SZ", 2)),
        policy=policy,
    )
    assert result.candidates.diagnostics.candidate_ready
    assert result.snapshot.diagnostics.snapshot_ready
    assert result.scan.diagnostics.scan_ready
    assert result.normalization.diagnostics.normalization_ready
    assert result.factors.diagnostics.factor_ready
    assert result.intraday_score.diagnostics.score_ready
    assert result.realtime_score.diagnostics.realtime_score_ready
    assert result.selection.diagnostics.selection_ready
    assert result.selection.items
    assert result.policy == policy
    assert result.candidates.policy == policy.candidate_policy
    assert result.scan.policy == policy.light_scan_policy
    assert result.intraday_score.policy == policy.intraday_score_policy
    assert result.realtime_score.policy == policy.realtime_score_policy
    assert result.selection.policy == policy.selection_policy
    assert result.calculation_at == CALCULATION_AT
    assert result.candidate_as_of == AS_OF
    assert result.calculation_at != result.candidate_as_of
    assert tuple(item.candidate for item in result.snapshot.items) == result.candidates.candidates
    assert tuple(item.snapshot_item for item in result.scan.items) == result.snapshot.items
    assert tuple(item.scan_item for item in result.normalization.items) == result.scan.items
    assert tuple(item.normalization_item for item in result.factors.items) == result.normalization.items
    assert tuple(item.factor_item for item in result.intraday_score.items) == result.factors.items
    assert tuple(item.intraday_score_item for item in result.realtime_score.items) == result.intraday_score.items


def test_candidate_ready_empty_propagates_without_requiring_capture() -> None:
    result = _run(_scores(_score("000001.SZ", 60)), _risk("000001.SZ"), None)
    assert result.candidates.diagnostics.candidate_ready and result.candidates.candidates == ()
    assert result.snapshot.diagnostics.snapshot_ready and result.snapshot.items == ()
    assert result.scan.diagnostics.scan_ready and result.scan.items == ()
    assert result.normalization.diagnostics.normalization_ready and result.normalization.items == ()
    assert result.factors.diagnostics.factor_ready and result.factors.items == ()
    assert result.intraday_score.diagnostics.score_ready and result.intraday_score.items == ()
    assert result.realtime_score.diagnostics.realtime_score_ready and result.realtime_score.items == ()
    assert result.selection.diagnostics.selection_ready and result.selection.items == ()


def test_candidate_blocked_flow_invokes_and_preserves_every_downstream_stage() -> None:
    result = _run(
        _scores(_score("000001.SZ", 80)),
        _risk("000001.SZ", incomplete=("000001.SZ",)),
        None,
    )
    assert not result.candidates.diagnostics.candidate_ready
    assert result.snapshot.diagnostics.blockers == (
        RealtimeCandidateSnapshotBlocker.CANDIDATE_POOL_NOT_READY,
    )
    assert not result.scan.diagnostics.scan_ready
    assert not result.normalization.diagnostics.normalization_ready
    assert not result.factors.diagnostics.factor_ready
    assert not result.intraday_score.diagnostics.score_ready
    assert not result.realtime_score.diagnostics.realtime_score_ready
    assert not result.selection.diagnostics.selection_ready and result.selection.items == ()


def test_snapshot_failures_propagate_without_manual_service_blockers() -> None:
    inputs = _scores(_score("000001.SZ", 90), _score("000002.SZ", 80))
    risk = _risk("000001.SZ", "000002.SZ")
    policy = RealtimeSelectionPipelinePolicy(
        candidate_policy=RealtimeCandidatePolicy(top_fraction=1)
    )
    cases = (
        (
            None,
            CALCULATION_AT,
            (RealtimeCandidateSnapshotBlocker.REALTIME_SNAPSHOT_UNAVAILABLE,),
        ),
        (
            _capture(
                _quote("000001.SZ", 1, ingested_at=AS_OF),
                _quote("000002.SZ", 2, ingested_at=AS_OF),
            ),
            AS_OF + timedelta(seconds=121),
            (RealtimeCandidateSnapshotBlocker.REALTIME_FRESHNESS_NOT_ALLOWED,),
        ),
        (
            _capture(_quote("000001.SZ", 1)),
            CALCULATION_AT,
            (RealtimeCandidateSnapshotBlocker.CANDIDATE_QUOTE_COVERAGE_INCOMPLETE,),
        ),
    )
    for capture, calculation_at, expected in cases:
        result = _run(inputs, risk, capture, calculation_at=calculation_at, policy=policy)
        assert result.snapshot.diagnostics.blockers == expected
        assert not result.selection.diagnostics.selection_ready and result.selection.items == ()


def test_application_propagates_existing_domain_errors_and_is_deterministic() -> None:
    scores = _scores(_score("000001.SZ", 90))
    with pytest.raises(RealtimeDataError, match="as_of"):
        _run(scores, _risk("000001.SZ", as_of=date(2026, 8, 30)), None)
    with pytest.raises(RealtimeDataError, match="timezone-aware"):
        _run(scores, _risk("000001.SZ"), None, calculation_at=AS_OF.replace(tzinfo=None))
    capture = _capture(_quote("000001.SZ", 1))
    risk = _risk("000001.SZ")
    assert _run(scores, risk, capture) == _run(scores, risk, capture)


def test_normal_pipeline_result_construction_rejects_cross_stage_mismatches() -> None:
    valid = _run(
        _scores(_score("000001.SZ", 90), _score("000002.SZ", 80)),
        _risk("000001.SZ", "000002.SZ"),
        _capture(_quote("000001.SZ", 1), _quote("000002.SZ", 2)),
        policy=_custom_policy(),
    )
    other = _run(
        _scores(_score("000001.SZ", 80), _score("000002.SZ", 90)),
        _risk("000001.SZ", "000002.SZ"),
        _capture(_quote("000001.SZ", 2), _quote("000002.SZ", 1)),
        policy=_custom_policy(),
    )
    for update in (
        {"calculation_at": AS_OF},
        {"candidate_as_of": AS_OF - timedelta(days=1)},
        {"policy": valid.policy.model_copy(update={"candidate_policy": RealtimeCandidatePolicy(top_fraction=.5)})},
        {"scan": valid.scan.model_copy(update={"policy": RealtimeLightScanPolicy(strong_move_pct=4)})},
        {"intraday_score": valid.intraday_score.model_copy(update={"policy": RealtimeIntradayScorePolicy(relative_strength=RealtimeIntradayFamilyWeight(weight=.3), activity_liquidity=RealtimeIntradayFamilyWeight(weight=.25), vwap_trend=RealtimeIntradayFamilyWeight(weight=.2), short_momentum=RealtimeIntradayFamilyWeight(weight=.15), risk_stability=RealtimeIntradayFamilyWeight(weight=.1))})},
        {"realtime_score": valid.realtime_score.model_copy(update={"policy": RealtimeScorePolicy(base_weight=.7, intraday_weight=.3)})},
        {"selection": valid.selection.model_copy(update={"policy": RealtimeSelectionPolicy(top_n=2)})},
        {"scan": valid.scan.model_copy(update={"diagnostics": valid.scan.diagnostics.model_copy(update={"upstream_snapshot_ready": False})})},
        {"snapshot": other.snapshot},
        {"selection": other.selection},
    ):
        try:
            _normal_pipeline(valid, **update)
        except ValidationError:
            continue
        raise AssertionError(f"pipeline mismatch was accepted: {update}")


def _run(
    scores: BaseScoreCrossSectionResult,
    risk: RiskEligibilitySnapshot,
    capture: RealtimeCaptureResult | None,
    *,
    calculation_at: datetime = CALCULATION_AT,
    policy: RealtimeSelectionPipelinePolicy | None = None,
) -> RealtimeSelectionPipelineResult:
    return RealtimeSelectionApplicationService().run(
        scores, risk, capture, calculation_at, policy
    )


def _normal_pipeline(
    result: RealtimeSelectionPipelineResult, **update: object
) -> RealtimeSelectionPipelineResult:
    values = result.model_dump() | update
    for field in (
        "policy", "candidates", "snapshot", "scan", "normalization", "factors",
        "intraday_score", "realtime_score", "selection",
    ):
        values.setdefault(field, getattr(result, field))
    return RealtimeSelectionPipelineResult(**values)


def _custom_policy() -> RealtimeSelectionPipelinePolicy:
    return RealtimeSelectionPipelinePolicy(
        candidate_policy=RealtimeCandidatePolicy(min_base_score=0, top_fraction=1),
        freshness_normal_max_seconds=30,
        freshness_warning_max_seconds=90,
        light_scan_policy=RealtimeLightScanPolicy(strong_move_pct=4, high_turnover_rate_pct=4, high_volume_ratio=2),
        intraday_score_policy=RealtimeIntradayScorePolicy(
            relative_strength=RealtimeIntradayFamilyWeight(weight=.4),
            activity_liquidity=RealtimeIntradayFamilyWeight(weight=.2),
            vwap_trend=RealtimeIntradayFamilyWeight(weight=.15),
            short_momentum=RealtimeIntradayFamilyWeight(weight=.15),
            risk_stability=RealtimeIntradayFamilyWeight(weight=.1),
        ),
        realtime_score_policy=RealtimeScorePolicy(base_weight=.8, intraday_weight=.2),
        selection_policy=RealtimeSelectionPolicy(min_intraday_score=0, top_n=1),
    )


def _scores(*stocks: BaseScoreStockResult) -> BaseScoreCrossSectionResult:
    ordered = tuple(sorted(stocks, key=lambda item: item.symbol))
    return BaseScoreCrossSectionResult(as_of=AS_OF, input_count=len(ordered), stocks=ordered)


def _score(symbol: str, base_score: float) -> BaseScoreStockResult:
    return BaseScoreStockResult(
        symbol=symbol,
        as_of=AS_OF,
        base_score=base_score,
        data_completeness=1,
        confidence=1,
        confidence_adjusted_score=base_score,
        available_family_weight=1,
        enabled_family_weight=1,
        available_families=len(FactorFamily),
        enabled_families=len(FactorFamily),
        contributions=tuple(
            FactorWeightContribution(
                family=family,
                enabled=True,
                configured_weight=_WEIGHTS[family],
                family_score=base_score,
                family_component_coverage=1,
                available=True,
                renormalized_weight=_WEIGHTS[family],
                weighted_contribution=base_score * _WEIGHTS[family],
            )
            for family in FactorFamily
        ),
    )


def _risk(
    *symbols: str, incomplete: tuple[str, ...] = (), as_of: date | None = None
) -> RiskEligibilitySnapshot:
    ordered = tuple(sorted(symbols))
    incomplete_symbols = set(incomplete)
    decisions = tuple(
        RiskEligibilityDecision(
            symbol=symbol,
            eligible=symbol not in incomplete_symbols,
            risk_complete=symbol not in incomplete_symbols,
            reasons=()
            if symbol not in incomplete_symbols
            else (RiskExclusionReason.MISSING_RISK_STATE,),
        )
        for symbol in ordered
    )
    return RiskEligibilitySnapshot(
        as_of=as_of or AS_OF.date(),
        structural_members=len(decisions),
        risk_records=len(decisions),
        risk_complete_members=sum(item.risk_complete for item in decisions),
        eligible_members=tuple(item.symbol for item in decisions if item.eligible),
        decisions=decisions,
    )


def _capture(*quotes: RealtimeQuote) -> RealtimeCaptureResult:
    return RealtimeCaptureResult(
        scope=RealtimeCaptureScope.ALL_MARKET,
        requested_symbols=None,
        received_quotes=len(quotes),
        received_symbols=tuple(quote.symbol for quote in quotes),
        source="test:realtime",
        ingested_at=quotes[0].ingested_at,
        source_timestamp_available_quotes=0,
        persist_requested_symbols=(),
        persisted_quotes=0,
        persisted_symbols=(),
        persistence_performed=False,
        quotes=quotes,
    )


def _quote(symbol: str, rank: int, *, ingested_at: datetime = AS_OF + timedelta(seconds=5)) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=10 + rank,
        open=10,
        high=11 + rank,
        low=9,
        prev_close=10,
        volume=1000 * rank,
        amount=10000 * rank,
        change_pct=float(rank),
        turnover_rate=float(rank),
        volume_ratio=float(rank),
        ingested_at=ingested_at,
        source="test:realtime",
    )
