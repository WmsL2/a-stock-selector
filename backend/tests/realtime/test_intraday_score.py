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
    RealtimeIntradayScoreEngine,
    RealtimeIntradayScorePolicy,
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


def _score(factors):
    return RealtimeIntradayScoreEngine().compute(factors)


def _factors(relative, activity, risk, rs_coverage=1):
    families = {
        "relative_strength": _family(RealtimeIntradayFactorFamily.RELATIVE_STRENGTH, relative, rs_coverage),
        "activity_liquidity": _family(RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY, activity),
        "vwap_trend": _family(RealtimeIntradayFactorFamily.VWAP_TREND, None),
        "short_momentum": _family(RealtimeIntradayFactorFamily.SHORT_MOMENTUM, None),
        "risk_stability": _family(RealtimeIntradayFactorFamily.RISK_STABILITY, risk),
    }
    available = sum(f.available for f in families.values())
    candidate = RealtimeCandidate.model_construct(symbol="000001.SZ", market_rank=1)
    normalization_item = RealtimeSignalNormalizationItem.model_construct(
        scan_item=RealtimeLightScanItem.model_construct(
            snapshot_item=RealtimeCandidateSnapshotItem.model_construct(candidate=candidate)
        )
    )
    item = RealtimeIntradayFactorItem.model_construct(normalization_item=normalization_item, **families, available_families=available, total_families=5, family_coverage=available / 5)
    now = datetime(2026, 8, 31, tzinfo=UTC)
    return RealtimeIntradayFactorResult.model_construct(calculation_at=now, candidate_as_of=now, diagnostics=RealtimeIntradayFactorDiagnostics.model_construct(factor_ready=True, blockers=()), items=(item,))


def _family(family, score, coverage=1):
    return RealtimeIntradayFamilyResult.model_construct(family=family, score=score, available=score is not None, available_components=1 if score is not None else 0, total_components=1, component_coverage=coverage, components=())
