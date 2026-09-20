"""Offline cumulative observed-rank-cutoff contracts delegated to Task50."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.selection import (
    SelectionResearchEffectivenessAnalyzer,
    SelectionResearchHorizonEffectiveness,
    SelectionResearchRankCutoffEffectiveness,
    SelectionResearchRankCutoffEffectivenessAnalyzer,
    SelectionResearchRankCutoffEffectivenessReport,
    SelectionResearchReturnAvailability,
    SelectionResearchReturnHistory,
    SelectionResearchReturnItem,
    SelectionResearchReturnLabel,
    SelectionResearchReturnReport,
)
from stock_selector.selection.research_rank_cutoff_effectiveness import (
    _filtered_history,
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
        endpoint_trade_date=(AT.date() + timedelta(days=horizon) if value is not None else None),
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


def _cutoff_by_rank(
    report: SelectionResearchRankCutoffEffectivenessReport,
) -> dict[int, SelectionResearchRankCutoffEffectiveness]:
    return {item.cutoff_rank: item for item in report.cutoffs}


def test_empty_history_has_no_cutoffs() -> None:
    result = SelectionResearchRankCutoffEffectivenessAnalyzer().analyze(_history())

    assert result.cutoffs == ()
    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (0, 0, 0)


def test_observed_sparse_cutoffs_and_included_prefixes_are_exact() -> None:
    history = _history(_report(0, (
        _available_item(4, "600519.SH", 0.10),
        _available_item(1, "000001.SZ", 0.0),
        _available_item(3, "601398.SH", -0.10),
    )))

    result = SelectionResearchRankCutoffEffectivenessAnalyzer().analyze(history)

    assert tuple(item.cutoff_rank for item in result.cutoffs) == (1, 3, 4)
    assert tuple(item.included_ranks for item in result.cutoffs) == (
        (1,),
        (1, 3),
        (1, 3, 4),
    )
    assert 2 not in _cutoff_by_rank(result)


def test_cutoff_observations_are_cumulative_and_final_cutoff_covers_all_items() -> None:
    history = _history(
        _report(0, ()),
        _report(1, (_available_item(3, "600519.SH", 0.10), _available_item(1, "000001.SZ", 0.0))),
        _report(2, (_available_item(1, "601398.SH", -0.10),)),
    )

    result = SelectionResearchRankCutoffEffectivenessAnalyzer().analyze(history)

    assert (result.snapshot_count, result.empty_snapshot_count, result.item_observation_count) == (3, 1, 3)
    assert tuple(item.observation_count for item in result.cutoffs) == (2, 3)
    assert result.cutoffs[-1].observation_count == result.item_observation_count
    assert all(
        earlier.observation_count <= later.observation_count
        for earlier, later in zip(result.cutoffs, result.cutoffs[1:])
    )


def test_cutoff_horizons_delegate_exactly_to_task50_with_mixed_availability() -> None:
    mixed = _item(3, "600519.SH", (
        _label(5, SelectionResearchReturnAvailability.AVAILABLE, 0.10),
        _label(20, SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE),
        _label(60, SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE),
    ))
    original_items = (mixed, _available_item(1, "000001.SZ", 0.0))
    history = _history(_report(0, original_items))

    result = SelectionResearchRankCutoffEffectivenessAnalyzer().analyze(history)
    cutoff_three = _cutoff_by_rank(result)[3]
    expected = SelectionResearchEffectivenessAnalyzer().analyze(_filtered_history(history, 3))

    assert cutoff_three.observation_count == expected.item_observation_count == 2
    assert cutoff_three.horizons == expected.horizons
    assert tuple(item.horizon_sessions for item in cutoff_three.horizons) == HORIZONS
    assert tuple(item.total_labels for item in cutoff_three.horizons) == (2, 2, 2)
    assert cutoff_three.horizons[1].anchor_unavailable_labels == 1
    assert cutoff_three.horizons[2].non_contiguous_return_evidence_labels == 1
    assert tuple(item.symbol for item in _filtered_history(history, 3).reports[0].items) == (
        "600519.SH",
        "000001.SZ",
    )


def test_metadata_propagates_and_analysis_is_deterministic() -> None:
    history = _history(_report(0, ()), _report(1, (_available_item(4, "600519.SH", 0.10),)))
    analyzer = SelectionResearchRankCutoffEffectivenessAnalyzer()

    first = analyzer.analyze(history)
    second = analyzer.analyze(history)

    assert first == second
    assert (first.evaluated_at, first.start_date, first.end_date) == (
        history.evaluated_at,
        history.start_date,
        history.end_date,
    )


def test_models_reject_malformed_cutoff_invariants() -> None:
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
    horizons = (
        horizon,
        horizon.model_copy(update={"horizon_sessions": 20}),
        horizon.model_copy(update={"horizon_sessions": 60}),
    )
    with pytest.raises(ValueError, match="must end at cutoff rank"):
        SelectionResearchRankCutoffEffectiveness(
            cutoff_rank=3,
            included_ranks=(1,),
            observation_count=1,
            horizons=horizons,
        )
    cutoff_one = SelectionResearchRankCutoffEffectiveness(
        cutoff_rank=1,
        included_ranks=(1,),
        observation_count=1,
        horizons=horizons,
    )
    cutoff_three = SelectionResearchRankCutoffEffectiveness(
        cutoff_rank=3,
        included_ranks=(3,),
        observation_count=1,
        horizons=horizons,
    )
    with pytest.raises(ValueError, match="cumulative observed-rank prefixes"):
        SelectionResearchRankCutoffEffectivenessReport(
            evaluated_at=EVALUATED_AT,
            start_date=None,
            end_date=None,
            snapshot_count=1,
            empty_snapshot_count=0,
            item_observation_count=2,
            cutoffs=(cutoff_one, cutoff_three),
        )
    with pytest.raises(ValueError, match="final cutoff observations"):
        SelectionResearchRankCutoffEffectivenessReport(
            evaluated_at=EVALUATED_AT,
            start_date=None,
            end_date=None,
            snapshot_count=2,
            empty_snapshot_count=0,
            item_observation_count=2,
            cutoffs=(cutoff_one,),
        )


def test_source_has_no_arithmetic_io_or_selection_dependencies_independent_of_cwd() -> None:
    source_path = Path(__file__).resolve().parents[2] / "src/stock_selector/selection/research_rank_cutoff_effectiveness.py"
    source = source_path.read_text(encoding="utf-8")

    for forbidden in (
        "import math",
        "import statistics",
        "return_fraction",
        "SelectionResearchRankEffectiveness",
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
