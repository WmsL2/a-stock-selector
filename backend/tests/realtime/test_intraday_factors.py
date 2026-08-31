"""Task 19 intraday-family behavior over Task 18 normalized input only."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stock_selector.realtime import (
    RealtimeCandidate,
    RealtimeCandidateSnapshotItem,
    RealtimeIntradayComponentResult,
    RealtimeIntradayComponentTransformation,
    RealtimeIntradayComponentUnavailableReason,
    RealtimeIntradayFactorBlocker,
    RealtimeIntradayFactorEngine,
    RealtimeIntradayFactorFamily,
    RealtimeIntradayFactorItem,
    RealtimeIntradayFamilyResult,
    RealtimeLightScanItem,
    RealtimeSignalNormalizationDiagnostics,
    RealtimeSignalNormalizationItem,
    RealtimeSignalNormalizationResult,
    RealtimeSignalPercentiles,
)


def test_canonical_family_formulas_and_component_shapes() -> None:
    result = _compute(
        _normalized(
            price_vs_open_pct_percentile=60,
            price_vs_prev_close_pct_percentile=80,
            session_range_pct_percentile=25,
            turnover_rate_pct_percentile=80,
            volume_ratio_percentile=60,
        )
    )
    item = result.items[0]
    assert [family.family for family in _families(item)] == list(RealtimeIntradayFactorFamily)
    assert item.relative_strength.score == 70
    assert item.activity_liquidity.score == 70
    assert item.risk_stability.score == 75
    assert item.risk_stability.components[0].transformation is RealtimeIntradayComponentTransformation.ONE_HUNDRED_MINUS
    assert item.risk_stability.components[0].source_percentile == 25
    assert [component.component_name for component in item.vwap_trend.components] == [
        "vwap_position", "vwap_trend"
    ]
    assert [component.component_name for component in item.short_momentum.components] == [
        "short_momentum_5m", "short_momentum_15m"
    ]
    assert all(
        component.unavailable_reason
        is RealtimeIntradayComponentUnavailableReason.MINUTE_DATA_NOT_AVAILABLE
        for component in (*item.vwap_trend.components, *item.short_momentum.components)
    )
    assert sum(len(family.components) for family in _families(item)) == 9


def test_missing_components_are_not_zero_and_change_pct_is_unused() -> None:
    with_change = _compute(
        _normalized(change_pct_percentile=100, price_vs_open_pct_percentile=60, turnover_rate_pct_percentile=80)
    ).items[0]
    without_change = _compute(
        _normalized(change_pct_percentile=0, price_vs_open_pct_percentile=60, turnover_rate_pct_percentile=80)
    ).items[0]
    assert with_change.relative_strength.score == without_change.relative_strength.score == 60
    assert with_change.activity_liquidity.score == 80
    assert with_change.relative_strength.component_coverage == 0.5
    assert with_change.activity_liquidity.component_coverage == 0.5
    no_strength = _compute(_normalized(change_pct_percentile=100)).items[0]
    assert no_strength.relative_strength.score is None
    assert no_strength.relative_strength.available is False
    assert no_strength.relative_strength.components[0].unavailable_reason is RealtimeIntradayComponentUnavailableReason.MISSING_NORMALIZED_SIGNAL


@pytest.mark.parametrize(("source", "expected"), [(0, 100), (25, 75), (50, 50), (100, 0)])
def test_stability_inversion_boundaries(source: float, expected: float) -> None:
    item = _compute(_normalized(session_range_pct_percentile=source)).items[0]
    assert item.risk_stability.score == expected


def test_sina_missing_activity_preserves_stock_and_reports_family_coverage() -> None:
    normalized = _normalized(
        price_vs_open_pct_percentile=50,
        price_vs_prev_close_pct_percentile=50,
        session_range_pct_percentile=50,
    )
    result = _compute(normalized)
    item = result.items[0]
    assert item.normalization_item == normalized.items[0]
    assert item.activity_liquidity.available is False
    assert item.available_families == 2
    assert item.family_coverage == 0.4
    assert result.diagnostics.available_family_values == 2
    assert result.diagnostics.total_family_slots == 5
    assert result.diagnostics.overall_family_coverage == 0.4


def test_rank_ready_empty_blocked_and_deterministic_semantics() -> None:
    normalized = _normalized_items(100, 0)
    result = _compute(normalized)
    assert [item.normalization_item.scan_item.snapshot_item.candidate.market_rank for item in result.items] == [1, 2]
    assert result == _compute(normalized)
    empty = _compute(_normalized_items())
    assert empty.diagnostics.factor_ready is True
    assert empty.items == ()
    assert empty.diagnostics.overall_family_coverage is None
    blocked = _compute(_normalized_items(0, ready=False))
    assert blocked.items == ()
    assert blocked.diagnostics.blockers == (
        RealtimeIntradayFactorBlocker.SIGNAL_NORMALIZATION_NOT_READY,
    )


def test_component_contract_rejects_invalid_source_transformation_and_availability() -> None:
    valid = _source_component()
    assert valid.score == 80
    invalid_updates = (
        {"score": 101},
        {"available": False},
        {"unavailable_reason": RealtimeIntradayComponentUnavailableReason.MISSING_NORMALIZED_SIGNAL},
        {"score": 79},
        {"transformation": RealtimeIntradayComponentTransformation.ONE_HUNDRED_MINUS},
        {"source_percentile": None},
    )
    for update in invalid_updates:
        with pytest.raises(ValidationError):
            RealtimeIntradayComponentResult(**(valid.model_dump() | update))
    minute = RealtimeIntradayComponentResult(
        component_name="vwap_position",
        family=RealtimeIntradayFactorFamily.VWAP_TREND,
        source_percentile_name=None,
        source_percentile=None,
        transformation=RealtimeIntradayComponentTransformation.IDENTITY,
        score=None,
        available=False,
        unavailable_reason=RealtimeIntradayComponentUnavailableReason.MINUTE_DATA_NOT_AVAILABLE,
    )
    with pytest.raises(ValidationError):
        RealtimeIntradayComponentResult(
            **(minute.model_dump() | {"unavailable_reason": RealtimeIntradayComponentUnavailableReason.MISSING_NORMALIZED_SIGNAL})
        )


def test_family_and_stock_contracts_reject_incorrect_accounting_and_identities() -> None:
    component = _source_component()
    family = RealtimeIntradayFamilyResult(
        family=RealtimeIntradayFactorFamily.RELATIVE_STRENGTH,
        score=80,
        available=True,
        available_components=1,
        total_components=1,
        component_coverage=1,
        components=(component,),
    )
    for update in (
        {"available_components": 0},
        {"component_coverage": 0.5},
        {"components": (component, component), "total_components": 2, "available_components": 2, "component_coverage": 1},
        {"components": (component.model_copy(update={"family": RealtimeIntradayFactorFamily.ACTIVITY_LIQUIDITY}),)},
    ):
        with pytest.raises(ValidationError):
            RealtimeIntradayFamilyResult(**(family.model_dump() | update))
    item = _compute(_normalized(price_vs_open_pct_percentile=50)).items[0]
    for update in (
        {"total_families": 4},
        {"available_families": 0},
        {"family_coverage": 1},
        {"relative_strength": item.activity_liquidity.model_dump()},
    ):
        with pytest.raises(ValidationError):
            RealtimeIntradayFactorItem(**(item.model_dump() | update))


def _compute(normalized):
    return RealtimeIntradayFactorEngine().compute(normalized)


def _source_component() -> RealtimeIntradayComponentResult:
    return RealtimeIntradayComponentResult(
        component_name="previous_close_strength",
        family=RealtimeIntradayFactorFamily.RELATIVE_STRENGTH,
        source_percentile_name="price_vs_prev_close_pct_percentile",
        source_percentile=80,
        transformation=RealtimeIntradayComponentTransformation.IDENTITY,
        score=80,
        available=True,
        unavailable_reason=None,
    )


def _normalized(**percentile_values: float | None):
    return _normalized_items(percentile_values)


def _normalized_items(*change_values: float, ready: bool = True):
    if len(change_values) == 1 and isinstance(change_values[0], dict):
        percentile_values = change_values[0]
        change_values = (0.0,)
        default_value = None
    else:
        percentile_values = {}
        default_value = 0.0
    items = tuple(
        _normalization_item(rank, value, percentile_values, default_value)
        for rank, value in enumerate(change_values, start=1)
    )
    return RealtimeSignalNormalizationResult.model_construct(
        calculation_at=datetime(2026, 8, 31, tzinfo=UTC),
        candidate_as_of=datetime(2026, 8, 30, tzinfo=UTC),
        diagnostics=RealtimeSignalNormalizationDiagnostics.model_construct(
            normalization_ready=ready,
            blockers=(),
            calculation_at=datetime(2026, 8, 31, tzinfo=UTC),
            candidate_as_of=datetime(2026, 8, 30, tzinfo=UTC),
        ),
        items=items if ready else (),
    )


def _normalization_item(rank, value, values, default_value):
    percentiles = RealtimeSignalPercentiles.model_construct(
        change_pct_percentile=values.get("change_pct_percentile", value if default_value is not None else None),
        price_vs_open_pct_percentile=values.get("price_vs_open_pct_percentile", default_value),
        price_vs_prev_close_pct_percentile=values.get("price_vs_prev_close_pct_percentile", default_value),
        session_range_pct_percentile=values.get("session_range_pct_percentile", default_value),
        turnover_rate_pct_percentile=values.get("turnover_rate_pct_percentile", default_value),
        volume_ratio_percentile=values.get("volume_ratio_percentile", default_value),
    )
    available = sum(item is not None for item in percentiles.model_dump().values())
    return RealtimeSignalNormalizationItem.model_construct(
        scan_item=RealtimeLightScanItem.model_construct(
            snapshot_item=RealtimeCandidateSnapshotItem.model_construct(
                candidate=RealtimeCandidate.model_construct(symbol=f"{rank:06d}.SZ", market_rank=rank)
            )
        ),
        percentiles=percentiles,
        available_percentiles=available,
        percentile_completeness=available / 6,
    )


def _families(item):
    return (
        item.relative_strength,
        item.activity_liquidity,
        item.vwap_trend,
        item.short_momentum,
        item.risk_stability,
    )
