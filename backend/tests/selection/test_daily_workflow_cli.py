"""Offline graph contracts for ``selection daily``."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_selector import cli
from stock_selector.cli import main
from stock_selector.config import Settings

from .test_daily import (
    _AS_OF,
    _financial,
    _industry,
    _repository,
    _returns,
    _risk,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
STRUCTURAL = SimpleNamespace(members=("000001.SZ",))


def _forbidden(name: str):
    def fail(*_args: object, **_kwargs: object) -> None: raise AssertionError(name)
    return fail


@pytest.mark.parametrize(("mode", "expected"), (("ready", 0), ("blocked", 0), ("failed_blocked", 1), ("failed_ready", 1), ("boom", 1)))
def test_daily_cli_uses_one_shared_graph_and_maps_outcomes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str, expected: int) -> None:
    names = ("paths", "settings", "repository", "initialize", "now", "universe", "build_current", "provider", "refresh_service", "daily_service", "workflow_service", "workflow_run", "research_builder", "research_build", "research_store", "research_export")
    calls: dict[str, object] = {name: 0 for name in names}
    settings = Settings()
    provider, risk, financial, industry, valuation = (object() for _ in range(5))
    core, structural_valuation, task35, sweep = (object() for _ in range(4))
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
    def task35_factory(c: object, v: object, a: object, r: object) -> object: assert (c, v, a, r) == (core, structural_valuation, None, calls["repository_obj"]); return task35
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
    snapshot = object()
    class Builder:
        def __init__(self, repository_arg: object, settings_arg: object) -> None: calls["research_builder"] += 1; assert repository_arg is calls["repository_obj"] and settings_arg is settings
        def build(self, result: object, *, refresh_had_collection_failures: bool) -> object: calls["research_build"] += 1; assert result is selection_result and refresh_had_collection_failures is report.had_collection_failures; return snapshot
    class Store:
        def __init__(self, paths_arg: object) -> None: calls["research_store"] += 1; assert paths_arg is calls["paths_obj"]
        def export(self, value: object) -> object: calls["research_export"] += 1; assert value is snapshot; return SimpleNamespace(json_path="runtime/snapshots/selection/test/selection.json", csv_path="runtime/snapshots/selection/test/selection.csv")
    def paths_factory() -> object:
        calls["paths"] += 1; value = SimpleNamespace(config_dir=Path("config"), snapshots_dir=Path("runtime/snapshots")); calls["paths_obj"] = value; return value
    monkeypatch.setattr(cli.AppPaths, "from_project_root", paths_factory)
    monkeypatch.setattr(cli, "load_settings", lambda _path: calls.__setitem__("settings", calls["settings"] + 1) or settings)
    def now(zone: ZoneInfo) -> datetime: calls["now"] += 1; assert zone == ZoneInfo(settings.app.timezone); return NOW
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository); monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe); monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    for name, result in (("CurrentRiskStateCollector", risk), ("FinancialCollector", financial), ("IndustryCollector", industry), ("ValuationCollector", valuation)): monkeypatch.setattr(f"stock_selector.collection.{name}", leaf(result))
    for name, factory in (("StructuralCoreFundamentalsCollector", core_factory), ("StructuralValuationCollector", valuation_factory), ("StructuralSlowInputCollector", task35_factory), ("StructuralSlowInputSweepCollector", sweep_factory)): monkeypatch.setattr(f"stock_selector.collection.{name}", factory)
    for name in ("AdjustedDailyReturnCollector", "StructuralAdjustedReturnCollector"):
        monkeypatch.setattr(f"stock_selector.collection.{name}", _forbidden(name))
    monkeypatch.setattr("stock_selector.selection.CurrentSelectionRefreshService", Refresh); monkeypatch.setattr("stock_selector.selection.DailySelectionService", Daily); monkeypatch.setattr("stock_selector.selection.CurrentDailySelectionWorkflowService", Workflow); monkeypatch.setattr("stock_selector.selection.SelectionResearchSnapshotBuilder", Builder); monkeypatch.setattr("stock_selector.selection.SelectionResearchArtifactStore", Store)
    for name in ("_run_selection_refresh_current_command", "_run_selection_run_current_command", "_run_selection_prepare_inputs_command"): monkeypatch.setattr(cli, name, _forbidden(name))
    events: list[str] = []
    monkeypatch.setattr(cli, "_print_selection_refresh_current_report", lambda _: events.append("refresh"))
    seen_selection: list[object] = []
    monkeypatch.setattr(cli, "_print_daily_selection_execution", lambda value: events.append("selection") or seen_selection.append(value))
    assert main(["selection", "daily"]) == expected
    captured = capsys.readouterr()
    if mode == "boom":
        assert all(calls[name] == 1 for name in names[:-4])
        assert "Daily selection workflow error: boom" in captured.err and events == []
        assert calls["research_builder"] == calls["research_build"] == calls["research_store"] == calls["research_export"] == 0
    else:
        assert all(calls[name] == 1 for name in names)
        assert events == ["refresh", "selection"] and seen_selection == [selection_result]
        assert "=== Selection research export ===" in captured.out


@pytest.mark.parametrize("command", ("prepare-inputs", "refresh-current", "daily"))
@pytest.mark.parametrize("stored_adjusted", (True, False))
def test_readiness_cli_real_collectors_never_fetch_hfq(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str], command: str, stored_adjusted: bool,
) -> None:
    """Exercise real persistence, readiness, and daily scoring with an offline provider."""
    from datetime import date

    from stock_selector.config import AppPaths
    from stock_selector.models import ValuationRecord
    from stock_selector.selection import DailySelectionService

    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path, symbols)
    returns = _returns(symbols[0], 60) if stored_adjusted else ()
    if returns:
        repository.upsert_adjusted_daily_returns(returns)
    assert repository.load_factor_input_symbols() == ()
    events: list[str] = []

    class Provider:
        def get_current_risk_states(self, request: object) -> tuple:
            events.append("risk")
            assert request.symbols == symbols and request.as_of == _AS_OF.date()
            return tuple(_risk(symbol) for symbol in request.symbols)

        def get_financial_records(self, request: object) -> tuple:
            events.append("financial")
            return tuple(_financial(symbol, period, 10) for symbol in request.symbols
                         for period in (date(2024, 12, 31), date(2025, 12, 31)))

        def get_industry_records(self, request: object) -> tuple:
            events.append("industry")
            return tuple(_industry(symbol) for symbol in request.symbols)

        def get_valuation_records(self, request: object) -> tuple:
            events.append("valuation")
            return tuple(ValuationRecord(symbol=symbol, as_of=request.as_of,
                                         pe=10, pb=2, pcf=5, source="offline")
                         for symbol in request.symbols)

        get_adjusted_daily_returns = _forbidden("HFQ request")

    original_paths = AppPaths.from_project_root
    monkeypatch.setattr(cli.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli, "load_settings", lambda _: Settings())
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _: _AS_OF))
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", Provider)
    for name in ("AdjustedDailyReturnCollector", "StructuralAdjustedReturnCollector"):
        monkeypatch.setattr(f"stock_selector.collection.{name}", _forbidden(name))
    original_build = DailySelectionService.build
    selections: list[object] = []

    def build(service: DailySelectionService, as_of: datetime) -> object:
        events.append("selection")
        assert service._repository.load_factor_input_symbols() == symbols
        factor_input = service._factor_input(symbols[0], as_of)
        assert (factor_input.adjusted_return_series is not None) is stored_adjusted
        result = original_build(service, as_of)
        selections.append(result)
        return result

    monkeypatch.setattr(DailySelectionService, "build", build)
    args = ["selection", command]
    if command == "prepare-inputs":
        args += ["--limit", "100"]
    assert main(args) == 0
    assert events[:7] == ["risk", "financial", "industry", "financial", "industry", "valuation", "valuation"]
    assert repository.load_factor_input_symbols() == symbols
    assert repository.load_adjusted_daily_returns(symbols[0]) == returns
    assert repository.load_adjusted_return_symbols() == ((symbols[0],) if stored_adjusted else ())
    output = capsys.readouterr().out
    assert "Adjusted-return refresh: skipped (optional; does not block readiness)" in output
    assert "Adjusted success / empty / failed:" not in output
    assert "upstream inputs ready: NO" in output
    assert "upstream inputs ready: YES" in output
    if command == "daily":
        assert events[-1] == "selection" and len(selections) == 1
        result = selections[0]
        assert result.diagnostics.selection_ready is True
        by_symbol = {item.symbol: item for item in result.selection.items}
        assert (by_symbol[symbols[0]].momentum_score is not None) is stored_adjusted
        assert by_symbol[symbols[1]].momentum_score is None
    else:
        assert selections == []
