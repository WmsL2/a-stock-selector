"""Task 20 score composition contracts."""

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
    RealtimeIntradayFamilyWeight,
    RealtimeIntradayFamilyWeightContribution,
    RealtimeIntradayScoreBlocker,
    RealtimeIntradayScoreDiagnostics,
    RealtimeIntradayScoreEngine,
    RealtimeIntradayScoreItem,
    RealtimeIntradayScorePolicy,
    RealtimeIntradayScoreResult,
    RealtimeLightScanItem,
    RealtimeSignalNormalizationItem,
)


def test_default_policy_and_invalid_policies() -> None:
    policy = RealtimeIntradayScorePolicy()
    assert [getattr(policy, family.value).weight for family in RealtimeIntradayFactorFamily] == [0.30, 0.25, 0.20, 0.15, 0.10]
    for value in (-0.1, 1.1, nan, inf):
        with pytest.raises(ValidationError):
            RealtimeIntradayFamilyWeight(weight=value)
    with pytest.raises(ValidationError):
        RealtimeIntradayFamilyWeight(weight=0)
    with pytest.raises(ValidationError):
        RealtimeIntradayScorePolicy(relative_strength=RealtimeIntradayFamilyWeight(weight=0.4))


def test_three_family_and_sina_score_semantics() -> None:
    result = _score(_factors(80, 60, 70))
    item = result.items[0]
    assert item.available_family_weight == pytest.approx(0.65)
    assert item.data_completeness == pytest.approx(0.65)
    assert item.confidence == pytest.approx(0.65)
    assert item.intraday_score == pytest.approx((80 * .30 + 60 * .25 + 70 * .10) / .65)
    assert item.confidence_adjusted_score == pytest.approx(46)
    sina = _score(_factors(80, None, 70)).items[0]
    assert (sina.available_family_weight, sina.data_completeness, sina.confidence, sina.intraday_score, sina.confidence_adjusted_score) == pytest.approx((.4, .4, .4, 77.5, 31))
    assert sina.contributions[1].weighted_contribution is None
    assert sina.contributions[1].renormalized_weight == 0


def test_partial_coverage_affects_confidence_not_main_score_and_no_scores_is_valid() -> None:
    full = _score(_factors(80, 60, 70, rs_coverage=1)).items[0]
    partial = _score(_factors(80, 60, 70, rs_coverage=.5)).items[0]
    assert partial.intraday_score == full.intraday_score
    assert partial.confidence == pytest.approx(.5)
    missing = _score(_factors(None, None, None)).items[0]
    assert (missing.intraday_score, missing.data_completeness, missing.confidence, missing.confidence_adjusted_score) == (None, 0, 0, None)


def test_full_five_family_custom_policy_and_disabled_family() -> None:
    factors = _factors(80, 60, 70, vwap=50, short=40)
    full = _score(factors).items[0]
    assert (full.available_family_weight, full.data_completeness, full.confidence) == (1, 1, 1)
    assert full.intraday_score == pytest.approx(80*.30 + 60*.25 + 50*.20 + 40*.15 + 70*.10)
    policy = RealtimeIntradayScorePolicy(
        relative_strength=RealtimeIntradayFamilyWeight(weight=.50),
        activity_liquidity=RealtimeIntradayFamilyWeight(weight=.30),
        vwap_trend=RealtimeIntradayFamilyWeight(enabled=False, weight=.20),
        short_momentum=RealtimeIntradayFamilyWeight(enabled=False, weight=.15),
        risk_stability=RealtimeIntradayFamilyWeight(weight=.20),
    )
    custom = _score(factors, policy).items[0]
    assert (custom.data_completeness, custom.confidence) == (1, 1)
    assert custom.intraday_score == pytest.approx(80*.5 + 60*.3 + 70*.2)
    assert custom.contributions[2].enabled is False
    assert custom.contributions[2].available is False
    assert custom.contributions[2].weighted_contribution is None


def test_result_and_score_item_normal_construction_rejects_linkage_and_order() -> None:
    result = _score(_factors(80, 60, 70))
    item = result.items[0]
    values = item.model_dump()
    values["factor_item"] = item.factor_item
    assert RealtimeIntradayScoreItem(**values) == item
    bad_evidence = values | {"contributions": (item.contributions[0].model_copy(update={"family_score": 1}), *item.contributions[1:])}
    with pytest.raises(ValidationError):
        RealtimeIntradayScoreItem(**bad_evidence)
    result_values = result.model_dump()
    result_values["diagnostics"] = result.diagnostics
    result_values["items"] = result.items
    assert RealtimeIntradayScoreResult(**result_values) == result
    duplicate = result_values | {"items": (item, item), "diagnostics": result.diagnostics.model_copy(update={"input_items": 2, "output_items": 2, "intraday_score_available_items": 2, "intraday_score_unavailable_items": 0})}
    with pytest.raises(ValidationError):
        RealtimeIntradayScoreResult(**duplicate)


def test_ready_empty_blocked_diagnostics_and_determinism() -> None:
    factors = _factors(80, 60, 70)
    assert _score(factors) == _score(factors)
    empty = _factors(None, None, None, empty=True)
    score = _score(empty)
    assert score.diagnostics.score_ready is True and score.items == ()
    blocked = _factors(None, None, None, ready=False)
    blocked_score = _score(blocked)
    assert blocked_score.diagnostics.score_ready is False and blocked_score.items == ()


def test_result_model_rejects_blocked_duplicate_rank_order_and_policy_mismatch() -> None:
    one = _score(_factors(10, None, None)).items[0]
    two = _score(_factors(90, None, None, symbol="000002.SZ", rank=2)).items[0]
    with pytest.raises(ValidationError):
        _score_result((one,), ready=False)
    with pytest.raises(ValidationError):
        _score_result((one, one))
    with pytest.raises(ValidationError):
        _score_result((two, one))
    other_policy = RealtimeIntradayScorePolicy(
        relative_strength=RealtimeIntradayFamilyWeight(weight=.4),
        activity_liquidity=RealtimeIntradayFamilyWeight(weight=.3),
        vwap_trend=RealtimeIntradayFamilyWeight(enabled=False, weight=.2),
        short_momentum=RealtimeIntradayFamilyWeight(enabled=False, weight=.1),
        risk_stability=RealtimeIntradayFamilyWeight(weight=.3),
    )
    with pytest.raises(ValidationError):
        _score_result((one,), policy=other_policy)


def test_multicandidate_order_mixed_diagnostics_and_timestamps() -> None:
    factors = _factor_result(
        _factors(5, None, None, symbol="000001.SZ", rank=1).items[0],
        _factors(95, None, None, symbol="000002.SZ", rank=2).items[0],
        _factors(None, None, None, symbol="000003.SZ", rank=3).items[0],
    )
    result = _score(factors)
    assert [item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol for item in result.items] == ["000001.SZ", "000002.SZ", "000003.SZ"]
    assert [item.factor_item.normalization_item.scan_item.snapshot_item.candidate.market_rank for item in result.items] == [1, 2, 3]
    assert result.items[1].intraday_score > result.items[0].intraday_score
    assert result.diagnostics.intraday_score_available_items == 2
    assert result.diagnostics.intraday_score_unavailable_items == 1
    assert result.calculation_at != result.candidate_as_of
    assert result.diagnostics.calculation_at == result.calculation_at


@pytest.mark.parametrize(
    "update",
    [
        {"available": False}, {"renormalized_weight": 0.2, "available": False},
        {"weighted_contribution": None}, {"weighted_contribution": 1},
        {"family_score": 101}, {"configured_weight": 2}, {"renormalized_weight": 2},
        {"family_component_coverage": 2},
    ],
)
def test_contribution_normal_construction_rejects_invalid_states(update) -> None:
    valid = _score(_factors(80, None, None)).items[0].contributions[0]
    with pytest.raises(ValidationError):
        RealtimeIntradayFamilyWeightContribution(**(valid.model_dump() | update))


@pytest.mark.parametrize(
    "update",
    [
        {"available_families": 0}, {"enabled_families": 0}, {"available_family_weight": 0},
        {"enabled_family_weight": .5}, {"data_completeness": .2}, {"confidence": .2},
        {"confidence": 1}, {"intraday_score": 1}, {"confidence_adjusted_score": 1},
    ],
)
def test_score_item_normal_construction_rejects_invalid_states(update) -> None:
    valid = _score(_factors(80, 60, 70)).items[0]
    values = valid.model_dump() | update
    values["factor_item"] = valid.factor_item
    with pytest.raises(ValidationError):
        RealtimeIntradayScoreItem(**values)


def test_score_item_rejects_coverage_order_and_renormalized_weight_mismatches() -> None:
    valid = _score(_factors(80, 60, 70)).items[0]
    values = valid.model_dump()
    values["factor_item"] = valid.factor_item
    bad_coverage = values | {"contributions": (valid.contributions[0].model_copy(update={"family_component_coverage": .5}), *valid.contributions[1:])}
    bad_order = values | {"contributions": tuple(reversed(valid.contributions))}
    bad_weight = values | {"contributions": (valid.contributions[0].model_copy(update={"renormalized_weight": .1, "weighted_contribution": 8}), *valid.contributions[1:])}
    for update in (bad_coverage, bad_order, bad_weight):
        with pytest.raises(ValidationError):
            RealtimeIntradayScoreItem(**update)


def _score(factors, policy=None):
    return RealtimeIntradayScoreEngine().compute(factors, policy)


def _factors(relative, activity, risk, rs_coverage=1, vwap=None, short=None, empty=False, ready=True, symbol="000001.SZ", rank=1):
    families = {
        "relative_strength": _family(RealtimeIntradayFactorFamily.RELATIVE_STRENGTH, relative, rs_coverage),
        "activity_liquidity": _family(RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY, activity),
        "vwap_trend": _family(RealtimeIntradayFactorFamily.VWAP_TREND, vwap),
        "short_momentum": _family(RealtimeIntradayFactorFamily.SHORT_MOMENTUM, short),
        "risk_stability": _family(RealtimeIntradayFactorFamily.RISK_STABILITY, risk),
    }
    available = sum(f.available for f in families.values())
    candidate = RealtimeCandidate.model_construct(symbol=symbol, market_rank=rank)
    normalization_item = RealtimeSignalNormalizationItem.model_construct(
        scan_item=RealtimeLightScanItem.model_construct(
            snapshot_item=RealtimeCandidateSnapshotItem.model_construct(candidate=candidate)
        )
    )
    item = RealtimeIntradayFactorItem.model_construct(normalization_item=normalization_item, **families, available_families=available, total_families=5, family_coverage=available / 5)
    return _factor_result(*( () if empty else (item,) ), ready=ready)


def _factor_result(*items, ready=True):
    calculation_at = datetime(2026, 8, 31, tzinfo=UTC)
    candidate_as_of = datetime(2026, 8, 30, tzinfo=UTC)
    return RealtimeIntradayFactorResult.model_construct(
        calculation_at=calculation_at, candidate_as_of=candidate_as_of,
        diagnostics=RealtimeIntradayFactorDiagnostics.model_construct(factor_ready=ready, blockers=()), items=items,
    )


def _score_result(items, ready=True, policy=None):
    calculation_at = datetime(2026, 8, 31, tzinfo=UTC)
    candidate_as_of = datetime(2026, 8, 30, tzinfo=UTC)
    return RealtimeIntradayScoreResult(
        calculation_at=calculation_at, candidate_as_of=candidate_as_of,
        policy=policy or RealtimeIntradayScorePolicy(),
        diagnostics=RealtimeIntradayScoreDiagnostics(
            calculation_at=calculation_at, candidate_as_of=candidate_as_of,
            upstream_factor_ready=ready, upstream_blockers=(), input_items=len(items),
            output_items=len(items), score_ready=ready,
            blockers=() if ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,),
            intraday_score_available_items=sum(item.intraday_score is not None for item in items),
            intraday_score_unavailable_items=sum(item.intraday_score is None for item in items),
        ),
        items=items,
    )


def _family(family, score, coverage=1):
    return RealtimeIntradayFamilyResult.model_construct(family=family, score=score, available=score is not None, available_components=1 if score is not None else 0, total_components=1, component_coverage=coverage, components=())
