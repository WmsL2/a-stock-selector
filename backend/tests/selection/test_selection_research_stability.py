"""Pure selection research stability contracts."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.models.selection import Evidence
from stock_selector.selection import (
    DailySelectionDiagnostics,
    SelectionBlocker,
    SelectionResearchItem,
    SelectionResearchRankMovement,
    SelectionResearchRankMovementStatus,
    SelectionResearchSnapshot,
    SelectionResearchStabilityAnalyzer,
    SelectionResearchStabilityComparisonBlocker,
    SelectionResearchStabilityTransition,
)

_AS_OF = datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


def _snapshot(
    offset: int,
    items: tuple[tuple[str, int], ...],
    *,
    ready: bool = True,
    strategy: str = "official",
) -> SelectionResearchSnapshot:
    as_of = _AS_OF + timedelta(days=offset)
    blockers = () if ready else (SelectionBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,)
    research_items = tuple(
        SelectionResearchItem(
            rank=rank, as_of=as_of, symbol=symbol, name=f"name-{symbol}", board="sz_main",
            industry_code=None, industry_name=None, base_score=80.0, confidence_adjusted_score=60.0,
            data_completeness=0.8, confidence=0.8, quality_score=80.0, value_score=80.0,
            growth_score=80.0, momentum_score=None, low_volatility_score=None,
            evidence=(Evidence(code="evidence", message="evidence"),), risks=(),
        )
        for symbol, rank in items
    ) if ready else ()
    diagnostics = DailySelectionDiagnostics(
        as_of=as_of, selection_ready=ready, blockers=blockers,
        input_instruments=10, structural_members=10, risk_records=10, risk_complete_members=10,
        risk_coverage_ratio=1.0, risk_eligible_members=10,
        factor_input_members=10 if ready else 0, scoreable_members=10 if ready else 0,
        requested_top_n=20, returned_items=len(research_items), price_factors_operational=True,
    )
    return SelectionResearchSnapshot(
        as_of=as_of, strategy_name=strategy, selection_ready=ready, blockers=blockers,
        refresh_had_collection_failures=False, diagnostics=diagnostics, items=research_items,
    )


def test_empty_and_single_snapshot_reports_have_no_transitions() -> None:
    analyzer = SelectionResearchStabilityAnalyzer()
    assert analyzer.analyze(()).model_dump() == {
        "schema_version": 1, "start_date": None, "end_date": None, "snapshot_count": 0,
        "transition_count": 0, "comparable_transition_count": 0, "transitions": (),
    }
    report = analyzer.analyze((_snapshot(0, (("A", 1),)),))
    assert report.snapshot_count == 1
    assert report.transition_count == 0


def test_ready_transitions_preserve_official_order_counts_and_rank_signs() -> None:
    previous = _snapshot(0, (("C", 7), ("A", 1), ("B", 3), ("X", 9)))
    current = _snapshot(2, (("A", 2), ("D", 8), ("B", 3), ("C", 1)))
    transition = SelectionResearchStabilityAnalyzer().analyze((previous, current)).transitions[0]

    assert (transition.previous_item_count, transition.current_item_count) == (4, 4)
    assert (transition.retained_count, transition.entered_count, transition.exited_count) == (3, 1, 1)
    assert transition.retention_rate == 0.75
    assert transition.overlap_rate == 0.6
    assert [item.symbol for item in transition.movements] == ["A", "D", "B", "C", "X"]
    assert [item.status.value for item in transition.movements] == ["retained", "entered", "retained", "retained", "exited"]
    assert [item.rank_change for item in transition.movements] == [-1, None, 0, 6, None]


@pytest.mark.parametrize(
    ("previous_ready", "current_ready", "strategy", "expected"),
    [
        (False, True, "official", ["previous_selection_blocked"]),
        (True, False, "official", ["current_selection_blocked"]),
        (False, False, "official", ["previous_selection_blocked", "current_selection_blocked"]),
        (True, True, "changed", ["strategy_changed"]),
    ],
)
def test_non_comparable_pairs_have_no_synthetic_movements(
    previous_ready: bool, current_ready: bool, strategy: str, expected: list[str]
) -> None:
    previous = _snapshot(0, (("A", 1),), ready=previous_ready)
    current = _snapshot(1, (("A", 1),), ready=current_ready, strategy=strategy)
    transition = SelectionResearchStabilityAnalyzer().analyze((previous, current)).transitions[0]

    assert transition.comparable is False
    assert [item.value for item in transition.comparison_blockers] == expected
    assert transition.movements == ()
    assert transition.retained_count is None
    assert transition.retention_rate is None


def test_filters_are_inclusive_preserve_adjacent_input_order_and_do_not_mutate() -> None:
    snapshots = (_snapshot(0, (("A", 1),)), _snapshot(2, (("A", 1),)), _snapshot(5, (("A", 1),)))
    analyzer = SelectionResearchStabilityAnalyzer()
    report = analyzer.analyze(snapshots, start_date=date(2026, 9, 17))
    assert [(item.previous_as_of.date(), item.current_as_of.date()) for item in report.transitions] == [
        (date(2026, 9, 17), date(2026, 9, 20))
    ]
    assert analyzer.analyze(snapshots, end_date=date(2026, 9, 17)).snapshot_count == 2
    assert analyzer.analyze(snapshots, start_date=date(2026, 9, 17), end_date=date(2026, 9, 17)).transition_count == 0
    assert analyzer.analyze(snapshots, start_date=date(2026, 10, 1)).snapshot_count == 0
    assert snapshots[0].items[0].rank == 1
    with pytest.raises(ValueError, match="start_date must not follow end_date"):
        analyzer.analyze(snapshots, start_date=date(2026, 9, 20), end_date=date(2026, 9, 17))


def test_domain_models_reject_inconsistent_transition_values() -> None:
    with pytest.raises(ValueError, match="rank change"):
        SelectionResearchRankMovement(
            symbol="A", name="A", status=SelectionResearchRankMovementStatus.RETAINED,
            previous_rank=3, current_rank=2, rank_change=0,
        )
    with pytest.raises(ValueError, match="unavailable"):
        SelectionResearchStabilityTransition(
            previous_as_of=_AS_OF, current_as_of=_AS_OF + timedelta(days=1),
            previous_strategy_name="official", current_strategy_name="official",
            previous_selection_ready=False, current_selection_ready=True,
            previous_blockers=(SelectionBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,),
            current_blockers=(), comparable=False,
            comparison_blockers=(SelectionResearchStabilityComparisonBlocker.PREVIOUS_SELECTION_BLOCKED,),
            previous_item_count=0, current_item_count=1, retained_count=0, entered_count=None,
            exited_count=None, retention_rate=None, overlap_rate=None, movements=(),
        )


def test_analyzer_source_is_pure_domain_analysis() -> None:
    source = Path(__file__).parents[2] / "src" / "stock_selector" / "selection" / "research_stability.py"
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "SelectionResearchArtifactStore", "LocalMarketRepository", "DailySelectionService",
        "SelectionResearchReturnLabeler", "SelectionResearchReturnHistoryBuilder",
        "SelectionResearchEffectivenessAnalyzer", "stock_selector.providers", "stock_selector.collection",
        "datetime.now", "date.today", "requests", "fastapi", "portfolio", "backtest", "trading",
    )
    assert not [value for value in forbidden if value in text]
