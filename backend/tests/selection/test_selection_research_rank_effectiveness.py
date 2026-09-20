"""Offline exact-rank contracts delegated to Task50 effectiveness arithmetic."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.selection import (
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchHorizonEffectiveness,
    SelectionResearchRankEffectiveness,
    SelectionResearchRankEffectivenessAnalyzer,
    SelectionResearchRankEffectivenessReport,
    SelectionResearchReturnAvailability,
    SelectionResearchReturnHistory,
    SelectionResearchReturnItem,
    SelectionResearchReturnLabel,
    SelectionResearchReturnReport,
)

AT = datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
EVALUATED_AT = AT + timedelta(days=90)
HORIZONS = (5, 20, 60)


def _label(
    horizon: int,
    availability: SelectionResearchReturnAvailability,
    value: float | None = None,
) -> SelectionResearchReturnLabel:
    return SelectionResearchReturnLabel(
        horizon_sessions=horizon,
        availability=availability,
        return_fraction=value,
        endpoint_trade_date=AT.date() + timedelta(days=horizon) if value is not None else None,
        endpoint_observed_at=EVALUATED_AT if value is not None else None,
    )


def _item(
    rank: int,
    symbol: str,
    labels: tuple[SelectionResearchReturnLabel, ...],
) -> SelectionResearchReturnItem:
    return SelectionResearchReturnItem(rank=rank, symbol=symbol, labels=labels)


def _available_item(rank: int, symbol: str, value: float) -> SelectionResearchReturnItem:
    return _item(
        rank,
        symbol,
        tuple(
            _label(horizon, SelectionResearchReturnAvailability.AVAILABLE, value)
            for horizon in HORIZONS
        ),
    )


def _report(
    day: int, items: tuple[SelectionResearchReturnItem, ...]
) -> SelectionResearchReturnReport:
    snapshot_as_of = AT + timedelta(days=day)
    return SelectionResearchReturnReport(
        snapshot_as_of=snapshot_as_of,
        evaluated_at=EVALUATED_AT,
        anchor_date=snapshot_as_of.date(),
        items=items,
    )


def _history(*reports: SelectionResearchReturnReport) -> SelectionResearchReturnHistory:
    return SelectionResearchReturnHistory(
        evaluated_at=EVALUATED_AT,
        start_date=AT.date(),
        end_date=AT.date() + timedelta(days=10),
        reports=reports,
    )


def _filtered_history(
    history: SelectionResearchReturnHistory, rank: int
) -> SelectionResearchReturnHistory:
    return SelectionResearchReturnHistory(
        evaluated_at=history.evaluated_at,
        start_date=history.start_date,
        end_date=history.end_date,
        reports=tuple(
            SelectionResearchReturnReport(
                snapshot_as_of=report.snapshot_as_of,
                evaluated_at=report.evaluated_at,
                anchor_date=report.anchor_date,
                items=tuple(item for item in report.items if item.rank == rank),
            )
            for report in history.reports
        ),
    )


def _rank_by_value(report: SelectionResearchRankEffectivenessReport) -> dict[int, SelectionResearchRankEffectiveness]:
    return {item.rank: item for item in report.ranks}


def test_empty_history_has_no_rank_observations() -> None:
    result = SelectionResearchRankEffectivenessAnalyzer().analyze(_history())

    assert result.ranks == ()
    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (0, 0, 0)


def test_discovers_observed_sparse_exact_ranks_in_ascending_order_only() -> None:
    history = _history(_report(0, (
        _available_item(3, "600519.SH", 0.10),
        _available_item(1, "000001.SZ", 0.0),
        _available_item(4, "601398.SH", -0.10),
    )))

    result = SelectionResearchRankEffectivenessAnalyzer().analyze(history)

    assert tuple(item.rank for item in result.ranks) == (1, 3, 4)
    assert 2 not in _rank_by_value(result)


def test_exact_rank_counts_retain_blocked_snapshots_only_in_overall_metadata() -> None:
    history = _history(
        _report(0, ()),
        _report(1, (_available_item(1, "600519.SH", 0.10), _available_item(3, "000001.SZ", 0.0))),
        _report(2, (_available_item(1, "601398.SH", -0.10),)),
    )

    result = SelectionResearchRankEffectivenessAnalyzer().analyze(history)

    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (3, 1, 3)
    ranks = _rank_by_value(result)
    assert ranks[1].observation_count == 2
    assert ranks[3].observation_count == 1
    assert all(item.observation_count > 0 for item in result.ranks)


def test_rank_horizons_delegate_exactly_to_task50_with_mixed_availability() -> None:
    mixed = _item(3, "600519.SH", (
        _label(5, SelectionResearchReturnAvailability.AVAILABLE, 0.10),
        _label(20, SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE),
        _label(60, SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE),
    ))
    history = _history(_report(0, (mixed, _available_item(1, "000001.SZ", 0.0))))

    result = SelectionResearchRankEffectivenessAnalyzer().analyze(history)
    rank_three = _rank_by_value(result)[3]
    expected = SelectionResearchEffectivenessAnalyzer().analyze(_filtered_history(history, 3))

    assert rank_three.observation_count == expected.item_observation_count == 1
    assert rank_three.horizons == expected.horizons
    assert tuple(item.horizon_sessions for item in rank_three.horizons) == HORIZONS
    assert tuple(item.total_labels for item in rank_three.horizons) == (1, 1, 1)
    assert rank_three.horizons[1].anchor_unavailable_labels == 1
    assert rank_three.horizons[2].non_contiguous_return_evidence_labels == 1


def test_metadata_propagates_and_analysis_is_deterministic() -> None:
    history = _history(_report(0, ()), _report(1, (_available_item(4, "600519.SH", 0.10),)))
    analyzer = SelectionResearchRankEffectivenessAnalyzer()

    first = analyzer.analyze(history)
    second = analyzer.analyze(history)

    assert first == second
    assert (first.evaluated_at, first.start_date, first.end_date) == (
        history.evaluated_at,
        history.start_date,
        history.end_date,
    )


def test_models_reject_invalid_rank_report_invariants() -> None:
    horizon = SelectionResearchHorizonEffectiveness(
        horizon_sessions=5,
        total_labels=1,
        available_labels=1,
        anchor_unavailable_labels=0,
        insufficient_future_returns_labels=0,
        non_contiguous_return_evidence_labels=0,
        availability_rate=1.0,
        positive_return_labels=1,
        zero_return_labels=0,
        negative_return_labels=0,
        positive_return_rate=1.0,
        mean_return_fraction=0.1,
        median_return_fraction=0.1,
    )
    with pytest.raises(ValueError, match="rank horizon totals"):
        SelectionResearchRankEffectiveness(
            rank=1,
            observation_count=2,
            horizons=(horizon, horizon.model_copy(update={"horizon_sessions": 20}), horizon.model_copy(update={"horizon_sessions": 60})),
        )
    with pytest.raises(ValueError, match="greater than 0"):
        SelectionResearchRankEffectiveness(
            rank=0,
            observation_count=1,
            horizons=(horizon, horizon.model_copy(update={"horizon_sessions": 20}), horizon.model_copy(update={"horizon_sessions": 60})),
        )
    rank = SelectionResearchRankEffectiveness(
        rank=1,
        observation_count=1,
        horizons=(horizon, horizon.model_copy(update={"horizon_sessions": 20}), horizon.model_copy(update={"horizon_sessions": 60})),
    )
    with pytest.raises(ValueError, match="rank observation counts"):
        SelectionResearchRankEffectivenessReport(
            evaluated_at=EVALUATED_AT,
            start_date=None,
            end_date=None,
            snapshot_count=1,
            empty_snapshot_count=0,
            item_observation_count=2,
            ranks=(rank,),
        )
    with pytest.raises(ValueError, match="item observations require rank entries"):
        SelectionResearchRankEffectivenessReport(
            evaluated_at=EVALUATED_AT,
            start_date=None,
            end_date=None,
            snapshot_count=1,
            empty_snapshot_count=0,
            item_observation_count=1,
            ranks=(),
        )
    with pytest.raises(ValueError, match="empty item observations require no rank entries"):
        SelectionResearchRankEffectivenessReport(
            evaluated_at=EVALUATED_AT,
            start_date=None,
            end_date=None,
            snapshot_count=1,
            empty_snapshot_count=1,
            item_observation_count=0,
            ranks=(rank,),
        )


def test_source_has_no_arithmetic_io_or_selection_dependencies_independent_of_cwd() -> None:
    source_path = Path(__file__).resolve().parents[2] / "src/stock_selector/selection/research_rank_effectiveness.py"
    source = source_path.read_text(encoding="utf-8")

    for forbidden in (
        "import math",
        "import statistics",
        "return_fraction",
        "SelectionResearchArtifactStore",
        "LocalMarketRepository",
        "SelectionResearchReturnLabeler",
        "stock_selector.providers",
        "stock_selector.collection",
        "DailySelectionService",
        "FiveFactorEngine",
        "BaseScoreEngine",
        "benchmark",
        "portfolio",
        "backtest",
        "trading",
    ):
        assert forbidden not in source
