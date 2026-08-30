"""Domain invariants for immutable BaseScore results."""

import pytest
from pydantic import ValidationError

from stock_selector.factors.models import FactorFamily
from stock_selector.scoring import BaseScoreEngine
from stock_selector.scoring.models import (
    BaseScoreCrossSectionResult,
    BaseScoreStockResult,
    FactorWeightContribution,
)

from .helpers import AS_OF, request


def _result():
    return BaseScoreEngine().compute(
        request(
            {
                FactorFamily.QUALITY: (80, 1),
                FactorFamily.VALUE: (70, 1),
                FactorFamily.GROWTH: (60, 1),
                FactorFamily.MOMENTUM: (None, 0),
                FactorFamily.LOW_VOLATILITY: (None, 0),
            }
        )
    ).stocks[0]


def test_contribution_contract_rejects_invalid_range_and_consistency():
    base = {
        "family": FactorFamily.QUALITY,
        "enabled": True,
        "configured_weight": 0.3,
        "family_score": 80,
        "family_component_coverage": 1,
        "available": True,
        "renormalized_weight": 1,
        "weighted_contribution": 80,
    }
    for changes in (
        {"configured_weight": 1.1},
        {"family_score": 101},
        {"family_component_coverage": 1.1},
        {"renormalized_weight": -0.1},
        {"weighted_contribution": 79},
        {"enabled": False},
    ):
        with pytest.raises(ValidationError):
            FactorWeightContribution(**{**base, **changes})


def test_stock_result_contracts_score_relationships_and_family_order():
    result = _result()
    base = result.model_dump()
    invalid = (
        {"symbol": "600519"},
        {"as_of": AS_OF.replace(tzinfo=None)},
        {"confidence": 0.8},
        {"base_score": None, "confidence_adjusted_score": 10},
        {"available_families": 1},
        {"contributions": tuple(reversed(result.contributions))},
    )
    for changes in invalid:
        with pytest.raises(ValidationError):
            BaseScoreStockResult(**{**base, **changes})


def test_cross_section_requires_count_sorted_unique_and_shared_as_of():
    first = _result().model_copy(update={"symbol": "000001.SZ"})
    second = _result()
    base = {"as_of": AS_OF, "input_count": 2, "stocks": (first, second)}
    invalid = (
        {"input_count": 1},
        {"stocks": (second, first)},
        {"stocks": (first, first)},
        {"stocks": (first, second.model_copy(update={"as_of": AS_OF.replace(day=30)}))},
    )
    for changes in invalid:
        with pytest.raises(ValidationError):
            BaseScoreCrossSectionResult(**{**base, **changes})


def test_naive_datetime_is_rejected_without_constructing_a_clock_value():
    result = _result()
    with pytest.raises(ValidationError):
        BaseScoreCrossSectionResult(
            as_of=AS_OF.replace(tzinfo=None), input_count=1, stocks=(result,)
        )
