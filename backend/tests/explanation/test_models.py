"""Identity contracts for explanation inputs and outputs."""

from datetime import timedelta

import pytest

from stock_selector.explanation import (
    ExplanationDataError,
    ExplanationEngine,
    ExplanationInput,
)
from stock_selector.risk import RiskEligibilityDecision, RiskExclusionReason

from .conftest import AS_OF, SYMBOL, explanation_input


def test_input_rejects_mismatched_symbol_or_as_of() -> None:
    request = explanation_input()
    with pytest.raises(ExplanationDataError):
        ExplanationInput(
            symbol="000001.SZ",
            as_of=AS_OF,
            factor_result=request.factor_result,
            score_result=request.score_result,
            price_factors_operational=False,
        )
    with pytest.raises(ExplanationDataError):
        ExplanationInput(
            symbol=SYMBOL,
            as_of=AS_OF + timedelta(days=1),
            factor_result=request.factor_result,
            score_result=request.score_result,
            price_factors_operational=False,
        )


def test_input_rejects_ineligible_risk_decision() -> None:
    request = explanation_input()
    with pytest.raises(ExplanationDataError):
        ExplanationInput(
            symbol=SYMBOL,
            as_of=AS_OF,
            factor_result=request.factor_result,
            score_result=request.score_result,
            risk_decision=RiskEligibilityDecision(
                symbol=SYMBOL,
                eligible=False,
                risk_complete=True,
                reasons=(RiskExclusionReason.ST,),
            ),
            price_factors_operational=False,
        )


def test_summary_codes_match_the_stable_evidence_then_risk_order() -> None:
    result = ExplanationEngine().explain(explanation_input())
    assert result.summary_codes == tuple(item.code for item in result.evidence) + tuple(
        item.code for item in result.risks
    )
