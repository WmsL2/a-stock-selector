"""Synthetic immutable factor outputs for BaseScore tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from stock_selector.config.models import FactorsConfig
from stock_selector.factors.models import (
    ComponentUnavailableReason,
    FactorComponentResult,
    FactorFamily,
    FactorFamilyResult,
    FiveFactorCrossSectionResult,
    FiveFactorStockResult,
)
from stock_selector.scoring.models import BaseScoreRequest

AS_OF = datetime(2026, 3, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


def family_result(
    family: FactorFamily, score: float | None, coverage: float = 1.0
) -> FactorFamilyResult:
    if score is None:
        components = (
            FactorComponentResult(
                factor_name=f"{family.value}_0",
                family=family,
                raw_value=None,
                score=None,
                available=False,
                raw_unavailable_reason=ComponentUnavailableReason.MISSING_FINANCIAL,
                preprocessing_unavailable_reason=None,
            ),
        )
        available_components = 0
    else:
        total_components = 4 if coverage == 0.25 else 1
        available_components = int(total_components * coverage)
        components = tuple(
            FactorComponentResult(
                factor_name=f"{family.value}_{index}",
                family=family,
                raw_value=score if index < available_components else None,
                score=score if index < available_components else None,
                available=index < available_components,
                raw_unavailable_reason=(
                    None
                    if index < available_components
                    else ComponentUnavailableReason.MISSING_COMPONENT_VALUE
                ),
                preprocessing_unavailable_reason=None,
            )
            for index in range(total_components)
        )
    return FactorFamilyResult(
        symbol="600519.SH",
        as_of=AS_OF,
        family=family,
        score=score,
        available=score is not None,
        available_components=available_components,
        total_components=len(components),
        component_coverage=coverage if score is not None else 0.0,
        components=components,
    )


def stock_result(
    symbol: str = "600519.SH",
    values: dict[FactorFamily, tuple[float | None, float]] | None = None,
) -> FiveFactorStockResult:
    values = values or {family: (None, 0.0) for family in FactorFamily}
    families = {
        family: family_result(family, *values[family]) for family in FactorFamily
    }
    return FiveFactorStockResult(
        symbol=symbol,
        as_of=AS_OF,
        quality=families[FactorFamily.QUALITY].model_copy(update={"symbol": symbol}),
        value=families[FactorFamily.VALUE].model_copy(update={"symbol": symbol}),
        growth=families[FactorFamily.GROWTH].model_copy(update={"symbol": symbol}),
        momentum=families[FactorFamily.MOMENTUM].model_copy(
            update={"symbol": symbol}
        ),
        low_volatility=families[FactorFamily.LOW_VOLATILITY].model_copy(
            update={"symbol": symbol}
        ),
    )


def request(
    values: dict[FactorFamily, tuple[float | None, float]],
    config: FactorsConfig | None = None,
) -> BaseScoreRequest:
    stock = stock_result(values=values)
    factors = FiveFactorCrossSectionResult(
        as_of=AS_OF, input_count=1, stocks=(stock,)
    )
    return BaseScoreRequest(factors=factors, config=config or FactorsConfig())
