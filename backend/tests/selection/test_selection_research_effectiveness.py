"""Pure offline contracts for descriptive metrics over Task49 label history."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.selection import (
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchEffectivenessReport,
    SelectionResearchHorizonEffectiveness,
    SelectionResearchReturnAvailability,
    SelectionResearchReturnHistory,
    SelectionResearchReturnItem,
    SelectionResearchReturnLabel,
    SelectionResearchReturnReport,
)

AT = datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


def _label(
    horizon: int,
    availability: SelectionResearchReturnAvailability,
    return_fraction: float | None = None,
) -> SelectionResearchReturnLabel:
    return SelectionResearchReturnLabel(
        horizon_sessions=horizon,
        availability=availability,
        return_fraction=return_fraction,
        endpoint_trade_date=(
            AT.date() + timedelta(days=horizon)
            if return_fraction is not None
            else None
        ),
        endpoint_observed_at=AT if return_fraction is not None else None,
    )


def _item(
    symbol: str,
    rank: int,
    labels: tuple[SelectionResearchReturnLabel, ...],
) -> SelectionResearchReturnItem:
    return SelectionResearchReturnItem(rank=rank, symbol=symbol, labels=labels)


def _report(
    day: int,
    items: tuple[SelectionResearchReturnItem, ...],
    *,
    evaluated_at: datetime = AT + timedelta(days=90),
) -> SelectionResearchReturnReport:
    snapshot_at = AT + timedelta(days=day)
    return SelectionResearchReturnReport(
        snapshot_as_of=snapshot_at,
        evaluated_at=evaluated_at,
        anchor_date=snapshot_at.date(),
        items=items,
    )


def _history(*reports: SelectionResearchReturnReport) -> SelectionResearchReturnHistory:
    return SelectionResearchReturnHistory(
        evaluated_at=AT + timedelta(days=90),
        start_date=AT.date(),
        end_date=AT.date() + timedelta(days=10),
        reports=reports,
    )


def _horizons(report):  # type: ignore[no-untyped-def]
    return {item.horizon_sessions: item for item in report.horizons}


def test_empty_history_has_no_rates_or_return_metrics() -> None:
    result = SelectionResearchEffectivenessAnalyzer().analyze(_history())

    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (0, 0, 0)
    for horizon in result.horizons:
        assert horizon.total_labels == 0
        assert horizon.availability_rate is None
        assert horizon.positive_return_rate is None
        assert horizon.mean_return_fraction is None
        assert horizon.median_return_fraction is None


def test_availability_and_return_direction_accounting_use_available_labels_only() -> None:
    available = SelectionResearchReturnAvailability.AVAILABLE
    item_one = _item("600519.SH", 2, (
        _label(5, available, 0.10),
        _label(20, SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE),
        _label(60, SelectionResearchReturnAvailability.INSUFFICIENT_FUTURE_RETURNS),
    ))
    item_two = _item("000001.SZ", 1, (
        _label(5, available, 0.0),
        _label(20, available, -0.20),
        _label(60, SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE),
    ))

    result = SelectionResearchEffectivenessAnalyzer().analyze(_history(_report(0, (item_one, item_two))))

    horizons = _horizons(result)
    five = horizons[5]
    assert (five.total_labels, five.available_labels, five.positive_return_labels, five.zero_return_labels, five.negative_return_labels) == (2, 2, 1, 1, 0)
    assert five.availability_rate == 1.0
    assert five.positive_return_rate == 0.5
    assert five.mean_return_fraction == pytest.approx(0.05)
    assert five.median_return_fraction == pytest.approx(0.05)
    twenty = horizons[20]
    assert (twenty.available_labels, twenty.anchor_unavailable_labels, twenty.negative_return_labels) == (1, 1, 1)
    assert twenty.mean_return_fraction == pytest.approx(-0.20)
    sixty = horizons[60]
    assert (sixty.available_labels, sixty.insufficient_future_returns_labels, sixty.non_contiguous_return_evidence_labels) == (0, 1, 1)
    assert sixty.mean_return_fraction is None


def test_blocked_empty_snapshots_are_counted_but_add_no_observations() -> None:
    item = _item("600519.SH", 1, tuple(
        _label(horizon, SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE)
        for horizon in (5, 20, 60)
    ))

    result = SelectionResearchEffectivenessAnalyzer().analyze(
        _history(_report(0, ()), _report(1, (item,)))
    )

    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (2, 1, 1)
    assert all(horizon.total_labels == 1 for horizon in result.horizons)


def test_item_observation_weighting_is_not_snapshot_weighting() -> None:
    available = SelectionResearchReturnAvailability.AVAILABLE
    first = _report(0, (
        _item("600519.SH", 2, tuple(_label(horizon, available, 1.0) for horizon in (5, 20, 60))),
        _item("000001.SZ", 1, tuple(_label(horizon, available, 0.0) for horizon in (5, 20, 60))),
    ))
    second = _report(1, (
        _item("601398.SH", 1, tuple(_label(horizon, available, 0.0) for horizon in (5, 20, 60))),
    ))

    result = SelectionResearchEffectivenessAnalyzer().analyze(_history(first, second))

    assert _horizons(result)[5].mean_return_fraction == pytest.approx(1 / 3)
    assert _horizons(result)[5].median_return_fraction == 0.0


def test_metadata_and_determinism_propagate_exactly_from_history() -> None:
    item = _item("600519.SH", 1, tuple(
        _label(horizon, SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE)
        for horizon in (5, 20, 60)
    ))
    history = _history(_report(0, (item,)))
    analyzer = SelectionResearchEffectivenessAnalyzer()

    first = analyzer.analyze(history)
    second = analyzer.analyze(history)

    assert first == second
    assert (first.evaluated_at, first.start_date, first.end_date) == (
        history.evaluated_at, history.start_date, history.end_date
    )


def test_models_reject_invalid_partitions_and_horizon_totals() -> None:
    with pytest.raises(ValueError, match="partition total"):
        SelectionResearchHorizonEffectiveness(
            horizon_sessions=5, total_labels=1, available_labels=1,
            anchor_unavailable_labels=1, insufficient_future_returns_labels=0,
            non_contiguous_return_evidence_labels=0, availability_rate=1.0,
            positive_return_labels=1, zero_return_labels=0, negative_return_labels=0,
            positive_return_rate=1.0, mean_return_fraction=0.1, median_return_fraction=0.1,
        )
    valid = SelectionResearchHorizonEffectiveness(
        horizon_sessions=5, total_labels=0, available_labels=0,
        anchor_unavailable_labels=0, insufficient_future_returns_labels=0,
        non_contiguous_return_evidence_labels=0, availability_rate=None,
        positive_return_labels=0, zero_return_labels=0, negative_return_labels=0,
        positive_return_rate=None, mean_return_fraction=None, median_return_fraction=None,
    )
    with pytest.raises(ValueError, match="each horizon total"):
        SelectionResearchEffectivenessReport(
            evaluated_at=AT, start_date=None, end_date=None, snapshot_count=0,
            empty_snapshot_count=0, item_observation_count=1, horizons=(valid, valid.model_copy(update={"horizon_sessions": 20}), valid.model_copy(update={"horizon_sessions": 60})),
        )


def test_source_has_no_io_selection_or_performance_dependencies_independent_of_cwd() -> None:
    source_path = Path(__file__).resolve().parents[2] / "src/stock_selector/selection/research_effectiveness.py"
    source = source_path.read_text(encoding="utf-8")
    for forbidden in (
        "SelectionResearchArtifactStore", "LocalMarketRepository", "SelectionResearchReturnLabeler",
        "stock_selector.providers", "stock_selector.collection", "DailySelectionService",
        "FiveFactorEngine", "BaseScoreEngine", "benchmark", "portfolio", "backtest", "trading",
    ):
        assert forbidden not in source
