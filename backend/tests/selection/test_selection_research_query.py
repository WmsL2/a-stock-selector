"""Pure query contracts for canonical research snapshots."""

import csv
import json
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest

from stock_selector.models.selection import Evidence
from stock_selector.selection import (
    DailySelectionDiagnostics,
    SelectionBlocker,
    SelectionResearchItem,
    SelectionResearchItemQueryAnalyzer,
    SelectionResearchSnapshot,
    selection_research_item_query_csv,
    selection_research_item_query_json,
)

_AS_OF = datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


def _snapshot(offset: int, items: tuple[tuple[str, int, str], ...], *, ready: bool = True) -> SelectionResearchSnapshot:
    as_of = _AS_OF + timedelta(days=offset)
    blockers = () if ready else (SelectionBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,)
    research_items = tuple(
        SelectionResearchItem(
            rank=rank, as_of=as_of, symbol=symbol, name=name, board="sz_main",
            industry_code="C15", industry_name="饮料", base_score=80.0,
            confidence_adjusted_score=70.0, data_completeness=0.8, confidence=0.9,
            quality_score=80.0, value_score=70.0, growth_score=60.0,
            momentum_score=None, low_volatility_score=None,
            evidence=(Evidence(code=f"e-{symbol}", message="evidence"),), risks=(),
        ) for symbol, rank, name in items
    ) if ready else ()
    diagnostics = DailySelectionDiagnostics(
        as_of=as_of, selection_ready=ready, blockers=blockers, input_instruments=2,
        structural_members=2, risk_records=2, risk_complete_members=2, risk_coverage_ratio=1.0,
        risk_eligible_members=2, factor_input_members=2 if ready else 0,
        scoreable_members=2 if ready else 0, requested_top_n=20,
        returned_items=len(research_items), price_factors_operational=True,
    )
    return SelectionResearchSnapshot(
        as_of=as_of, strategy_name="official", selection_ready=ready, blockers=blockers,
        refresh_had_collection_failures=False, diagnostics=diagnostics, items=research_items,
    )


def test_empty_and_canonical_flattening_preserve_supplied_order() -> None:
    analyzer = SelectionResearchItemQueryAnalyzer()
    assert analyzer.analyze(()).model_dump()["observations"] == ()
    snapshots = (_snapshot(0, (("B", 7, "Beta"), ("A", 1, "Alpha"))), _snapshot(2, (("C", 3, "Gamma"),)))
    report = analyzer.analyze(snapshots)
    assert [item.item.symbol for item in report.observations] == ["B", "A", "C"]
    assert report.matching_snapshot_count == 2


def test_filters_normalize_and_use_and_semantics_without_synthesizing_blocked_items() -> None:
    snapshots = (_snapshot(0, (("600519.SH", 7, "贵州茅台"), ("A", 1, "Alpha"))), _snapshot(1, (), ready=False))
    report = SelectionResearchItemQueryAnalyzer().analyze(
        snapshots, strategy_name=" official ", q=" 茅台 ", board=" sz_main ", industry_code=" C15 ", max_rank=7,
    )
    assert (report.strategy_name, report.q, report.board, report.industry_code) == ("official", "茅台", "sz_main", "C15")
    assert (report.snapshot_count, report.matching_snapshot_count) == (2, 1)
    assert [item.item.symbol for item in report.observations] == ["600519.SH"]
    assert SelectionResearchItemQueryAnalyzer().analyze(snapshots, q="alpha").observations[0].item.symbol == "A"


def test_validation_chronology_json_and_csv_contracts() -> None:
    first = _snapshot(0, (("A", 7, "Alpha"),))
    second = _snapshot(1, (("B", 1, "Beta"),))
    analyzer = SelectionResearchItemQueryAnalyzer()
    with pytest.raises(ValueError, match="strictly chronological"):
        analyzer.analyze((second, first))
    with pytest.raises(ValueError, match="max_rank"):
        analyzer.analyze((first,), max_rank=0)
    report = analyzer.analyze((first, second))
    assert json.loads(selection_research_item_query_json(report)) == report.model_dump(mode="json")
    rows = list(csv.reader(StringIO(selection_research_item_query_csv(report))))
    assert rows[0] == [
        "snapshot_as_of", "strategy_name", "refresh_had_collection_failures", "rank", "symbol", "name", "board", "industry_code", "industry_name", "base_score", "confidence_adjusted_score", "data_completeness", "confidence", "quality_score", "value_score", "growth_score", "momentum_score", "low_volatility_score", "evidence_json", "risks_json",
    ]
    assert [row[4] for row in rows[1:]] == ["A", "B"]
