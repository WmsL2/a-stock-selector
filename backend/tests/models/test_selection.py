"""Tests for score, explanation, and selection-result records."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.models import (
    Evidence,
    RiskFlag,
    RiskSeverity,
    SelectionResult,
    StockScore,
)


def _as_of() -> datetime:
    """Return one shared timestamp for selection tests."""
    return datetime(2026, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai"))


def _stock_score(**changes: object) -> StockScore:
    """Build a valid selection score with controlled overrides."""
    values: dict[str, object] = {
        "symbol": "600519.SH",
        "as_of": _as_of(),
        "base_score": 80.0,
        "data_completeness": 0.97,
        "confidence": 0.9,
    }
    values.update(changes)
    return StockScore(**values)


def test_evidence_and_risk_flags_validate_content() -> None:
    """Explanations validate percentile range and risk text is required."""
    assert Evidence(code="quality", message="高 ROE", percentile=100).percentile == 100
    assert RiskFlag(code="st", message="ST 风险", severity=RiskSeverity.WARNING).severity is RiskSeverity.WARNING
    with pytest.raises(ValidationError):
        Evidence(code="quality", message="高 ROE", percentile=101)
    with pytest.raises(ValidationError):
        RiskFlag(code="", message="风险", severity=RiskSeverity.HIGH)


def test_stock_score_validates_scores_proportions_and_ranks() -> None:
    """Scores use 0-100 while completeness and confidence use 0-1."""
    assert _stock_score(data_completeness=0, confidence=1).confidence == 1
    for changes in (
        {"base_score": 101.0},
        {"data_completeness": -0.1},
        {"data_completeness": 1.1},
        {"confidence": -0.1},
        {"confidence": 1.1},
        {"market_rank": 0},
    ):
        with pytest.raises(ValidationError):
            _stock_score(**changes)


def test_selection_result_requires_unique_symbols_and_shared_time() -> None:
    """Selection collections keep one timestamp and no duplicate securities."""
    score = _stock_score()
    result = SelectionResult(as_of=_as_of(), strategy_name="base", items=(score,))
    assert result.items == (score,)
    with pytest.raises(ValidationError):
        SelectionResult(as_of=_as_of(), strategy_name="base", items=(score, score))
    with pytest.raises(ValidationError):
        SelectionResult(
            as_of=_as_of(),
            strategy_name="base",
            items=(_stock_score(as_of=_as_of() + timedelta(days=1)),),
        )
