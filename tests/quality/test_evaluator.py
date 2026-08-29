"""Pure data-quality freshness and coverage tests."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.quality import (
    DataQualityError,
    DataQualityEvaluator,
    RealtimeFreshness,
)
from stock_selector.risk import RiskEligibilityDecision, RiskEligibilitySnapshot


def test_freshness_boundaries_and_future_protection() -> None:
    evaluator = DataQualityEvaluator()
    now = datetime(2026, 8, 29, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    for age, expected in ((0, RealtimeFreshness.FRESH), (60, RealtimeFreshness.FRESH), (61, RealtimeFreshness.WARNING), (120, RealtimeFreshness.WARNING), (121, RealtimeFreshness.STALE)):
        freshness, measured = evaluator.evaluate_freshness(now - timedelta(seconds=age), now, 60, 120)
        assert (freshness, measured) == (expected, float(age))
    assert evaluator.evaluate_freshness(None, now, 60, 120) == (RealtimeFreshness.UNAVAILABLE, None)
    with pytest.raises(DataQualityError):
        evaluator.evaluate_freshness(now + timedelta(seconds=1), now, 60, 120)


def test_coverage_is_conservative_until_every_structural_member_is_complete() -> None:
    evaluator = DataQualityEvaluator()
    now = datetime(2026, 8, 29, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    incomplete = _snapshot(4, 2, 1)
    status = evaluator.evaluate(incomplete, None, now, 60, 120)
    assert (status.risk_coverage_ratio, status.risk_filter_ready, status.risk_eligible_instruments) == (0.5, False, None)
    ready = evaluator.evaluate(_snapshot(4, 4, 3), None, now, 60, 120)
    assert (ready.risk_filter_ready, ready.risk_eligible_instruments) == (True, 3)


def _snapshot(structural: int, complete: int, eligible: int) -> RiskEligibilitySnapshot:
    symbols = tuple(f"{index:06d}.SH" for index in range(1, structural + 1))
    decisions = tuple(
        RiskEligibilityDecision(
            symbol=symbol,
            eligible=index < eligible,
            risk_complete=index < complete,
            reasons=() if index < eligible else ("missing_risk_state",),
        )
        for index, symbol in enumerate(symbols)
    )
    return RiskEligibilitySnapshot(
        as_of=date(2026, 8, 29),
        structural_members=structural,
        risk_records=complete,
        risk_complete_members=complete,
        eligible_members=symbols[:eligible],
        decisions=decisions,
    )
