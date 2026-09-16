"""Offline graph contracts for ``selection daily``."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_selector import cli
from stock_selector.cli import main
from stock_selector.config import Settings

NOW = datetime(2026, 9, 15, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
STRUCTURAL = SimpleNamespace(members=("000001.SZ",))


def _forbidden(name: str):
    def fail(*_args: object, **_kwargs: object) -> None: raise AssertionError(name)
    return fail


@pytest.mark.parametrize(("mode", "expected"), (("ready", 0), ("blocked", 0), ("failed_blocked", 1), ("failed_ready", 1), ("boom", 1)))
def test_daily_cli_uses_one_shared_graph_and_maps_outcomes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str, expected: int) -> None:
    names = ("paths", "settings", "repository", "initialize", "now", "universe", "build_current", "provider", "refresh_service", "daily_service", "workflow_service", "workflow_run")
    calls: dict[str, object] = {name: 0 for name in names}
    settings = Settings()
    provider, risk, financial, industry, valuation, adjusted = (object() for _ in range(6))
    core, structural_valuation, structural_adjusted, task35, sweep = (object() for _ in range(5))
    selection_result = SimpleNamespace(diagnostics=SimpleNamespace(selection_ready=mode in ("ready", "failed_ready"), blockers=("blocked",) if mode in ("blocked", "failed_blocked") else ()))
    report = SimpleNamespace(refresh_report=SimpleNamespace(had_collection_failures=mode.startswith("failed")), selection_result=selection_result, had_collection_failures=mode.startswith("failed"))
    class Repository:
        def __init__(self, _paths: object) -> None: calls["repository"] += 1; calls["repository_obj"] = self
        def initialize(self) -> None: calls["initialize"] += 1
    class Universe:
        def __init__(self, repository_arg: object, settings_arg: object) -> None:
            calls["universe"] += 1; assert repository_arg is calls["repository_obj"] and settings_arg is settings
        def build_current(self, as_of: object) -> object: calls["build_current"] += 1; assert as_of == NOW.date(); return STRUCTURAL
    def leaf(result: object):
        def construct(provider_arg: object, repository_arg: object) -> object: assert provider_arg is provider and repository_arg is calls["repository_obj"]; return result
        return construct
    def provider_factory() -> object: calls["provider"] += 1; return provider
    def core_factory(f: object, i: object, r: object) -> object: assert (f, i, r) == (financial, industry, calls["repository_obj"]); return core
    def valuation_factory(v: object, r: object) -> object: assert (v, r) == (valuation, calls["repository_obj"]); return structural_valuation
    def adjusted_factory(a: object, r: object) -> object: assert (a, r) == (adjusted, calls["repository_obj"]); return structural_adjusted
    def task35_factory(c: object, v: object, a: object, r: object) -> object: assert (c, v, a, r) == (core, structural_valuation, structural_adjusted, calls["repository_obj"]); return task35
    def sweep_factory(value: object) -> object: assert value is task35; return sweep
    class Refresh:
        def __init__(self, r: object, s: object, risk_arg: object, sweep_arg: object) -> None: calls["refresh_service"] += 1; calls["refresh_obj"] = self; assert (r, s, risk_arg, sweep_arg) == (calls["repository_obj"], settings, risk, sweep)
    class Daily:
        def __init__(self, r: object, s: object) -> None: calls["daily_service"] += 1; calls["daily_obj"] = self; assert (r, s) == (calls["repository_obj"], settings)
    class Workflow:
        def __init__(self, r: object, d: object) -> None: calls["workflow_service"] += 1; assert r is calls["refresh_obj"] and d is calls["daily_obj"]
        def run(self, current_at: object, structural: object) -> object:
            calls["workflow_run"] += 1; assert (current_at, structural) == (NOW, STRUCTURAL)
            if mode == "boom": raise ValueError("boom")
            return report
    monkeypatch.setattr(cli.AppPaths, "from_project_root", lambda: calls.__setitem__("paths", calls["paths"] + 1) or SimpleNamespace(config_dir=Path("config")))
    monkeypatch.setattr(cli, "load_settings", lambda _path: calls.__setitem__("settings", calls["settings"] + 1) or settings)
    def now(zone: ZoneInfo) -> datetime: calls["now"] += 1; assert zone == ZoneInfo(settings.app.timezone); return NOW
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository); monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe); monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    for name, result in (("CurrentRiskStateCollector", risk), ("FinancialCollector", financial), ("IndustryCollector", industry), ("ValuationCollector", valuation), ("AdjustedDailyReturnCollector", adjusted)): monkeypatch.setattr(f"stock_selector.collection.{name}", leaf(result))
    for name, factory in (("StructuralCoreFundamentalsCollector", core_factory), ("StructuralValuationCollector", valuation_factory), ("StructuralAdjustedReturnCollector", adjusted_factory), ("StructuralSlowInputCollector", task35_factory), ("StructuralSlowInputSweepCollector", sweep_factory)): monkeypatch.setattr(f"stock_selector.collection.{name}", factory)
    monkeypatch.setattr("stock_selector.selection.CurrentSelectionRefreshService", Refresh); monkeypatch.setattr("stock_selector.selection.DailySelectionService", Daily); monkeypatch.setattr("stock_selector.selection.CurrentDailySelectionWorkflowService", Workflow)
    for name in ("_run_selection_refresh_current_command", "_run_selection_run_current_command", "_run_selection_prepare_inputs_command"): monkeypatch.setattr(cli, name, _forbidden(name))
    events: list[str] = []
    monkeypatch.setattr(cli, "_print_selection_refresh_current_report", lambda _: events.append("refresh"))
    seen_selection: list[object] = []
    monkeypatch.setattr(cli, "_print_daily_selection_execution", lambda value: events.append("selection") or seen_selection.append(value))
    assert main(["selection", "daily"]) == expected
    assert all(calls[name] == 1 for name in names)
    captured = capsys.readouterr()
    if mode == "boom": assert "Daily selection workflow error: boom" in captured.err and events == []
    else: assert events == ["refresh", "selection"] and seen_selection == [selection_result]
