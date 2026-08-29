"""Pure conservative risk eligibility tests."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config.models import UniverseConfig
from stock_selector.risk import (
    DatedRiskState,
    RiskDataError,
    RiskEligibilityEvaluator,
    RiskExclusionReason,
)
from stock_selector.universe import UniverseDecision, UniverseSnapshot

AS_OF = date(2026, 8, 29)


def test_known_safe_and_known_risks_are_evaluated_in_fixed_order() -> None:
    snapshot = _structural("000001.SZ", "600519.SH")
    result = RiskEligibilityEvaluator().evaluate(
        snapshot,
        (
            _state("000001.SZ", is_st=False, is_suspended=False, is_delisting_period=False),
            _state("600519.SH", is_st=True, is_suspended=True, is_delisting_period=True),
        ),
        UniverseConfig(),
    )
    assert result.eligible_members == ("000001.SZ",)
    assert result.decisions[1].reasons == (
        RiskExclusionReason.ST,
        RiskExclusionReason.SUSPENDED,
        RiskExclusionReason.DELISTING_PERIOD,
    )


def test_missing_and_unknown_enabled_states_are_never_safe() -> None:
    result = RiskEligibilityEvaluator().evaluate(
        _structural("000001.SZ", "600519.SH"),
        (_state("000001.SZ", is_st=None, is_suspended=False, is_delisting_period=False),),
        UniverseConfig(),
    )
    assert result.risk_complete_members == 0
    assert result.decisions[0].reasons == (RiskExclusionReason.UNKNOWN_RISK_FIELD,)
    assert result.decisions[1].reasons == (RiskExclusionReason.MISSING_RISK_STATE,)


def test_unknown_disabled_field_does_not_block_but_missing_record_does() -> None:
    config = UniverseConfig(exclude_st=False)
    result = RiskEligibilityEvaluator().evaluate(
        _structural("600519.SH"),
        (_state("600519.SH", is_st=None, is_suspended=False, is_delisting_period=False),),
        config,
    )
    assert result.eligible_members == ("600519.SH",)
    assert result.risk_complete_members == 1


@pytest.mark.parametrize("wrong_day", [date(2025, 8, 29), date(2027, 8, 29)])
def test_risk_states_are_exact_date_only_without_carry_forward(wrong_day: date) -> None:
    with pytest.raises(RiskDataError):
        RiskEligibilityEvaluator().evaluate(
            _structural("600519.SH"),
            (_state("600519.SH", as_of=wrong_day),),
            UniverseConfig(),
        )


def test_duplicate_risk_state_is_rejected_and_non_members_not_evaluated() -> None:
    evaluator = RiskEligibilityEvaluator()
    with pytest.raises(RiskDataError):
        evaluator.evaluate(
            _structural("600519.SH"),
            (_state("600519.SH"), _state("600519.SH", is_st=True)),
            UniverseConfig(),
        )
    result = evaluator.evaluate(
        _structural("600519.SH"),
        (_state("600519.SH"), _state("000001.SZ")),
        UniverseConfig(),
    )
    assert [decision.symbol for decision in result.decisions] == ["600519.SH"]


def _structural(*symbols: str) -> UniverseSnapshot:
    decisions = tuple(UniverseDecision(symbol=symbol, included=True) for symbol in sorted(symbols))
    return UniverseSnapshot(
        as_of=AS_OF,
        input_count=len(decisions),
        members=tuple(decision.symbol for decision in decisions),
        decisions=decisions,
    )


def _state(
    symbol: str,
    *,
    as_of: date = AS_OF,
    is_st: bool | None = False,
    is_suspended: bool | None = False,
    is_delisting_period: bool | None = False,
) -> DatedRiskState:
    return DatedRiskState(
        symbol=symbol,
        as_of=as_of,
        is_st=is_st,
        is_suspended=is_suspended,
        is_delisting_period=is_delisting_period,
        observed_at=datetime(2026, 8, 29, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        source="test",
    )
