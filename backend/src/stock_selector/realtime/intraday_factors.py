"""Pure Task 19 directed intraday family calculations from Task 18 percentiles."""

from .models import (
    RealtimeIntradayComponentResult,
    RealtimeIntradayComponentTransformation,
    RealtimeIntradayComponentUnavailableReason,
    RealtimeIntradayFactorBlocker,
    RealtimeIntradayFactorDiagnostics,
    RealtimeIntradayFactorFamily,
    RealtimeIntradayFactorItem,
    RealtimeIntradayFactorResult,
    RealtimeIntradayFamilyResult,
    RealtimeSignalNormalizationItem,
    RealtimeSignalNormalizationResult,
)


class RealtimeIntradayFactorEngine:
    """Map normalized magnitudes to auditable, non-aggregated family scores."""

    def compute(
        self, normalized: RealtimeSignalNormalizationResult
    ) -> RealtimeIntradayFactorResult:
        if not normalized.diagnostics.normalization_ready:
            return _result(normalized, ())
        return _result(normalized, tuple(_item(item) for item in normalized.items))


def _item(normalization_item: RealtimeSignalNormalizationItem) -> RealtimeIntradayFactorItem:
    percentiles = normalization_item.percentiles
    relative_strength = _family(
        RealtimeIntradayFactorFamily.RELATIVE_STRENGTH,
        (
            _source_component(
                "previous_close_strength",
                RealtimeIntradayFactorFamily.RELATIVE_STRENGTH,
                "price_vs_prev_close_pct_percentile",
                percentiles.price_vs_prev_close_pct_percentile,
            ),
            _source_component(
                "open_strength",
                RealtimeIntradayFactorFamily.RELATIVE_STRENGTH,
                "price_vs_open_pct_percentile",
                percentiles.price_vs_open_pct_percentile,
            ),
        ),
    )
    activity_liquidity = _family(
        RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY,
        (
            _source_component(
                "turnover_activity",
                RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY,
                "turnover_rate_pct_percentile",
                percentiles.turnover_rate_pct_percentile,
            ),
            _source_component(
                "volume_ratio_activity",
                RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY,
                "volume_ratio_percentile",
                percentiles.volume_ratio_percentile,
            ),
        ),
    )
    risk_stability = _family(
        RealtimeIntradayFactorFamily.RISK_STABILITY,
        (
            _source_component(
                "session_range_stability",
                RealtimeIntradayFactorFamily.RISK_STABILITY,
                "session_range_pct_percentile",
                percentiles.session_range_pct_percentile,
                RealtimeIntradayComponentTransformation.ONE_HUNDRED_MINUS,
            ),
        ),
    )
    vwap_trend = _minute_family(
        RealtimeIntradayFactorFamily.VWAP_TREND, "vwap_position", "vwap_trend"
    )
    short_momentum = _minute_family(
        RealtimeIntradayFactorFamily.SHORT_MOMENTUM,
        "short_momentum_5m",
        "short_momentum_15m",
    )
    families = (relative_strength, activity_liquidity, vwap_trend, short_momentum, risk_stability)
    available = sum(family.available for family in families)
    return RealtimeIntradayFactorItem(
        normalization_item=normalization_item,
        relative_strength=relative_strength,
        activity_liquidity=activity_liquidity,
        vwap_trend=vwap_trend,
        short_momentum=short_momentum,
        risk_stability=risk_stability,
        available_families=available,
        family_coverage=available / 5,
    )


def _source_component(
    name: str,
    family: RealtimeIntradayFactorFamily,
    source_name: str,
    source_percentile: float | None,
    transformation: RealtimeIntradayComponentTransformation = RealtimeIntradayComponentTransformation.IDENTITY,
) -> RealtimeIntradayComponentResult:
    score = (
        source_percentile
        if transformation is RealtimeIntradayComponentTransformation.IDENTITY
        else (None if source_percentile is None else 100 - source_percentile)
    )
    return RealtimeIntradayComponentResult(
        component_name=name,
        family=family,
        source_percentile_name=source_name,
        source_percentile=source_percentile,
        transformation=transformation,
        score=score,
        available=score is not None,
        unavailable_reason=(
            None
            if score is not None
            else RealtimeIntradayComponentUnavailableReason.MISSING_NORMALIZED_SIGNAL
        ),
    )


def _minute_family(
    family: RealtimeIntradayFactorFamily, *names: str
) -> RealtimeIntradayFamilyResult:
    return _family(
        family,
        tuple(
            RealtimeIntradayComponentResult(
                component_name=name,
                family=family,
                source_percentile_name=None,
                source_percentile=None,
                transformation=RealtimeIntradayComponentTransformation.IDENTITY,
                score=None,
                available=False,
                unavailable_reason=RealtimeIntradayComponentUnavailableReason.MINUTE_DATA_NOT_AVAILABLE,
            )
            for name in names
        ),
    )


def _family(
    family: RealtimeIntradayFactorFamily,
    components: tuple[RealtimeIntradayComponentResult, ...],
) -> RealtimeIntradayFamilyResult:
    available = sum(component.available for component in components)
    score = (
        None
        if not available
        else sum(component.score for component in components if component.score is not None)
        / available
    )
    return RealtimeIntradayFamilyResult(
        family=family,
        score=score,
        available=bool(available),
        available_components=available,
        total_components=len(components),
        component_coverage=available / len(components),
        components=components,
    )


def _result(
    normalized: RealtimeSignalNormalizationResult,
    items: tuple[RealtimeIntradayFactorItem, ...],
) -> RealtimeIntradayFactorResult:
    available = sum(item.available_families for item in items)
    diagnostics = RealtimeIntradayFactorDiagnostics(
        calculation_at=normalized.calculation_at,
        candidate_as_of=normalized.candidate_as_of,
        upstream_normalization_ready=normalized.diagnostics.normalization_ready,
        upstream_blockers=normalized.diagnostics.blockers,
        input_items=len(normalized.items),
        output_items=len(items),
        factor_ready=normalized.diagnostics.normalization_ready,
        blockers=(
            ()
            if normalized.diagnostics.normalization_ready
            else (RealtimeIntradayFactorBlocker.SIGNAL_NORMALIZATION_NOT_READY,)
        ),
        relative_strength_available_items=sum(item.relative_strength.available for item in items),
        activity_liquidity_available_items=sum(item.activity_liquidity.available for item in items),
        vwap_trend_available_items=sum(item.vwap_trend.available for item in items),
        short_momentum_available_items=sum(item.short_momentum.available for item in items),
        risk_stability_available_items=sum(item.risk_stability.available for item in items),
        available_family_values=available,
        total_family_slots=len(normalized.items) * 5,
        overall_family_coverage=(
            None if not normalized.items else available / (len(normalized.items) * 5)
        ),
    )
    return RealtimeIntradayFactorResult(
        calculation_at=normalized.calculation_at,
        candidate_as_of=normalized.candidate_as_of,
        diagnostics=diagnostics,
        items=items,
    )
