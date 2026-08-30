"""Behavioral tests for the pure deterministic explanation engine."""

import pytest

from stock_selector.explanation import ExplanationEngine
from stock_selector.factors.models import FactorFamily
from stock_selector.models.selection import RiskSeverity

from .conftest import explanation_input, family


def _codes(items) -> list[str]:  # type: ignore[no-untyped-def]
    return [item.code for item in items]


def test_family_contribution_evidence_is_points_and_deterministically_ordered() -> None:
    result = ExplanationEngine().explain(explanation_input())
    family_evidence = [item for item in result.evidence if item.code.startswith("family_")]

    assert [(item.code, item.contribution) for item in family_evidence] == [
        ("family_quality_contribution", 32.0),
        ("family_value_contribution", 21.0),
        ("family_growth_contribution", 18.0),
    ]
    assert "贡献 32.0 分" in family_evidence[0].message
    assert family_evidence[0].contribution != 0.4


def test_component_evidence_selects_only_strongest_and_weakest_once() -> None:
    quality = family(
        FactorFamily.QUALITY,
        60,
        (
            ("quality_roe", 90, 28.3),
            ("quality_roa", 70, 15.0),
            ("quality_gross_margin", 50, 40.0),
            ("quality_net_margin", 30, 10.0),
        ),
    )
    result = ExplanationEngine().explain(explanation_input(quality=quality))

    quality_components = [item for item in result.evidence if item.code.startswith("component_quality")]
    assert [(item.code, item.factor_name, item.value, item.percentile) for item in quality_components] == [
        ("component_quality_strength", "quality_roe", 28.3, 90.0),
        ("component_quality_weakness", "quality_net_margin", 10.0, 30.0),
    ]
    one_component = ExplanationEngine().explain(
        explanation_input(
            quality=family(
                FactorFamily.QUALITY,
                90,
                (("quality_roe", 90, 28.3),),
            )
        )
    )
    assert _codes(one_component.evidence).count("component_quality_strength") == 1
    assert "component_quality_weakness" not in _codes(one_component.evidence)


def test_missing_partial_and_operational_price_limitations_are_structured() -> None:
    quality = family(
        FactorFamily.QUALITY,
        80,
        (
            ("quality_roe", 90, 28.3),
            ("quality_roa", 80, 15.0),
            ("quality_gross_margin", 70, 40.0),
        ),
        total_components=4,
    )
    result = ExplanationEngine().explain(explanation_input(quality=quality))
    risks = {item.code: item for item in result.risks}

    assert risks["partial_quality"].severity is RiskSeverity.INFO
    assert "3/4" in risks["partial_quality"].message
    assert risks["missing_momentum"].severity is RiskSeverity.INFO
    assert risks["missing_low_volatility"].severity is RiskSeverity.INFO
    assert risks["price_factors_unavailable"].severity is RiskSeverity.WARNING
    assert not any(item.code == "family_momentum_contribution" for item in result.evidence)


@pytest.mark.parametrize(
    ("weight", "expected"),
    ((0.4, RiskSeverity.HIGH), (0.5, RiskSeverity.WARNING), (0.8, None)),
)
def test_completeness_thresholds_are_informational(weight: float, expected: RiskSeverity | None) -> None:
    missing_value = family(FactorFamily.VALUE, None, total_components=1)
    result = ExplanationEngine().explain(
        explanation_input(
            value=missing_value,
            weights={
                FactorFamily.QUALITY: weight,
                FactorFamily.VALUE: 1 - weight,
                FactorFamily.GROWTH: 0.0,
                FactorFamily.MOMENTUM: 0.0,
                FactorFamily.LOW_VOLATILITY: 0.0,
            },
        )
    )
    risk = next((item for item in result.risks if item.code == "low_data_completeness"), None)
    assert (risk is None) is (expected is None)
    if expected is not None:
        assert risk.severity is expected


@pytest.mark.parametrize(
    ("available_components", "total_components", "expected"),
    ((4, 10, RiskSeverity.HIGH), (6, 10, RiskSeverity.WARNING), (9, 10, None)),
)
def test_confidence_thresholds_are_informational(
    available_components: int, total_components: int, expected: RiskSeverity | None
) -> None:
    quality = family(
        FactorFamily.QUALITY,
        80,
        tuple((f"quality_{index}", 80, float(index)) for index in range(available_components)),
        total_components=total_components,
    )
    result = ExplanationEngine().explain(
        explanation_input(
            quality=quality,
            weights={
                FactorFamily.QUALITY: 1.0,
                FactorFamily.VALUE: 0.0,
                FactorFamily.GROWTH: 0.0,
                FactorFamily.MOMENTUM: 0.0,
                FactorFamily.LOW_VOLATILITY: 0.0,
            },
        )
    )
    risk = next((item for item in result.risks if item.code == "low_confidence"), None)
    assert (risk is None) is (expected is None)
    if expected is not None:
        assert risk.severity is expected


def test_operational_price_true_does_not_claim_raw_price_limitation() -> None:
    result = ExplanationEngine().explain(explanation_input(price_factors_operational=True))

    assert "missing_momentum" in _codes(result.risks)
    assert "price_factors_unavailable" not in _codes(result.risks)


def test_full_operational_inputs_need_no_extra_data_or_model_risk() -> None:
    result = ExplanationEngine().explain(
        explanation_input(
            momentum=family(FactorFamily.MOMENTUM, 70),
            low_volatility=family(FactorFamily.LOW_VOLATILITY, 70),
            price_factors_operational=True,
        )
    )

    assert result.risks == ()


def test_repeat_input_is_identical_and_does_not_change_input_models() -> None:
    request = explanation_input()
    before = request.model_dump()
    engine = ExplanationEngine()

    first = engine.explain(request)
    second = engine.explain(request)

    assert first == second
    assert request.model_dump() == before
