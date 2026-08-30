"""Pure template-based evidence and limitation generation."""

from stock_selector.factors.models import (
    FactorComponentResult,
    FactorFamily,
    FactorFamilyResult,
)
from stock_selector.models.selection import Evidence, RiskFlag, RiskSeverity
from stock_selector.scoring import FactorWeightContribution

from .models import ExplanationInput, ExplanationResult

LOW_THRESHOLD = 0.50
WARNING_THRESHOLD = 0.80

_FAMILY_LABELS = {
    FactorFamily.QUALITY: "Quality",
    FactorFamily.VALUE: "Value",
    FactorFamily.GROWTH: "Growth",
    FactorFamily.MOMENTUM: "Momentum",
    FactorFamily.LOW_VOLATILITY: "LowVol",
}
_COMPONENT_LABELS = {
    "quality_roe": "ROE",
    "quality_roa": "ROA",
    "quality_gross_margin": "毛利率",
    "quality_net_margin": "净利率",
    "value_earnings_yield": "盈利收益率(1/PE)",
    "value_book_to_price": "账面市值比(1/PB)",
    "value_cashflow_yield": "现金流收益率(1/PCF)",
    "growth_revenue_yoy": "营收同比",
    "growth_net_profit_yoy": "净利润同比",
    "growth_deducted_net_profit_yoy": "扣非净利润同比",
    "momentum_20d": "20日动量",
    "momentum_60d": "60日动量",
    "low_volatility_20d": "20日波动率",
    "low_volatility_60d": "60日波动率",
}
_SEVERITY_ORDER = {RiskSeverity.HIGH: 0, RiskSeverity.WARNING: 1, RiskSeverity.INFO: 2}


class ExplanationEngine:
    """Generate stable structured explanations from completed factor and score results."""

    def explain(self, request: ExplanationInput) -> ExplanationResult:
        """Return deterministic evidence and informational limitations without mutation."""
        families = {family: getattr(request.factor_result, family.value) for family in FactorFamily}
        evidence = self._evidence(request, families)
        risks = self._risks(request, families)
        return ExplanationResult(
            symbol=request.symbol,
            as_of=request.as_of,
            evidence=tuple(evidence),
            risks=tuple(risks),
            summary_codes=tuple(item.code for item in evidence) + tuple(item.code for item in risks),
        )

    def _evidence(
        self,
        request: ExplanationInput,
        families: dict[FactorFamily, FactorFamilyResult],
    ) -> list[Evidence]:
        contributions = [item for item in request.score_result.contributions if item.available]
        contributions.sort(key=lambda item: (-_contribution(item), _family_index(item.family)))
        evidence: list[Evidence] = []
        for contribution in contributions:
            family = contribution.family
            evidence.append(
                Evidence(
                    code=f"family_{family.value}_contribution",
                    message=(
                        f"{_FAMILY_LABELS[family]} 得分 {contribution.family_score:.1f}，"
                        f"对 BaseScore 贡献 {_contribution(contribution):.1f} 分。"
                    ),
                    factor_name=family.value,
                    value=contribution.family_score,
                    contribution=_contribution(contribution),
                )
            )
            evidence.extend(self._component_evidence(family, families[family]))
        return evidence

    def _component_evidence(
        self, family: FactorFamily, result: FactorFamilyResult
    ) -> list[Evidence]:
        available = [item for item in result.components if item.available]
        if not available:
            return []
        strongest = min(available, key=lambda item: (-_score(item), item.factor_name))
        weakest = min(available, key=lambda item: (_score(item), item.factor_name))
        evidence = [_component_item(family, "strength", strongest)]
        if weakest.factor_name != strongest.factor_name:
            evidence.append(_component_item(family, "weakness", weakest))
        return evidence

    def _risks(
        self,
        request: ExplanationInput,
        families: dict[FactorFamily, FactorFamilyResult],
    ) -> list[RiskFlag]:
        risks: list[RiskFlag] = []
        risks.extend(_threshold_risks(request))
        price_missing = (
            not request.price_factors_operational
            and not families[FactorFamily.MOMENTUM].available
            and not families[FactorFamily.LOW_VOLATILITY].available
        )
        for family in FactorFamily:
            result = families[family]
            if not result.available:
                severity = (
                    RiskSeverity.INFO
                    if price_missing and family in {FactorFamily.MOMENTUM, FactorFamily.LOW_VOLATILITY}
                    else RiskSeverity.WARNING
                )
                risks.append(
                    RiskFlag(
                        code=f"missing_{family.value}",
                        message=f"{_FAMILY_LABELS[family]} 当前未参与 BaseScore。",
                        severity=severity,
                    )
                )
            elif result.component_coverage < 1:
                risks.append(
                    RiskFlag(
                        code=f"partial_{family.value}",
                        message=(
                            f"{_FAMILY_LABELS[family]} 使用 {result.available_components}/"
                            f"{result.total_components} 个组件计算。"
                        ),
                        severity=RiskSeverity.INFO,
                    )
                )
        if price_missing:
            risks.append(
                RiskFlag(
                    code="price_factors_unavailable",
                    message="当前本地 operational 日线为 RAW，Momentum 和 LowVol 未参与 BaseScore。",
                    severity=RiskSeverity.WARNING,
                )
            )
        return sorted(risks, key=lambda item: (_SEVERITY_ORDER[item.severity], item.code))


def _threshold_risks(request: ExplanationInput) -> list[RiskFlag]:
    risks: list[RiskFlag] = []
    for code, label, value in (
        ("low_data_completeness", "数据完整度", request.score_result.data_completeness),
        ("low_confidence", "置信度", request.score_result.confidence),
    ):
        if value < LOW_THRESHOLD:
            severity = RiskSeverity.HIGH
        elif value < WARNING_THRESHOLD:
            severity = RiskSeverity.WARNING
        else:
            continue
        risks.append(
            RiskFlag(
                code=code,
                message=f"{label}为 {value * 100:.0f}%。",
                severity=severity,
            )
        )
    return risks


def _component_item(
    family: FactorFamily, kind: str, component: FactorComponentResult
) -> Evidence:
    label = _COMPONENT_LABELS.get(component.factor_name, component.factor_name)
    raw = f" 原始值 {component.raw_value:.3f}，" if component.raw_value is not None else " "
    return Evidence(
        code=f"component_{family.value}_{kind}",
        message=f"{label}{raw}横截面得分 {_score(component):.1f}。",
        factor_name=component.factor_name,
        value=component.raw_value,
        percentile=_score(component),
    )


def _contribution(value: FactorWeightContribution) -> float:
    assert value.weighted_contribution is not None
    return value.weighted_contribution


def _score(value: FactorComponentResult) -> float:
    assert value.score is not None
    return value.score


def _family_index(family: FactorFamily) -> int:
    return tuple(FactorFamily).index(family)
