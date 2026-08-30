"""Pure configured-weight BaseScore composition with no runtime integrations."""

from stock_selector.factors.models import FactorFamily, FiveFactorStockResult

from .models import (
    BaseScoreCrossSectionResult,
    BaseScoreRequest,
    BaseScoreStockResult,
    FactorWeightContribution,
)


class BaseScoreEngine:
    """Compose immutable five-factor outputs using caller-supplied configuration."""

    def compute(self, request: BaseScoreRequest) -> BaseScoreCrossSectionResult:
        return BaseScoreCrossSectionResult(
            as_of=request.factors.as_of,
            input_count=request.factors.input_count,
            stocks=tuple(
                self._score_stock(stock, request)
                for stock in request.factors.stocks
            ),
        )

    @staticmethod
    def _score_stock(
        stock: FiveFactorStockResult, request: BaseScoreRequest
    ) -> BaseScoreStockResult:
        family_inputs = tuple(
            (
                family,
                getattr(request.config, family.value),
                getattr(stock, family.value),
            )
            for family in FactorFamily
        )
        enabled_weight = sum(
            group.weight for _family, group, _result in family_inputs if group.enabled
        )
        available_weight = sum(
            group.weight
            for _family, group, result in family_inputs
            if group.enabled and result.score is not None
        )
        contributions = tuple(
            FactorWeightContribution(
                family=family,
                enabled=group.enabled,
                configured_weight=group.weight,
                family_score=result.score,
                family_component_coverage=result.component_coverage,
                available=group.enabled and result.score is not None,
                renormalized_weight=(
                    group.weight / available_weight
                    if group.enabled
                    and result.score is not None
                    and available_weight
                    else 0.0
                ),
                weighted_contribution=(
                    result.score * group.weight / available_weight
                    if group.enabled
                    and result.score is not None
                    and available_weight
                    else 0.0
                    if group.enabled and result.score is not None
                    else None
                ),
            )
            for family, group, result in family_inputs
        )
        base_score = (
            sum(item.weighted_contribution or 0 for item in contributions)
            if available_weight
            else None
        )
        confidence = (
            sum(
                item.configured_weight * item.family_component_coverage
                for item in contributions
                if item.available
            )
            / enabled_weight
        )
        return BaseScoreStockResult(
            symbol=stock.symbol,
            as_of=stock.as_of,
            base_score=base_score,
            data_completeness=available_weight / enabled_weight,
            confidence=confidence,
            confidence_adjusted_score=(
                base_score * confidence if base_score is not None else None
            ),
            available_family_weight=available_weight,
            enabled_family_weight=enabled_weight,
            available_families=sum(item.available for item in contributions),
            enabled_families=sum(item.enabled for item in contributions),
            contributions=contributions,
        )
