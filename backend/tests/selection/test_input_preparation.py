"""Offline orchestration contracts for ``selection prepare-inputs``."""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_selector import cli
from stock_selector.cli import main
from stock_selector.config import AppPaths, Settings
from stock_selector.providers import ProviderError
from stock_selector.storage import StorageError

NOW = datetime(2026, 9, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
MEMBERS = ("000001.SZ", "000002.SZ", "000003.SZ")


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    eligible: tuple[str, ...] = ("000002.SZ",),
    before: tuple[str, ...] = ("000001.SZ",),
    after: tuple[str, ...] = ("000001.SZ", "000002.SZ"),
    selected: tuple[str, ...] = ("000002.SZ",),
    slow_failure: str | None = None,
    has_more: bool = False,
    empty: bool = False,
    incomplete_risk: bool = False,
    risk_error: Exception | None = None,
) -> dict[str, object]:
    """Install a full offline graph and retain every orchestration boundary."""
    calls: dict[str, object] = {
        "provider": 0,
        "risk_collect": 0,
        "factor_reads": 0,
        "coverage_requests": [],
        "readiness_requests": [],
        "slow": 0,
        "now": 0,
        "universe_build": 0,
        "risk_read_count": 0,
        "risk_evaluate": 0,
        "planner": 0,
        "wrappers": {},
        "task35": 0,
        "task36_construct": 0,
    }
    original_paths = AppPaths.from_project_root
    settings = Settings()
    calls["settings"] = settings

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            calls["initialized"] = True

        def load_risk_states(self, as_of: date, symbols: tuple[str, ...]) -> tuple[SimpleNamespace, ...]:
            calls["risk_read_count"] = int(calls["risk_read_count"]) + 1
            calls["risk_read"] = (as_of, symbols)
            states = tuple(SimpleNamespace(symbol=symbol) for symbol in symbols)
            calls["risk_states"] = states
            return states

        def load_factor_input_symbols(self) -> tuple[str, ...]:
            calls["factor_reads"] = int(calls["factor_reads"]) + 1
            return before if calls["factor_reads"] == 1 else after

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, as_of: date) -> SimpleNamespace:
            calls["universe_build"] = int(calls["universe_build"]) + 1
            calls["universe_as_of"] = as_of
            structural = SimpleNamespace(members=MEMBERS)
            calls["structural"] = structural
            return structural

    class RiskCollector:
        def __init__(self, provider: object, repository: object) -> None:
            calls["risk_dependencies"] = (provider, repository)

        def collect(self, request: object) -> SimpleNamespace:
            calls["risk_collect"] = int(calls["risk_collect"]) + 1
            calls["risk_request"] = request
            if risk_error is not None:
                raise risk_error
            return SimpleNamespace(
                requested_symbols=request.symbols,
                states_persisted=len(request.symbols),
                st_members=0,
                suspended_members=0,
                delisting_period_members=0,
                observed_at=NOW,
                source="offline-fake",
            )

    class Evaluator:
        def evaluate(self, structural: object, states: object, config: object) -> SimpleNamespace:
            calls["risk_evaluate"] = int(calls["risk_evaluate"]) + 1
            calls["evaluate"] = (structural, states, config)
            complete = MEMBERS[:-1] if incomplete_risk else MEMBERS
            return SimpleNamespace(
                eligible_members=eligible,
                decisions=tuple(
                    SimpleNamespace(symbol=symbol, risk_complete=symbol in complete)
                    for symbol in MEMBERS
                ),
            )

    class Coverage:
        def audit(self, request: object) -> SimpleNamespace:
            requests = calls["coverage_requests"]
            assert isinstance(requests, list)
            requests.append(request)
            factors = request.factor_input_symbols
            return SimpleNamespace(
                structural_factor_input_covered=len(set(request.structural_symbols) & set(factors)),
                structural_factor_input_missing=len(set(request.structural_symbols) - set(factors)),
            )

    class Readiness:
        def audit(self, request: object) -> SimpleNamespace:
            requests = calls["readiness_requests"]
            assert isinstance(requests, list)
            requests.append(request)
            missing = tuple(symbol for symbol in request.risk_eligible_symbols if symbol not in request.factor_input_symbols)
            return SimpleNamespace(
                as_of=request.as_of,
                structural_members=len(request.structural_symbols),
                risk_complete_members=len(request.risk_complete_symbols),
                risk_incomplete_members=1 if incomplete_risk else 0,
                risk_eligible_members=len(request.risk_eligible_symbols),
                eligible_factor_input_covered=len(request.risk_eligible_symbols) - len(missing),
                eligible_factor_input_missing=len(missing),
                eligible_factor_input_missing_symbols=missing,
                upstream_inputs_ready=not missing and not incomplete_risk,
                blockers=(),
            )

    class Planner:
        def plan(self, request: object) -> SimpleNamespace:
            calls["planner"] = int(calls["planner"]) + 1
            calls["plan_request"] = request
            return SimpleNamespace(
                selected_symbols=selected,
                missing_after_cursor=len(request.missing_structural_symbols),
                selected_count=len(selected),
                selected_first_symbol=selected[0] if selected else None,
                selected_last_symbol=selected[-1] if selected else None,
                has_more_missing_after_selection=has_more,
                next_start_after=selected[-1] if selected else None,
            )

    def provider() -> object:
        calls["provider"] = int(calls["provider"]) + 1
        return SimpleNamespace(name="provider")

    def base(name: str):
        def constructor(provider: object, repository: object) -> SimpleNamespace:
            dependencies = calls.setdefault("base_dependencies", [])
            assert isinstance(dependencies, list)
            dependencies.append((name, provider, repository))
            return SimpleNamespace(name=name)

        return constructor

    def wrapper(name: str):
        class Wrapper:
            def __init__(self, *_: object) -> None:
                wrappers = calls["wrappers"]
                assert isinstance(wrappers, dict)
                wrappers[name] = int(wrappers.get(name, 0)) + 1
                if name == "task35":
                    calls["task35"] = int(calls["task35"]) + 1

        return Wrapper

    class Sweep:
        def __init__(self, task35: object) -> None:
            calls["task36_construct"] = int(calls["task36_construct"]) + 1
            calls["task36_task35"] = task35

        def collect(self, request: object) -> SimpleNamespace:
            calls["slow"] = int(calls["slow"]) + 1
            calls["slow_request"] = request
            failed = (selected[0],) if slow_failure else ()
            success = 0 if empty else 1
            empty_count = 1 if empty else 0
            core = SimpleNamespace(financial_success=success, financial_empty=empty_count, financial_failed=failed if slow_failure == "financial" else (), industry_success=success, industry_empty=empty_count, industry_failed=failed if slow_failure == "industry" else ())
            valuation = SimpleNamespace(success_symbols=success, empty_symbols=empty_count, failed_symbols=failed if slow_failure == "valuation" else ())
            adjusted = SimpleNamespace(success_symbols=success, empty_symbols=empty_count, failed_symbols=failed if slow_failure == "adjusted" else (), availability_as_of=NOW)
            batch = SimpleNamespace(requested_symbols=request.symbols, batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1], core_report=core, valuation_report=valuation, adjusted_return_report=adjusted, factor_input_covered_after_run=len(after))
            return SimpleNamespace(batch_reports=(batch,), factor_input_covered_after_run=len(after))

    monkeypatch.setattr(cli, "load_settings", lambda _path: settings)
    monkeypatch.setattr(cli.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    def now(_timezone: object) -> datetime:
        calls["now"] = int(calls["now"]) + 1
        return NOW

    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider)
    monkeypatch.setattr("stock_selector.collection.CurrentRiskStateCollector", RiskCollector)
    monkeypatch.setattr("stock_selector.risk.evaluator.RiskEligibilityEvaluator", Evaluator)
    monkeypatch.setattr("stock_selector.collection.StructuralFactorInputCoverageAuditor", Coverage)
    monkeypatch.setattr("stock_selector.selection.DailySelectionInputReadinessAuditor", Readiness)
    monkeypatch.setattr("stock_selector.collection.StructuralMissingRefreshPlanner", Planner)
    monkeypatch.setattr("stock_selector.collection.FinancialCollector", base("financial"))
    monkeypatch.setattr("stock_selector.collection.IndustryCollector", base("industry"))
    monkeypatch.setattr("stock_selector.collection.ValuationCollector", base("valuation"))
    monkeypatch.setattr("stock_selector.collection.AdjustedDailyReturnCollector", base("adjusted"))
    for target, name in (
        ("StructuralCoreFundamentalsCollector", "core"),
        ("StructuralValuationCollector", "valuation"),
        ("StructuralAdjustedReturnCollector", "adjusted"),
        ("StructuralSlowInputCollector", "task35"),
    ):
        monkeypatch.setattr(f"stock_selector.collection.{target}", wrapper(name))
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputSweepCollector", Sweep)
    return calls


@pytest.mark.parametrize("argument", ("0", "101", "not-a-symbol", "300001.SZ"))
def test_prepare_inputs_rejects_invalid_bounds_before_provider_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argument: str) -> None:
    calls = _install(monkeypatch, tmp_path)
    command = ["selection", "prepare-inputs", "--limit", argument]
    if argument in ("not-a-symbol", "300001.SZ"):
        command = ["selection", "prepare-inputs", "--limit", "1", "--start-after", argument]
    assert main(command) == 1
    assert calls["provider"] == calls["risk_collect"] == calls["slow"] == 0


def test_prepare_inputs_refreshes_risk_then_one_eligible_missing_slice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    calls = _install(monkeypatch, tmp_path, has_more=True)
    for target in (
        "stock_selector.selection.DailySelectionService",
        "stock_selector.factors.FiveFactorEngine",
        "stock_selector.scoring.BaseScoreEngine",
        "stock_selector.explanation.ExplanationEngine",
        "stock_selector.realtime.RealtimeSelectionRuntimeService",
    ):
        monkeypatch.setattr(
            target,
            lambda target=target: (_ for _ in ()).throw(AssertionError(target)),
        )
    assert main(["selection", "prepare-inputs", "--limit", "1", "--start-after", "000001.SZ"]) == 0
    assert calls["now"] == calls["universe_build"] == 1
    assert calls["universe_as_of"] == NOW.date()
    risk_request = calls["risk_request"]
    assert (risk_request.symbols, risk_request.as_of) == (MEMBERS, NOW.date())
    assert calls["risk_read"] == (NOW.date(), MEMBERS)
    assert calls["risk_read_count"] == calls["risk_evaluate"] == 1
    structural, states, config = calls["evaluate"]
    assert structural is calls["structural"]
    assert states is calls["risk_states"]
    assert config is calls["settings"].universe
    assert calls["provider"] == calls["risk_collect"] == calls["slow"] == 1
    assert calls["factor_reads"] == 2
    plan = calls["plan_request"]
    slow = calls["slow_request"]
    assert plan.missing_structural_symbols == ("000002.SZ",)
    assert (plan.as_of, plan.structural_symbols) == (NOW, MEMBERS)
    assert (plan.limit, plan.start_after) == (1, "000001.SZ")
    assert slow.symbols == ("000002.SZ",)
    assert (slow.as_of, slow.has_more_structural_members) == (NOW, False)
    dependencies = calls["base_dependencies"]
    assert isinstance(dependencies, list)
    assert [item[0] for item in dependencies] == ["financial", "industry", "valuation", "adjusted"]
    assert len({id(item[1]) for item in dependencies}) == 1
    assert calls["risk_dependencies"][0] is dependencies[0][1]
    assert calls["task35"] == calls["task36_construct"] == 1
    wrappers = calls["wrappers"]
    assert wrappers == {"core": 1, "valuation": 1, "adjusted": 1, "task35": 1}
    coverage = calls["coverage_requests"]
    readiness = calls["readiness_requests"]
    assert isinstance(coverage, list) and isinstance(readiness, list)
    assert len(coverage) == len(readiness) == 2
    assert (coverage[0].as_of, coverage[0].structural_symbols, coverage[0].factor_input_symbols) == (NOW, MEMBERS, ("000001.SZ",))
    assert (coverage[1].as_of, coverage[1].structural_symbols, coverage[1].factor_input_symbols) == (NOW, MEMBERS, ("000001.SZ", "000002.SZ"))
    for request, factors in zip(readiness, (("000001.SZ",), ("000001.SZ", "000002.SZ")), strict=True):
        assert (request.as_of, request.structural_symbols) == (NOW, MEMBERS)
        assert request.risk_record_symbols == MEMBERS
        assert request.risk_complete_symbols == MEMBERS
        assert request.risk_eligible_symbols == ("000002.SZ",)
        assert request.factor_input_symbols == factors
    output = capsys.readouterr().out
    assert "Post-slow structural factor-input missing: 1" in output
    assert "Pre-slow upstream inputs ready: NO" in output
    assert "Post-slow upstream inputs ready: YES" in output
    assert "Post-slow eligible factor-input missing: 0" in output
    assert "Has more eligible missing after selection: YES" in output
    assert "Next eligible-missing start-after: 000002.SZ" in output
    assert "Preparation does not run DailySelectionService" in output
    assert "selection_ready" not in output


@pytest.mark.parametrize(
    ("eligible", "before", "selected", "message"),
    (((), (), (), "No risk-eligible structural members"), (("000002.SZ",), ("000002.SZ",), (), "already ready"), (("000002.SZ",), (), (), "after start-after")),
)
def test_prepare_inputs_zero_target_paths_skip_slow_graph(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], eligible: tuple[str, ...], before: tuple[str, ...], selected: tuple[str, ...], message: str) -> None:
    calls = _install(monkeypatch, tmp_path, eligible=eligible, before=before, selected=selected)
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 0
    assert calls["risk_collect"] == 1
    assert calls["slow"] == 0
    assert calls["task35"] == calls["task36_construct"] == 0
    assert calls["wrappers"] == {}
    assert calls["factor_reads"] == 1
    assert message in capsys.readouterr().out


def test_prepare_inputs_accepts_covered_ineligible_cursor_and_exhausts_eligible_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    calls = _install(monkeypatch, tmp_path, eligible=("000002.SZ",), selected=())
    assert main(["selection", "prepare-inputs", "--limit", "1", "--start-after", "000001.SZ"]) == 0
    assert calls["plan_request"].start_after == "000001.SZ"
    assert calls["planner"] == calls["risk_collect"] == 1
    assert calls["slow"] == calls["task35"] == calls["task36_construct"] == 0
    assert calls["factor_reads"] == 1
    output = capsys.readouterr().out
    assert "No eligible factor-input-missing members after start-after." in output
    assert "already ready" not in output


def test_prepare_inputs_allows_empty_slow_results_without_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    calls = _install(monkeypatch, tmp_path, after=("000001.SZ",), empty=True)
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 0
    assert calls["slow"] == 1
    assert calls["factor_reads"] == 2
    assert "Post-slow upstream inputs ready: NO" in capsys.readouterr().out


def test_prepare_inputs_reports_remaining_eligible_work_without_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _install(
        monkeypatch,
        tmp_path,
        eligible=("000002.SZ", "000003.SZ"),
        after=("000001.SZ", "000002.SZ"),
        has_more=True,
    )
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 0
    output = capsys.readouterr().out
    assert "Has more eligible missing after selection: YES" in output
    assert "Next eligible-missing start-after: 000002.SZ" in output
    assert "Post-slow upstream inputs ready: NO" in output


@pytest.mark.parametrize("failure", ("financial", "industry", "valuation", "adjusted"))
def test_prepare_inputs_returns_one_for_nested_slow_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str) -> None:
    calls = _install(monkeypatch, tmp_path, slow_failure=failure)
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 1
    assert calls["slow"] == 1
    assert calls["factor_reads"] == 2
    coverage = calls["coverage_requests"]
    readiness = calls["readiness_requests"]
    assert isinstance(coverage, list) and isinstance(readiness, list)
    assert len(coverage) == len(readiness) == 2


@pytest.mark.parametrize(
    "error",
    (StorageError("risk write"), ProviderError("offline-fake", "risk", "provider")),
)
def test_prepare_inputs_aborts_for_typed_risk_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception) -> None:
    storage_calls = _install(monkeypatch, tmp_path, risk_error=error)
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 1
    assert storage_calls["slow"] == storage_calls["task35"] == 0


def test_prepare_inputs_stops_before_planning_for_incomplete_risk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    incomplete_calls = _install(monkeypatch, tmp_path, incomplete_risk=True)
    assert main(["selection", "prepare-inputs", "--limit", "1"]) == 1
    assert incomplete_calls["slow"] == 0
    assert incomplete_calls["planner"] == incomplete_calls["task36_construct"] == 0
