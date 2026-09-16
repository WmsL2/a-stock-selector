"""Focused contracts for current refresh followed by official selection."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.selection import (
    CurrentSelectionRefreshReport,
    CurrentSelectionRefreshStep,
    DailySelectionResult,
)
from stock_selector.selection.current_workflow import (
    CurrentDailySelectionWorkflowReport,
    CurrentDailySelectionWorkflowService,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def _reports() -> tuple[CurrentSelectionRefreshReport, DailySelectionResult]:
    symbols = ("000001.SZ", "000002.SZ")
    readiness = SimpleNamespace(
        risk_records=2,
        risk_complete_members=2,
        risk_eligible_members=1,
        eligible_factor_input_covered=1,
        eligible_factor_input_missing_symbols=("000001.SZ",),
    )
    coverage = SimpleNamespace(
        as_of=NOW,
        structural_symbols=symbols,
        risk_record_symbols=symbols,
        risk_complete_symbols=symbols,
        risk_eligible_symbols=("000001.SZ",),
        input_readiness=readiness,
    )
    plan = SimpleNamespace(
        as_of=NOW,
        structural_symbols=symbols,
        missing_structural_symbols=("000001.SZ",),
        selected_symbols=("000001.SZ",),
        selected_count=1,
        selected_last_symbol="000001.SZ",
        limit=100,
        start_after=None,
    )
    sweep = SimpleNamespace(
        as_of=NOW,
        requested_symbols=("000001.SZ",),
        has_more_structural_members=False,
        batch_reports=(
            SimpleNamespace(
                core_report=SimpleNamespace(financial_failed=("000001.SZ",), industry_failed=()),
                valuation_report=SimpleNamespace(failed_symbols=()),
                adjusted_return_report=SimpleNamespace(failed_symbols=()),
            ),
        ),
    )
    step = CurrentSelectionRefreshStep.model_construct(
        plan=plan, sweep_report=sweep, coverage_after=coverage
    )
    refresh = CurrentSelectionRefreshReport.model_construct(
        as_of=NOW,
        structural_symbols=symbols,
        risk_collection_result=SimpleNamespace(as_of=NOW.date(), requested_symbols=symbols),
        initial_coverage=coverage,
        steps=(step,),
        final_coverage=coverage,
        attempted_symbols=("000001.SZ",),
        had_collection_failures=True,
    )
    selection = DailySelectionResult.model_construct(
        as_of=NOW,
        diagnostics=SimpleNamespace(
            as_of=NOW,
            selection_ready=False,
            returned_items=0,
            structural_members=2,
            risk_records=2,
            risk_complete_members=2,
            risk_eligible_members=1,
            factor_input_members=1,
        ),
        selection=SimpleNamespace(as_of=NOW, items=()),
    )
    return refresh, selection


def test_real_combined_report_accepts_aligned_snapshots_and_derives_failure() -> None:
    refresh, selection = _reports()
    report = CurrentDailySelectionWorkflowReport(as_of=NOW, refresh_report=refresh, selection_result=selection)
    assert report.refresh_report is refresh and report.had_collection_failures is True


@pytest.mark.parametrize("field", ("top", "refresh", "selection", "diagnostics", "payload", "structural", "records", "complete", "eligible", "factor"))
def test_real_combined_report_rejects_snapshot_tampering(field: str) -> None:
    refresh, selection = _reports()
    as_of = NOW.replace(day=14) if field == "top" else NOW
    if field == "refresh": refresh = refresh.model_copy(update={"as_of": NOW.replace(day=14)})
    if field == "selection": selection = selection.model_copy(update={"as_of": NOW.replace(day=14)})
    if field == "diagnostics": selection.diagnostics.as_of = NOW.replace(day=14)
    if field == "payload": selection.selection.as_of = NOW.replace(day=14)
    if field == "structural": selection.diagnostics.structural_members = 3
    if field == "records": refresh.final_coverage.input_readiness.risk_records = 1
    if field == "complete": refresh.final_coverage.input_readiness.risk_complete_members = 1
    if field == "eligible": refresh.final_coverage.input_readiness.risk_eligible_members = 0
    if field == "factor": refresh.final_coverage.input_readiness.eligible_factor_input_covered = 0
    with pytest.raises((ValidationError, ValueError)):
        CurrentDailySelectionWorkflowReport(as_of=as_of, refresh_report=refresh, selection_result=selection)


def test_real_combined_report_rejects_naive_top_level_as_of() -> None:
    refresh, selection = _reports()
    with pytest.raises((ValidationError, ValueError)):
        CurrentDailySelectionWorkflowReport(
            as_of=NOW.replace(tzinfo=None),
            refresh_report=refresh,
            selection_result=selection,
        )


def test_nested_refresh_failure_still_runs_official_selection() -> None:
    calls: list[tuple[str, object]] = []
    refresh_report, selection_result = _reports()
    class Refresh:
        def refresh(self, at: datetime, structural: object) -> object:
            calls.append(("refresh", at)); assert structural is snapshot; return refresh_report
    class Selection:
        def build(self, at: datetime) -> object:
            calls.append(("selection", at)); return selection_result
    snapshot = object()
    report = CurrentDailySelectionWorkflowService(Refresh(), Selection()).run(NOW, snapshot)
    assert calls == [("refresh", NOW), ("selection", NOW)]
    assert refresh_report.had_collection_failures is True
    assert report.refresh_report is refresh_report and report.selection_result is selection_result
    assert report.had_collection_failures is True


def test_refresh_exception_prevents_selection() -> None:
    class Refresh:
        def refresh(self, *_: object) -> object: raise ValueError("refresh")
    class Selection:
        def build(self, *_: object) -> object: raise AssertionError("selection")
    with pytest.raises(ValueError, match="refresh"):
        CurrentDailySelectionWorkflowService(Refresh(), Selection()).run(NOW, object())


def test_selection_exception_propagates_after_one_refresh() -> None:
    refresh, _ = _reports()
    calls: list[str] = []
    class Refresh:
        def refresh(self, at: datetime, structural: object) -> CurrentSelectionRefreshReport:
            calls.append("refresh"); assert at is NOW and structural is snapshot; return refresh
    class Selection:
        def build(self, at: datetime) -> DailySelectionResult:
            calls.append("selection"); assert at is NOW; raise ValueError("selection boom")
    snapshot = object()
    with pytest.raises(ValueError, match="selection boom"):
        CurrentDailySelectionWorkflowService(Refresh(), Selection()).run(NOW, snapshot)
    assert calls == ["refresh", "selection"]


def test_workflow_rejects_naive_current_at() -> None:
    with pytest.raises(ValueError):
        CurrentDailySelectionWorkflowService(SimpleNamespace(), SimpleNamespace()).run(NOW.replace(tzinfo=None), object())


def test_workflow_source_has_no_forbidden_dependencies() -> None:
    source = (Path(__file__).parents[2] / "src/stock_selector/selection/current_workflow.py").read_text(encoding="utf-8")
    for forbidden in ("AKShareProvider", "stock_selector.providers", "stock_selector.collection", "datetime.now", "date.today", "FiveFactorEngine", "BaseScoreEngine", "ExplanationEngine", "FastAPI", "stock_selector.api", "stock_selector.realtime", "broker", "order"):
        assert forbidden not in source
