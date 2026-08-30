"""Behavioral tests for configured BaseScore composition."""

import math
from datetime import date, timedelta

import pytest

from stock_selector.config.models import FactorsConfig
from stock_selector.factors import (
    AdjustedClosePoint,
    FactorFamily,
    FiveFactorEngine,
    FiveFactorRequest,
    PriceSeriesInput,
    StockFactorInput,
)
from stock_selector.models import FinancialRecord, ValuationRecord
from stock_selector.scoring import BaseScoreEngine
from stock_selector.scoring.models import BaseScoreRequest

from .helpers import AS_OF, request, stock_result


def _values(
    quality: tuple[float | None, float],
    value: tuple[float | None, float],
    growth: tuple[float | None, float],
    momentum: tuple[float | None, float],
    low_volatility: tuple[float | None, float],
) -> dict[FactorFamily, tuple[float | None, float]]:
    return {
        FactorFamily.QUALITY: quality,
        FactorFamily.VALUE: value,
        FactorFamily.GROWTH: growth,
        FactorFamily.MOMENTUM: momentum,
        FactorFamily.LOW_VOLATILITY: low_volatility,
    }


def test_full_availability_uses_configured_weights_and_contributions() -> None:
    result = BaseScoreEngine().compute(
        request(_values((80, 1), (60, 1), (70, 1), (90, 1), (50, 1)))
    ).stocks[0]
    assert result.base_score == 71.5
    assert result.data_completeness == result.confidence == 1
    assert result.confidence_adjusted_score == 71.5
    assert [item.renormalized_weight for item in result.contributions] == [
        0.30,
        0.25,
        0.20,
        0.15,
        0.10,
    ]
    assert [item.weighted_contribution for item in result.contributions] == [
        24.0,
        15.0,
        14.0,
        13.5,
        5.0,
    ]


def test_missing_families_renormalize_without_component_coverage_penalty() -> None:
    result = BaseScoreEngine().compute(
        request(_values((80, 0.25), (70, 1), (60, 1), (None, 0), (None, 0)))
    ).stocks[0]
    assert result.available_family_weight == pytest.approx(0.75)
    assert result.base_score == pytest.approx((80 * 0.30 + 70 * 0.25 + 60 * 0.20) / 0.75)
    assert result.data_completeness == pytest.approx(0.75)
    assert result.confidence == pytest.approx(0.525)
    assert result.confidence < result.data_completeness
    assert result.confidence_adjusted_score == pytest.approx(result.base_score * 0.525)
    assert [item.renormalized_weight for item in result.contributions] == pytest.approx(
        [0.30 / 0.75, 0.25 / 0.75, 0.20 / 0.75, 0, 0]
    )
    assert sum(item.renormalized_weight for item in result.contributions) == pytest.approx(
        1.0
    )
    assert sum(
        item.weighted_contribution or 0 for item in result.contributions
    ) == pytest.approx(result.base_score)


def test_one_partial_and_no_available_family_semantics() -> None:
    engine = BaseScoreEngine()
    one = engine.compute(
        request(_values((82, 1), (None, 0), (None, 0), (None, 0), (None, 0)))
    ).stocks[0]
    assert (one.base_score, one.data_completeness, one.confidence) == (82, 0.3, 0.3)
    assert one.confidence_adjusted_score == pytest.approx(24.6)

    partial = engine.compute(
        request(
            _values((82, 0.25), (None, 0), (None, 0), (None, 0), (None, 0))
        )
    ).stocks[0]
    assert (partial.base_score, partial.data_completeness, partial.confidence) == (
        82,
        0.3,
        0.075,
    )
    assert partial.confidence_adjusted_score == pytest.approx(82 * 0.075)

    unavailable = engine.compute(
        request(_values((None, 0), (None, 0), (None, 0), (None, 0), (None, 0)))
    ).stocks[0]
    assert unavailable.base_score is None
    assert unavailable.confidence_adjusted_score is None
    assert (
        unavailable.data_completeness,
        unavailable.confidence,
        unavailable.available_family_weight,
        unavailable.available_families,
    ) == (0, 0, 0, 0)
    assert all(item.renormalized_weight == 0 for item in unavailable.contributions)


def test_disabled_families_are_excluded_from_all_score_denominators() -> None:
    config = FactorsConfig(
        quality={"enabled": True, "weight": 0.40},
        value={"enabled": True, "weight": 0.30},
        growth={"enabled": True, "weight": 0.30},
        momentum={"enabled": False, "weight": 0.15},
        low_volatility={"enabled": False, "weight": 0.10},
    )
    result = BaseScoreEngine().compute(
        request(
            _values((80, 1), (70, 1), (60, 1), (100, 1), (100, 1)), config
        )
    ).stocks[0]
    assert result.base_score == pytest.approx(80 * 0.4 + 70 * 0.3 + 60 * 0.3)
    assert result.data_completeness == result.confidence == 1
    momentum, low_volatility = result.contributions[-2:]
    assert (momentum.enabled, momentum.available, momentum.renormalized_weight) == (
        False,
        False,
        0,
    )
    assert momentum.weighted_contribution is None
    assert low_volatility.weighted_contribution is None


def test_output_is_symbol_ordered_and_deterministic() -> None:
    values = _values((80, 1), (70, 1), (60, 1), (None, 0), (None, 0))
    factors = request(values).factors
    first = stock_result("000001.SZ", values)
    second = stock_result("600519.SH", values)
    ordered = factors.model_copy(
        update={"input_count": 2, "stocks": (first, second)}
    )
    scored = BaseScoreEngine().compute(
        BaseScoreRequest(factors=ordered, config=FactorsConfig())
    )
    assert tuple(item.symbol for item in scored.stocks) == ("000001.SZ", "600519.SH")
    assert scored == BaseScoreEngine().compute(
        BaseScoreRequest(factors=ordered, config=FactorsConfig())
    )


def _financial(symbol: str, period: date, **values: float) -> FinancialRecord:
    return FinancialRecord(
        symbol=symbol,
        report_period=period,
        announcement_date=date(2026, 2, 1),
        available_at=AS_OF - timedelta(days=1),
        roe=values.get("roe"),
        roa=values.get("roa"),
        gross_margin=values.get("gross_margin"),
        net_margin=values.get("net_margin"),
        revenue=values.get("revenue"),
        net_profit=values.get("net_profit"),
        deducted_net_profit=values.get("deducted_net_profit"),
        source="synthetic",
    )


def test_task11_integration_renormalizes_unadjusted_price_families() -> None:
    symbol = "600519.SH"
    current = _financial(
        symbol,
        date(2025, 12, 31),
        roe=80,
        roa=70,
        gross_margin=60,
        net_margin=50,
        revenue=120,
        net_profit=110,
        deducted_net_profit=105,
    )
    prior = _financial(
        symbol,
        date(2024, 12, 31),
        roe=1,
        roa=1,
        gross_margin=1,
        net_margin=1,
        revenue=100,
        net_profit=100,
        deducted_net_profit=100,
    )
    factors = FiveFactorEngine().compute(
        FiveFactorRequest(
            stocks=(
                StockFactorInput(
                    symbol=symbol,
                    as_of=AS_OF,
                    industry_key="A",
                    financial_current=current,
                    financial_prior_year=prior,
                    valuation=ValuationRecord(
                        symbol=symbol,
                        as_of=AS_OF,
                        pe=10,
                        pb=2,
                        pcf=5,
                        source="synthetic",
                    ),
                    price_series=PriceSeriesInput(
                        symbol=symbol,
                        as_of=AS_OF,
                        points=(
                            AdjustedClosePoint(
                                trade_date=AS_OF.date() - timedelta(days=1), close=10
                            ),
                        ),
                        corporate_action_adjusted=False,
                        source="synthetic",
                    ),
                ),
            )
        )
    )
    result = BaseScoreEngine().compute(
        BaseScoreRequest(factors=factors, config=FactorsConfig())
    ).stocks[0]
    assert result.base_score is not None
    assert result.data_completeness == pytest.approx(0.75)
    assert result.confidence == pytest.approx(0.75)
    assert math.isclose(
        result.base_score,
        sum(item.weighted_contribution or 0 for item in result.contributions),
    )
