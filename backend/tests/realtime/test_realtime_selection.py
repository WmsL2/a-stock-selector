"""Task 22 deterministic realtime selection-policy contracts."""

from datetime import UTC, datetime
from math import inf, nan

import pytest
from pydantic import ValidationError

from stock_selector.realtime import (
    RealtimeCandidate,
    RealtimeCandidateSnapshotItem,
    RealtimeIntradayFactorDiagnostics,
    RealtimeIntradayFactorFamily,
    RealtimeIntradayFactorItem,
    RealtimeIntradayFactorResult,
    RealtimeIntradayFamilyResult,
    RealtimeIntradayScoreBlocker,
    RealtimeIntradayScoreDiagnostics,
    RealtimeIntradayScoreEngine,
    RealtimeIntradayScoreItem,
    RealtimeIntradayScoreResult,
    RealtimeLightScanItem,
    RealtimeScoreBlocker,
    RealtimeScoreEngine,
    RealtimeScoreResult,
    RealtimeSelectionBlocker,
    RealtimeSelectionDiagnostics,
    RealtimeSelectionEngine,
    RealtimeSelectionItem,
    RealtimeSelectionPolicy,
    RealtimeSelectionResult,
    RealtimeSignalNormalizationItem,
)


def test_default_policy_and_invalid_values() -> None:
    assert RealtimeSelectionPolicy() == RealtimeSelectionPolicy(min_intraday_score=65, top_n=100)
    for values in (
        {"min_intraday_score": nan}, {"min_intraday_score": inf},
        {"min_intraday_score": -1}, {"min_intraday_score": 101},
        {"top_n": 0}, {"top_n": -1},
    ):
        with pytest.raises(ValidationError):
            RealtimeSelectionPolicy(**values)


def test_inclusive_threshold_and_missing_score_diagnostics() -> None:
    result = _select(_scores(
        _upstream_item("000001.SZ", 1, 80, None),
        _upstream_item("000002.SZ", 2, 80, 64.999),
        _upstream_item("000003.SZ", 3, 80, 65),
        _upstream_item("000004.SZ", 4, 80, 65.001),
    ))
    assert _symbols(result) == ["000004.SZ", "000003.SZ"]
    diagnostics = result.diagnostics
    assert (diagnostics.input_items, diagnostics.intraday_score_available_items,
            diagnostics.intraday_score_missing_items, diagnostics.intraday_threshold_qualified_items,
            diagnostics.intraday_threshold_rejected_items, diagnostics.ranking_universe_items,
            diagnostics.selected_items) == (4, 3, 1, 2, 1, 2, 2)


def test_ready_empty_all_missing_and_no_qualified_are_not_blocked() -> None:
    empty = _select(_scores())
    assert empty.diagnostics.selection_ready and empty.items == () and empty.diagnostics.blockers == ()
    all_missing = _select(_scores(_upstream_item("000001.SZ", 1, 80, None)))
    assert all_missing.diagnostics.selection_ready and all_missing.items == ()
    no_qualified = _select(_scores(
        _upstream_item("000001.SZ", 1, 80, None),
        _upstream_item("000002.SZ", 2, 80, 60),
        _upstream_item("000003.SZ", 3, 80, 64),
    ))
    assert no_qualified.diagnostics.selection_ready and no_qualified.items == ()
    assert (no_qualified.diagnostics.intraday_score_available_items,
            no_qualified.diagnostics.intraday_score_missing_items,
            no_qualified.diagnostics.intraday_threshold_rejected_items) == (2, 1, 2)


def test_blocked_realtime_score_has_the_sole_task22_blocker() -> None:
    blocked = _select(_scores(ready=False))
    assert blocked.items == ()
    assert blocked.diagnostics.blockers == (RealtimeSelectionBlocker.REALTIME_SCORE_NOT_READY,)
    assert blocked.diagnostics.upstream_blockers == (RealtimeScoreBlocker.INTRADAY_SCORE_NOT_READY,)


def test_raw_realtime_score_symbol_ties_and_retained_item_drive_ranking() -> None:
    scores = _scores(
        _upstream_item("000003.SZ", 1, 70, 95),
        _upstream_item("000001.SZ", 5, 80, 80),
        _upstream_item("000002.SZ", 10, 90, 70),
    )
    result = _select(scores)
    assert _symbols(result) == ["000002.SZ", "000001.SZ", "000003.SZ"]
    assert [item.realtime_rank for item in result.items] == [1, 2, 3]
    assert result.items[0].score_item is scores.items[2]
    assert result.items[0].score_item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.market_rank == 10


def test_confidence_completeness_and_base_score_do_not_filter_or_rank() -> None:
    high_raw_low_adjusted = _upstream_item(
        "000001.SZ", 1, 90, 70, base_comp=.2, base_conf=.1, partial=True
    )
    low_raw_high_adjusted = _upstream_item("000002.SZ", 2, 75, 70)
    result = _select(_scores(high_raw_low_adjusted, low_raw_high_adjusted))
    assert _symbols(result) == ["000001.SZ", "000002.SZ"]
    assert result.items[0].score_item.confidence_adjusted_score < result.items[1].score_item.confidence_adjusted_score
    assert result.items[0].score_item.intraday_score_item.data_completeness == pytest.approx(.4)
    assert result.items[0].score_item.intraday_score_item.confidence == pytest.approx(.2)


def test_custom_policy_filters_before_ranking_and_truncates() -> None:
    result = _select(
        _scores(
            _upstream_item("000001.SZ", 1, 95, 69),
            _upstream_item("000002.SZ", 2, 80, 70),
            _upstream_item("000003.SZ", 3, 90, 70),
            _upstream_item("000004.SZ", 4, 70, 80),
        ),
        RealtimeSelectionPolicy(min_intraday_score=70, top_n=2),
    )
    assert _symbols(result) == ["000003.SZ", "000002.SZ"]
    assert result.diagnostics.ranking_universe_items == 3
    assert result.diagnostics.selected_items == 2


def test_default_top100_filters_before_ranking_and_resolves_boundary_tie() -> None:
    qualified = tuple(
        _upstream_item(f"{number:06d}.SZ", number, 80, 70)
        for number in range(1, 102)
    )
    below_threshold_high_score = _upstream_item("999999.SZ", 102, 99, 64)
    result = _select(_scores(*qualified, below_threshold_high_score))
    assert result.diagnostics.ranking_universe_items == 101
    assert len(result.items) == 100
    assert [item.realtime_rank for item in result.items] == list(range(1, 101))
    assert _symbols(result)[-1] == "000100.SZ"
    assert "000101.SZ" not in _symbols(result)
    assert "999999.SZ" not in _symbols(result)


def test_selection_and_diagnostics_normal_construction_reject_invalid_states() -> None:
    valid = _select(_scores(
        _upstream_item("000001.SZ", 1, 80, 70),
        _upstream_item("000002.SZ", 2, 90, 70),
    ))
    first, second = valid.items
    below = RealtimeSelectionItem(score_item=_scores(_upstream_item("000003.SZ", 3, 80, 60)).items[0], realtime_rank=1)
    for items, diagnostics, policy in (
        ((first,), _diagnostics(1, 1, selected=0), RealtimeSelectionPolicy()),
        ((below,), _diagnostics(1, 1), RealtimeSelectionPolicy()),
        ((first, first), _diagnostics(2, 2, selected=2), RealtimeSelectionPolicy()),
        ((second, first), _diagnostics(2, 2, selected=2), RealtimeSelectionPolicy()),
        ((first.model_copy(update={"realtime_rank": 2}),), _diagnostics(1, 1), RealtimeSelectionPolicy()),
        ((first,), _diagnostics(1, 1), RealtimeSelectionPolicy(min_intraday_score=80)),
        ((first, second), _diagnostics(2, 2, selected=2), RealtimeSelectionPolicy(top_n=1)),
    ):
        with pytest.raises(ValidationError):
            RealtimeSelectionResult(
                calculation_at=_CALCULATION_AT,
                candidate_as_of=_CANDIDATE_AS_OF,
                policy=policy,
                diagnostics=diagnostics,
                items=items,
            )
    with pytest.raises(ValidationError):
        RealtimeSelectionResult(
            calculation_at=_CANDIDATE_AS_OF,
            candidate_as_of=_CANDIDATE_AS_OF,
            policy=RealtimeSelectionPolicy(),
            diagnostics=valid.diagnostics,
            items=valid.items,
        )
    diagnostic_values = valid.diagnostics.model_dump()
    for update in (
        {"intraday_score_missing_items": 1},
        {"intraday_threshold_rejected_items": 1},
        {"ranking_universe_items": 1},
        {"selected_items": 3},
        {"selection_ready": False},
    ):
        with pytest.raises(ValidationError):
            RealtimeSelectionDiagnostics(**(diagnostic_values | update))


_CALCULATION_AT = datetime(2026, 8, 31, tzinfo=UTC)
_CANDIDATE_AS_OF = datetime(2026, 8, 30, tzinfo=UTC)


def _select(scores: RealtimeScoreResult, policy: RealtimeSelectionPolicy | None = None) -> RealtimeSelectionResult:
    return RealtimeSelectionEngine().select(scores, policy)


def _scores(*items: RealtimeIntradayScoreItem, ready: bool = True) -> RealtimeScoreResult:
    intraday = RealtimeIntradayScoreResult.model_construct(
        calculation_at=_CALCULATION_AT,
        candidate_as_of=_CANDIDATE_AS_OF,
        diagnostics=RealtimeIntradayScoreDiagnostics.model_construct(
            score_ready=ready,
            blockers=() if ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,),
        ),
        items=items,
    )
    return RealtimeScoreEngine().compute(intraday)


def _upstream_item(
    symbol: str,
    market_rank: int,
    base_score: float,
    intraday_score: float | None,
    base_comp: float = .8,
    base_conf: float = .7,
    partial: bool = False,
) -> RealtimeIntradayScoreItem:
    candidate = RealtimeCandidate(
        symbol=symbol,
        as_of=_CANDIDATE_AS_OF,
        base_score=base_score,
        market_rank=market_rank,
        data_completeness=base_comp,
        confidence=base_conf,
    )
    available_families = 2 if partial else 3
    available_weight = .4 if partial else .65
    coverage = .5 if partial else 10 / 13
    score = intraday_score
    families = {
        "relative_strength": _family(RealtimeIntradayFactorFamily.RELATIVE_STRENGTH, score, coverage),
        "activity_liquidity": _family(RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY, None if partial else score, coverage),
        "vwap_trend": _family(RealtimeIntradayFactorFamily.VWAP_TREND, None),
        "short_momentum": _family(RealtimeIntradayFactorFamily.SHORT_MOMENTUM, None),
        "risk_stability": _family(RealtimeIntradayFactorFamily.RISK_STABILITY, score, coverage),
    }
    factor_item = RealtimeIntradayFactorItem.model_construct(
        normalization_item=RealtimeSignalNormalizationItem.model_construct(
            scan_item=RealtimeLightScanItem.model_construct(
                snapshot_item=RealtimeCandidateSnapshotItem.model_construct(candidate=candidate)
            )
        ),
        **families,
        available_families=available_families if score is not None else 0,
        total_families=5,
        family_coverage=available_families / 5 if score is not None else 0,
    )
    factors = RealtimeIntradayFactorResult.model_construct(
        calculation_at=_CALCULATION_AT,
        candidate_as_of=_CANDIDATE_AS_OF,
        diagnostics=RealtimeIntradayFactorDiagnostics.model_construct(factor_ready=True, blockers=()),
        items=(factor_item,),
    )
    item = RealtimeIntradayScoreEngine().compute(factors).items[0]
    assert item.intraday_score == intraday_score
    assert item.data_completeness == pytest.approx(available_weight if score is not None else 0)
    return item


def _diagnostics(input_items: int, qualified: int, selected: int | None = None) -> RealtimeSelectionDiagnostics:
    selected_items = qualified if selected is None else selected
    return RealtimeSelectionDiagnostics(
        calculation_at=_CALCULATION_AT,
        candidate_as_of=_CANDIDATE_AS_OF,
        upstream_realtime_score_ready=True,
        upstream_blockers=(),
        input_items=input_items,
        intraday_score_available_items=input_items,
        intraday_score_missing_items=0,
        intraday_threshold_qualified_items=qualified,
        intraday_threshold_rejected_items=input_items - qualified,
        ranking_universe_items=qualified,
        selected_items=selected_items,
        selection_ready=True,
        blockers=(),
    )


def _symbols(result: RealtimeSelectionResult) -> list[str]:
    return [
        item.score_item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol
        for item in result.items
    ]


def _family(
    family: RealtimeIntradayFactorFamily,
    score: float | None,
    coverage: float = 0.0,
) -> RealtimeIntradayFamilyResult:
    return RealtimeIntradayFamilyResult.model_construct(
        family=family,
        score=score,
        available=score is not None,
        available_components=1 if score is not None else 0,
        total_components=1,
        component_coverage=coverage,
        components=(),
    )
