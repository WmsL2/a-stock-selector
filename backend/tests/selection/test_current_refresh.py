"""Offline regression contracts for Task45 current refresh orchestration."""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    CurrentRiskCollectionResult,
    StructuralSlowInputSweepReport,
)
from stock_selector.config import Settings
from stock_selector.risk import DatedRiskState
from stock_selector.selection import (
    CurrentSelectionRefreshReport,
    CurrentSelectionRefreshService,
)
from stock_selector.universe.models import UniverseDecision, UniverseSnapshot

NOW = datetime(2026, 9, 14, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def symbols(count: int) -> tuple[str, ...]:
    return tuple(f"{index:06d}.SZ" for index in range(1, count + 1))


class Repository:
    def __init__(self, members: tuple[str, ...], eligible: bool = True) -> None:
        self.members, self.eligible, self.covered = members, eligible, set[str]()
        self.risk_reads = 0
        self.reads = {name: 0 for name in ("financial", "valuation", "industry", "factor", "adjusted")}

    def load_risk_states(self, as_of: date, received: tuple[str, ...]) -> tuple[DatedRiskState, ...]:
        self.risk_reads += 1
        assert received == self.members
        return tuple(DatedRiskState(symbol=symbol, as_of=as_of, is_st=not self.eligible, is_suspended=False, is_delisting_period=False, observed_at=NOW, source="test") for symbol in received)

    def load_financial_symbols(self) -> tuple[str, ...]: self.reads["financial"] += 1; return tuple(sorted(self.covered))
    def load_valuation_symbols(self) -> tuple[str, ...]: self.reads["valuation"] += 1; return ()
    def load_industry_symbols(self) -> tuple[str, ...]: self.reads["industry"] += 1; return tuple(sorted(self.covered))
    def load_factor_input_symbols(self) -> tuple[str, ...]: self.reads["factor"] += 1; return tuple(sorted(self.covered))
    def load_adjusted_return_symbols(self) -> tuple[str, ...]: self.reads["adjusted"] += 1; return tuple(sorted(self.covered))


class RiskCollector:
    def __init__(self) -> None: self.calls = 0
    def collect(self, request: object) -> CurrentRiskCollectionResult:
        self.calls += 1
        return CurrentRiskCollectionResult(as_of=request.as_of, requested_symbols=request.symbols, states_received=len(request.symbols), states_persisted=len(request.symbols), st_members=0, suspended_members=0, delisting_period_members=0, observed_at=NOW, source="test")


class Sweep:
    def __init__(self, repository: Repository, failed: set[str] | None = None, empty: set[str] | None = None) -> None:
        self.repository, self.failed, self.empty = repository, failed or set(), empty or set()
        self.requests: list[object] = []
    def collect(self, request: object) -> StructuralSlowInputSweepReport:
        self.requests.append(request)
        self.repository.covered.update(set(request.symbols) - self.failed - self.empty)
        failed = tuple(sorted(set(request.symbols) & self.failed))
        batches = []
        for index in range(0, len(request.symbols), 20):
            chunk = request.symbols[index:index + 20]
            chunk_failed = tuple(symbol for symbol in chunk if symbol in failed)
            batches.append(SimpleNamespace(
                requested_symbols=chunk, as_of=request.as_of,
                batch_first_symbol=chunk[0], batch_last_symbol=chunk[-1],
                has_more_structural_members=index + 20 < len(request.symbols),
                next_start_after=chunk[-1] if index + 20 < len(request.symbols) else None,
                factor_input_covered_after_run=len(chunk) - len(chunk_failed),
                core_report=SimpleNamespace(financial_failed=chunk_failed, industry_failed=()),
                valuation_report=SimpleNamespace(failed_symbols=()),
                adjusted_return_report=SimpleNamespace(failed_symbols=()),
            ))
        return StructuralSlowInputSweepReport.model_construct(as_of=request.as_of, requested_symbols=request.symbols, batch_reports=tuple(batches), factor_input_covered_after_run=len(request.symbols) - len(failed), batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1], has_more_structural_members=request.has_more_structural_members, next_start_after=None)


class NoSweep:
    def collect(self, _request: object) -> object: raise AssertionError("slow refresh must not run")


def structural(members: tuple[str, ...]) -> UniverseSnapshot:
    return UniverseSnapshot(as_of=NOW.date(), input_count=len(members), members=members, decisions=tuple(UniverseDecision(symbol=symbol, included=True) for symbol in members))


def run(count: int, *, eligible: bool = True, failed: set[str] | None = None, empty: set[str] | None = None):
    members = symbols(count); repository, collector = Repository(members, eligible), RiskCollector(); sweep = Sweep(repository, failed, empty)
    report = CurrentSelectionRefreshService(repository, Settings(), collector, sweep).refresh(NOW, structural(members))
    return report, repository, collector, sweep


def test_already_ready_has_one_risk_snapshot_and_no_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    members = symbols(2); repository, collector = Repository(members), RiskCollector(); repository.covered.update(members)
    from stock_selector.risk.evaluator import RiskEligibilityEvaluator
    original, calls = RiskEligibilityEvaluator.evaluate, {"evaluate": 0}
    def evaluate(self: object, snapshot: object, states: object, config: object) -> object:
        calls["evaluate"] += 1; return original(self, snapshot, states, config)
    monkeypatch.setattr(RiskEligibilityEvaluator, "evaluate", evaluate)
    report = CurrentSelectionRefreshService(repository, Settings(), collector, NoSweep()).refresh(NOW, structural(members))
    assert collector.calls == repository.risk_reads == calls["evaluate"] == 1
    assert report.initial_coverage == report.final_coverage and report.steps == ()


def test_zero_risk_eligible_is_normal_not_ready_completion() -> None:
    report, _, collector, sweep = run(2, eligible=False)
    assert collector.calls == 1 and not sweep.requests and not report.had_collection_failures
    assert not report.final_coverage.input_readiness.upstream_inputs_ready


def test_one_missing_sweeps_once_and_reaudits() -> None:
    report, repository, _, sweep = run(1)
    step = report.steps[0]
    assert report.attempted_symbols == symbols(1) and len(sweep.requests) == 1
    assert step.plan.limit == 100 and step.plan.start_after is None and not step.sweep_report.has_more_structural_members
    assert step.coverage_after.input_readiness.upstream_inputs_ready
    assert all(value == 2 for value in repository.reads.values())


@pytest.mark.parametrize(("count", "sizes"), ((100, (100,)), (101, (100, 1)), (201, (100, 100, 1))))
def test_outer_batches_are_bounded_forward_and_nonduplicating(count: int, sizes: tuple[int, ...]) -> None:
    report, repository, collector, sweep = run(count)
    assert tuple(len(request.symbols) for request in sweep.requests) == sizes
    assert report.attempted_symbols == symbols(count) and len(set(report.attempted_symbols)) == count
    assert collector.calls == repository.risk_reads == 1 and report.final_coverage.input_readiness.upstream_inputs_ready
    assert [step.plan.start_after for step in report.steps] == [None, *[step.plan.selected_last_symbol for step in report.steps[:-1]]]
    assert all(step.plan.limit == 100 and step.sweep_report.as_of == NOW for step in report.steps)


def test_failed_early_member_is_not_retried_and_later_batches_continue() -> None:
    report, _, _, sweep = run(201, failed={"000003.SZ"})
    assert report.had_collection_failures and report.attempted_symbols.count("000003.SZ") == 1
    assert len(sweep.requests) == 3 and sweep.requests[-1].symbols == ("000201.SZ",)
    assert not report.final_coverage.input_readiness.upstream_inputs_ready


def test_empty_member_is_not_failure_or_retry() -> None:
    report, _, _, sweep = run(101, empty={"000003.SZ"})
    assert not report.had_collection_failures and report.attempted_symbols.count("000003.SZ") == 1
    assert len(sweep.requests) == 2 and not report.final_coverage.input_readiness.upstream_inputs_ready


def test_adjusted_return_only_evidence_does_not_change_initial_target() -> None:
    report, _, _, _ = run(1, empty={"000001.SZ"})
    assert report.initial_coverage.factor_input_symbols == ()
    assert report.initial_coverage.input_readiness.eligible_factor_input_missing_symbols == ("000001.SZ",)


@pytest.mark.parametrize("mutation", ("as_of", "structural", "risk_request", "first_cursor", "limit", "duplicate", "attempted", "final", "failures"))
def test_report_rejects_tampered_outer_contract(mutation: str) -> None:
    report, _, _, _ = run(101); values = report.model_dump()
    if mutation == "as_of": values["as_of"] = NOW.replace(day=13)
    elif mutation == "structural": values["structural_symbols"] = symbols(100)
    elif mutation == "risk_request": values["risk_collection_result"] = report.risk_collection_result.model_copy(update={"requested_symbols": symbols(100)})
    elif mutation == "first_cursor": values["steps"][0]["plan"]["start_after"] = "000001.SZ"
    elif mutation == "limit": values["steps"][0]["plan"]["limit"] = 99
    elif mutation == "duplicate": values["steps"][1]["plan"]["selected_symbols"] = values["steps"][0]["plan"]["selected_symbols"]
    elif mutation == "attempted": values["attempted_symbols"] = symbols(100)
    elif mutation == "final": values["final_coverage"] = report.initial_coverage.model_copy()
    else: values["had_collection_failures"] = True
    with pytest.raises(ValidationError): CurrentSelectionRefreshReport.model_validate(values)


def test_current_refresh_source_has_no_forbidden_runtime_dependencies() -> None:
    source = (Path(__file__).parents[2] / "src/stock_selector/selection/current_refresh.py").read_text(encoding="utf-8")
    for forbidden in ("AKShareProvider", "stock_selector.providers", "datetime.now", "date.today", "FastAPI", "stock_selector.api", "stock_selector.realtime", "stock_selector.factors", "stock_selector.scoring", "stock_selector.explanation"):
        assert forbidden not in source
