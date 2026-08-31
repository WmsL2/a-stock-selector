"""Task 21 RealTimeScore composition contracts."""

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
    RealtimeScoreDiagnostics,
    RealtimeScoreEngine,
    RealtimeScoreItem,
    RealtimeScoreLayer,
    RealtimeScoreLayerContribution,
    RealtimeScorePolicy,
    RealtimeScoreResult,
    RealtimeSignalNormalizationItem,
)


def test_default_policy_and_invalid_policy_values() -> None:
    assert RealtimeScorePolicy() == RealtimeScorePolicy(base_weight=.75, intraday_weight=.25)
    for values in (
        {"base_weight": nan}, {"intraday_weight": inf}, {"base_weight": 0},
        {"intraday_weight": 0}, {"base_weight": -0.1}, {"intraday_weight": 1},
        {"base_weight": .8, "intraday_weight": .3},
    ):
        with pytest.raises(ValidationError):
            RealtimeScorePolicy(**values)


def test_default_blend_retains_sources_and_evidence_formulae() -> None:
    result = _compute(_task20_result(_upstream_item(base=80, intraday=60, base_comp=.8, base_conf=.7, intra_comp=.65, intra_conf=.5)))
    item = result.items[0]
    assert item.realtime_score == pytest.approx(75)
    assert item.data_completeness == pytest.approx(.7625)
    assert item.confidence == pytest.approx(.65)
    assert item.confidence_adjusted_score == pytest.approx(48.75)
    assert tuple(contribution.layer for contribution in item.contributions) == tuple(RealtimeScoreLayer)
    assert [contribution.renormalized_weight for contribution in item.contributions] == pytest.approx([.75, .25])
    assert item.intraday_score_item is result.items[0].intraday_score_item


def test_missing_intraday_renormalizes_score_but_not_evidence() -> None:
    result = _compute(_task20_result(_upstream_item(base=80, intraday=None, base_comp=.8, base_conf=.7, intra_comp=0, intra_conf=0)))
    item = result.items[0]
    base, intraday = item.contributions
    assert item.realtime_score == pytest.approx(80)
    assert item.available_layer_weight == pytest.approx(.75)
    assert (base.renormalized_weight, intraday.renormalized_weight, intraday.weighted_contribution) == (1, 0, None)
    assert item.data_completeness == pytest.approx(.60)
    assert item.confidence == pytest.approx(.525)
    assert item.confidence_adjusted_score == pytest.approx(42)
    assert item.realtime_score != pytest.approx(60)


def test_custom_policy_and_mixed_diagnostics_preserve_order_without_filtering() -> None:
    scores = _task20_result(
        _upstream_item(symbol="000001.SZ", rank=1, base=20, intraday=None),
        _upstream_item(symbol="000002.SZ", rank=2, base=90, intraday=100),
        _upstream_item(symbol="000003.SZ", rank=3, base=70, intraday=10),
    )
    result = _compute(scores, RealtimeScorePolicy(base_weight=.8, intraday_weight=.2))
    assert [candidate.symbol for candidate in _candidates(result)] == ["000001.SZ", "000002.SZ", "000003.SZ"]
    assert [candidate.market_rank for candidate in _candidates(result)] == [1, 2, 3]
    assert [item.realtime_score for item in result.items] == pytest.approx([20, 92, 58])
    assert result.diagnostics.blended_items == 2
    assert result.diagnostics.base_only_items == 1
    assert result.items[1].intraday_score_item is scores.items[1]


def test_ready_empty_blocked_and_deterministic_behavior() -> None:
    ready_empty = _compute(_task20_result())
    assert ready_empty.diagnostics.realtime_score_ready is True
    assert ready_empty.items == () and ready_empty.diagnostics.blockers == ()
    blocked = _compute(_task20_result(ready=False))
    assert blocked.items == ()
    assert blocked.diagnostics.blockers == (RealtimeScoreBlocker.INTRADAY_SCORE_NOT_READY,)
    assert blocked.diagnostics.upstream_blockers == (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,)
    source = _task20_result(_upstream_item(base=75, intraday=55))
    assert _compute(source) == _compute(source)
    assert _compute(source).calculation_at != _compute(source).candidate_as_of


@pytest.mark.parametrize(
    "update",
    [
        {"available": False}, {"source_score": None}, {"renormalized_weight": .1, "available": False},
        {"weighted_contribution": 1, "available": False}, {"weighted_contribution": None},
        {"weighted_contribution": 1}, {"source_score": 101}, {"configured_weight": 2},
        {"source_data_completeness": 1.1}, {"source_confidence": 1},
    ],
)
def test_contribution_normal_construction_rejects_invalid_states(update: dict[str, object]) -> None:
    valid = _compute(_task20_result(_upstream_item())).items[0].contributions[0]
    with pytest.raises(ValidationError):
        RealtimeScoreLayerContribution(**(valid.model_dump() | update))


@pytest.mark.parametrize(
    "update",
    [
        {"total_layers": 1}, {"available_layers": 0}, {"available_layer_weight": .5},
        {"realtime_score": 1}, {"data_completeness": .1}, {"confidence": .1},
        {"confidence": 1}, {"confidence_adjusted_score": 1},
    ],
)
def test_item_normal_construction_rejects_invariants(update: dict[str, object]) -> None:
    valid = _compute(_task20_result(_upstream_item())).items[0]
    values = valid.model_dump() | update
    values["intraday_score_item"] = valid.intraday_score_item
    with pytest.raises(ValidationError):
        RealtimeScoreItem(**values)
    for contributions in (
        tuple(reversed(valid.contributions)),
        (valid.contributions[0].model_copy(update={"source_score": 1, "weighted_contribution": .75}), valid.contributions[1]),
        (valid.contributions[0].model_copy(update={"renormalized_weight": .5, "weighted_contribution": 40}), valid.contributions[1]),
    ):
        values = valid.model_dump()
        values["intraday_score_item"] = valid.intraday_score_item
        values["contributions"] = contributions
        with pytest.raises(ValidationError):
            RealtimeScoreItem(**values)


@pytest.mark.parametrize(
    "index, update",
    [
        (0, {"source_score": 81, "weighted_contribution": 60.75}),
        (0, {"source_data_completeness": .9}),
        (0, {"source_confidence": .6}),
        (1, {"source_score": 61, "weighted_contribution": 15.25}),
        (1, {"source_data_completeness": .7}),
        (1, {"source_confidence": .4}),
    ],
)
def test_item_normal_construction_rejects_all_upstream_source_mismatches(
    index: int, update: dict[str, object]
) -> None:
    valid = _compute(_task20_result(_upstream_item())).items[0]
    contributions = list(valid.contributions)
    contributions[index] = contributions[index].model_copy(update=update)
    values = valid.model_dump()
    values["intraday_score_item"] = valid.intraday_score_item
    values["contributions"] = tuple(contributions)
    with pytest.raises(ValidationError):
        RealtimeScoreItem(**values)


def test_intraday_contribution_normal_construction_rejects_missing_score_cross_states() -> None:
    missing = _compute(_task20_result(_upstream_item(intraday=None))).items[0].contributions[1]
    for update in (
        {"available": True},
        {"renormalized_weight": .25},
        {"weighted_contribution": 1},
    ):
        with pytest.raises(ValidationError):
            RealtimeScoreLayerContribution(**(missing.model_dump() | update))


def test_result_normal_construction_rejects_blocked_duplicates_rank_policy_and_counts() -> None:
    first = _compute(_task20_result(_upstream_item(symbol="000001.SZ", rank=1))).items[0]
    second = _compute(_task20_result(_upstream_item(symbol="000002.SZ", rank=2))).items[0]
    with pytest.raises(ValidationError):
        _result((first,), ready=False)
    with pytest.raises(ValidationError):
        _result((first, first))
    with pytest.raises(ValidationError):
        _result((second, first))
    with pytest.raises(ValidationError):
        _result((first,), policy=RealtimeScorePolicy(base_weight=.8, intraday_weight=.2))
    invalid_diagnostics = _diagnostics(1, ready=True).model_copy(update={"output_items": 2})
    with pytest.raises(ValidationError):
        RealtimeScoreResult(
            calculation_at=_CALCULATION_AT, candidate_as_of=_CANDIDATE_AS_OF,
            policy=RealtimeScorePolicy(), diagnostics=invalid_diagnostics, items=(first,),
        )


_CALCULATION_AT = datetime(2026, 8, 31, tzinfo=UTC)
_CANDIDATE_AS_OF = datetime(2026, 8, 30, tzinfo=UTC)


def _compute(scores: RealtimeIntradayScoreResult, policy: RealtimeScorePolicy | None = None) -> RealtimeScoreResult:
    return RealtimeScoreEngine().compute(scores, policy)


def _upstream_item(symbol: str = "000001.SZ", rank: int = 1, base: float = 80, intraday: float | None = 60, base_comp: float = .8, base_conf: float = .7, intra_comp: float = .65, intra_conf: float = .5) -> RealtimeIntradayScoreItem:
    candidate = RealtimeCandidate(symbol=symbol, as_of=_CANDIDATE_AS_OF, base_score=base, market_rank=rank, data_completeness=base_comp, confidence=base_conf)
    score = intraday if intraday is not None else None
    coverage = intra_conf / intra_comp if score is not None else 0.0
    families = {
        "relative_strength": _family(RealtimeIntradayFactorFamily.RELATIVE_STRENGTH, score, coverage),
        "activity_liquidity": _family(RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY, score, coverage),
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
        available_families=3 if score is not None else 0,
        total_families=5,
        family_coverage=.6 if score is not None else 0,
    )
    factors = RealtimeIntradayFactorResult.model_construct(
        calculation_at=_CALCULATION_AT,
        candidate_as_of=_CANDIDATE_AS_OF,
        diagnostics=RealtimeIntradayFactorDiagnostics.model_construct(factor_ready=True, blockers=()),
        items=(factor_item,),
    )
    item = RealtimeIntradayScoreEngine().compute(factors).items[0]
    assert item.intraday_score == intraday
    assert item.data_completeness == pytest.approx(intra_comp if score is not None else 0)
    assert item.confidence == pytest.approx(intra_conf if score is not None else 0)
    return item


def _task20_result(*items: RealtimeIntradayScoreItem, ready: bool = True) -> RealtimeIntradayScoreResult:
    blockers = () if ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,)
    return RealtimeIntradayScoreResult.model_construct(
        calculation_at=_CALCULATION_AT, candidate_as_of=_CANDIDATE_AS_OF,
        diagnostics=RealtimeIntradayScoreDiagnostics.model_construct(
            score_ready=ready, blockers=blockers
        ),
        items=items,
    )


def _diagnostics(count: int, ready: bool) -> RealtimeScoreDiagnostics:
    return RealtimeScoreDiagnostics(
        calculation_at=_CALCULATION_AT, candidate_as_of=_CANDIDATE_AS_OF,
        upstream_intraday_score_ready=ready,
        upstream_blockers=() if ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,),
        input_items=count, output_items=count, realtime_score_ready=ready,
        blockers=() if ready else (RealtimeScoreBlocker.INTRADAY_SCORE_NOT_READY,),
        blended_items=count, base_only_items=0,
    )


def _result(items: tuple[RealtimeScoreItem, ...], ready: bool = True, policy: RealtimeScorePolicy | None = None) -> RealtimeScoreResult:
    return RealtimeScoreResult(
        calculation_at=_CALCULATION_AT, candidate_as_of=_CANDIDATE_AS_OF,
        policy=policy or RealtimeScorePolicy(), diagnostics=_diagnostics(len(items), ready), items=items,
    )


def _candidates(result: RealtimeScoreResult) -> list[RealtimeCandidate]:
    return [item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate for item in result.items]


def _family(
    family: RealtimeIntradayFactorFamily, score: float | None, coverage: float = 0.0
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
