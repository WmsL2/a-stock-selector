"""Validation tests for dated risk observations and decisions."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.risk import (
    DatedRiskState,
    RiskEligibilityDecision,
    RiskExclusionReason,
)


def test_dated_risk_state_requires_information_aware_timestamp_and_symbol() -> None:
    with pytest.raises(ValidationError):
        DatedRiskState(
            symbol="600519.SH",
            as_of=date(2026, 8, 29),
            observed_at=datetime(2026, 8, 29, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
            source="test",
        )
    with pytest.raises(ValidationError):
        DatedRiskState(
            symbol="bad",
            as_of=date(2026, 8, 29),
            is_st=False,
            observed_at=_observed(),
            source="test",
        )


def test_dated_risk_state_preserves_true_false_and_unknown() -> None:
    state = DatedRiskState(
        symbol="600519.SH",
        as_of=date(2026, 8, 29),
        is_st=True,
        is_suspended=False,
        is_delisting_period=None,
        observed_at=_observed(),
        source="test",
    )
    assert (state.is_st, state.is_suspended, state.is_delisting_period) == (True, False, None)


def test_risk_decision_requires_deterministic_reason_semantics() -> None:
    with pytest.raises(ValidationError):
        RiskEligibilityDecision(
            symbol="600519.SH",
            eligible=True,
            risk_complete=False,
        )
    with pytest.raises(ValidationError):
        RiskEligibilityDecision(
            symbol="600519.SH",
            eligible=False,
            risk_complete=True,
            reasons=(RiskExclusionReason.SUSPENDED, RiskExclusionReason.ST),
        )


def _observed() -> datetime:
    return datetime(2026, 8, 29, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
