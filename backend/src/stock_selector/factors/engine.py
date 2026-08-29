"""Pure point-in-time five-family factor engine using Task 10 preprocessing."""

from collections import defaultdict
from statistics import mean

from stock_selector.preprocessing import (
    FactorDirection,
    FactorPreprocessingEngine,
    FactorPreprocessingRequest,
    MissingValuePolicy,
    NeutralizationMode,
    RawFactorObservation,
)

from .errors import FactorDataError
from .metrics import (
    financial_components,
    growth_components,
    price_components,
    value_components,
)
from .models import (
    FactorComponentResult,
    FactorFamily,
    FactorFamilyResult,
    FiveFactorCrossSectionResult,
    FiveFactorRequest,
    FiveFactorStockResult,
    StockFactorInput,
)

_FAMILIES = {
    FactorFamily.QUALITY: (
        financial_components,
        NeutralizationMode.INDUSTRY_PERCENTILE,
        FactorDirection.HIGHER_IS_BETTER,
    ),
    FactorFamily.VALUE: (
        value_components,
        NeutralizationMode.INDUSTRY_PERCENTILE,
        FactorDirection.HIGHER_IS_BETTER,
    ),
    FactorFamily.GROWTH: (
        growth_components,
        NeutralizationMode.INDUSTRY_PERCENTILE,
        FactorDirection.HIGHER_IS_BETTER,
    ),
    FactorFamily.MOMENTUM: (
        price_components,
        NeutralizationMode.NONE,
        FactorDirection.HIGHER_IS_BETTER,
    ),
    FactorFamily.LOW_VOLATILITY: (
        price_components,
        NeutralizationMode.NONE,
        FactorDirection.LOWER_IS_BETTER,
    ),
}


class FiveFactorEngine:
    def compute(self, request: FiveFactorRequest) -> FiveFactorCrossSectionResult:
        stocks = _validate(request)
        raw = {
            stock.symbol: {
                **financial_components(stock),
                **value_components(stock),
                **growth_components(stock),
                **price_components(stock),
            }
            for stock in stocks
        }
        component_results: dict[str, dict[str, FactorComponentResult]] = defaultdict(
            dict
        )
        for family, (_metric, neutralization, direction) in _FAMILIES.items():
            names = [
                name
                for name in next(iter(raw.values()))
                if name.startswith(
                    family.value
                    if family is not FactorFamily.LOW_VOLATILITY
                    else "low_volatility"
                )
            ]
            if family is FactorFamily.MOMENTUM:
                names = ["momentum_20d", "momentum_60d"]
            if family is FactorFamily.LOW_VOLATILITY:
                names = ["low_volatility_20d", "low_volatility_60d"]
            for name in names:
                result = FactorPreprocessingEngine().preprocess(
                    FactorPreprocessingRequest(
                        observations=tuple(
                            RawFactorObservation(
                                symbol=stock.symbol,
                                as_of=stock.as_of,
                                factor_name=name,
                                factor_group=family.value,
                                raw_value=raw[stock.symbol][name].value,
                                industry_key=stock.industry_key,
                                source=raw[stock.symbol][name].source,
                            )
                            for stock in stocks
                        ),
                        missing_policy=MissingValuePolicy.KEEP_MISSING,
                        direction=direction,
                        neutralization=neutralization,
                    )
                )
                for prepared in result.values:
                    evidence = raw[prepared.symbol][name]
                    component_results[prepared.symbol][name] = FactorComponentResult(
                        factor_name=name,
                        family=family,
                        raw_value=evidence.value,
                        score=prepared.score,
                        available=prepared.available,
                        raw_unavailable_reason=evidence.reason,
                        preprocessing_unavailable_reason=prepared.unavailable_reason,
                        source=evidence.source,
                    )
        outputs = []
        for stock in stocks:
            families = {
                family: _family(stock, family, component_results[stock.symbol])
                for family in FactorFamily
            }
            outputs.append(
                FiveFactorStockResult(
                    symbol=stock.symbol,
                    as_of=stock.as_of,
                    quality=families[FactorFamily.QUALITY],
                    value=families[FactorFamily.VALUE],
                    growth=families[FactorFamily.GROWTH],
                    momentum=families[FactorFamily.MOMENTUM],
                    low_volatility=families[FactorFamily.LOW_VOLATILITY],
                )
            )
        return FiveFactorCrossSectionResult(
            as_of=stocks[0].as_of, input_count=len(outputs), stocks=tuple(outputs)
        )


def _validate(request: FiveFactorRequest) -> tuple[StockFactorInput, ...]:
    if not request.stocks:
        raise FactorDataError("stocks must not be empty")
    if len({item.symbol for item in request.stocks}) != len(request.stocks):
        raise FactorDataError("stocks must be unique")
    as_of = request.stocks[0].as_of
    for stock in request.stocks:
        if stock.as_of != as_of:
            raise FactorDataError("stocks must use one as_of")
        if any(
            record is not None and record.available_at > as_of
            for record in (stock.financial_current, stock.financial_prior_year)
        ):
            raise FactorDataError("financial input is from the future")
        if stock.valuation is not None and stock.valuation.as_of > as_of:
            raise FactorDataError("valuation input is from the future")
    return tuple(sorted(request.stocks, key=lambda item: item.symbol))


def _family(
    stock: StockFactorInput,
    family: FactorFamily,
    components: dict[str, FactorComponentResult],
) -> FactorFamilyResult:
    prefix = family.value
    items = tuple(
        item for name, item in sorted(components.items()) if name.startswith(prefix)
    )
    available = tuple(
        item.score for item in items if item.available and item.score is not None
    )
    return FactorFamilyResult(
        symbol=stock.symbol,
        as_of=stock.as_of,
        family=family,
        score=mean(available) if available else None,
        available=bool(available),
        available_components=len(available),
        total_components=len(items),
        component_coverage=len(available) / len(items),
        components=items,
    )
