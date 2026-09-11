"""Offline contracts for the current official daily-selection CLI adapter."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_selector import cli
from stock_selector.cli import main
from stock_selector.config import AppPaths, Settings
from stock_selector.models.selection import SelectionResult, StockScore
from stock_selector.selection import (
    DailySelectionDiagnostics,
    DailySelectionResult,
    SelectionBlocker,
    SelectionDataError,
)
from stock_selector.storage import StorageError

NOW = datetime(2026, 9, 10, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def _result(
    items: tuple[StockScore, ...] = (),
    blockers: tuple[SelectionBlocker, ...] = (),
) -> DailySelectionResult:
    diagnostics = DailySelectionDiagnostics(
        as_of=NOW,
        selection_ready=bool(items),
        blockers=blockers,
        input_instruments=3,
        structural_members=3,
        risk_records=3,
        risk_complete_members=3,
        risk_coverage_ratio=1.0,
        risk_eligible_members=2,
        factor_input_members=2,
        scoreable_members=len(items),
        requested_top_n=10,
        returned_items=len(items),
        price_factors_operational=True,
    )
    return DailySelectionResult(
        as_of=NOW,
        diagnostics=diagnostics,
        selection=SelectionResult(as_of=NOW, strategy_name="base_score_v1", items=items),
    )


def _item(symbol: str, rank: int, score: float, adjusted: float, momentum: float | None = None) -> StockScore:
    return StockScore(
        symbol=symbol,
        as_of=NOW,
        base_score=score,
        quality_score=70,
        value_score=71,
        growth_score=72,
        momentum_score=momentum,
        low_volatility_score=None,
        data_completeness=0.75,
        confidence=0.72,
        confidence_adjusted_score=adjusted,
        market_rank=rank,
    )


def _install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: DailySelectionResult | Exception) -> dict[str, object]:
    calls: dict[str, object] = {"paths": 0, "settings": 0, "repository": 0, "initialize": 0, "now": 0, "service": 0, "build": 0}
    settings = Settings()
    calls["settings_instance"] = settings
    original_paths = AppPaths.from_project_root

    class Repository:
        def __init__(self, paths: object) -> None:
            calls["repository"] = int(calls["repository"]) + 1
            calls["repository_instance"] = self
            calls["paths_instance"] = paths

        def initialize(self) -> None:
            calls["initialize"] = int(calls["initialize"]) + 1

        def save_instruments(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_daily_bars(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_adjusted_daily_returns(self, *_: object) -> None:
            raise AssertionError("write")

        def save_realtime_snapshot(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_risk_states(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_financial_records(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_valuation_records(self, *_: object) -> None:
            raise AssertionError("write")

        def upsert_industry_records(self, *_: object) -> None:
            raise AssertionError("write")

    class Service:
        def __init__(self, repository: object, received_settings: object) -> None:
            calls["service"] = int(calls["service"]) + 1
            calls["service_dependencies"] = (repository, received_settings)

        def build(self, as_of: datetime) -> DailySelectionResult:
            calls["build"] = int(calls["build"]) + 1
            calls["build_as_of"] = as_of
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    def paths() -> AppPaths:
        calls["paths"] = int(calls["paths"]) + 1
        return original_paths(tmp_path)

    def load(_path: Path) -> Settings:
        calls["settings"] = int(calls["settings"]) + 1
        return settings

    def now(timezone: object) -> datetime:
        calls["now"] = int(calls["now"]) + 1
        calls["timezone"] = timezone
        return NOW

    monkeypatch.setattr(cli.AppPaths, "from_project_root", paths)
    monkeypatch.setattr(cli, "load_settings", load)
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.selection.DailySelectionService", Service)
    for target in (
        "stock_selector.providers.AKShareProvider",
        "stock_selector.collection.CurrentRiskStateCollector",
        "stock_selector.collection.FinancialCollector",
        "stock_selector.collection.IndustryCollector",
        "stock_selector.collection.ValuationCollector",
        "stock_selector.collection.AdjustedDailyReturnCollector",
        "stock_selector.collection.StructuralSlowInputCollector",
        "stock_selector.collection.StructuralSlowInputSweepCollector",
        "stock_selector.universe.CurrentUniverseService",
        "stock_selector.risk.evaluator.RiskEligibilityEvaluator",
        "stock_selector.selection.DailySelectionInputReadinessAuditor",
        "stock_selector.collection.StructuralFactorInputCoverageAuditor",
        "stock_selector.factors.FiveFactorEngine",
        "stock_selector.scoring.BaseScoreEngine",
        "stock_selector.explanation.ExplanationEngine",
    ):
        monkeypatch.setattr(target, lambda target=target: (_ for _ in ()).throw(AssertionError(target)))
    monkeypatch.setattr(
        cli,
        "_run_selection_prepare_inputs_command",
        lambda *_: (_ for _ in ()).throw(AssertionError("prepare")),
    )
    return calls


def test_run_current_is_one_clock_thin_adapter_and_preserves_official_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = _result((_item("600519.SH", 1, 90, 20), _item("000001.SZ", 2, 80, 79)))
    calls = _install(monkeypatch, tmp_path, result)

    assert main(["selection", "run-current"]) == 0
    assert calls["paths"] == calls["settings"] == calls["repository"] == calls["initialize"] == calls["now"] == calls["service"] == calls["build"] == 1
    assert calls["service_dependencies"] == (
        calls["repository_instance"],
        calls["settings_instance"],
    )
    assert calls["build_as_of"] is NOW
    assert str(calls["timezone"]) == calls["settings_instance"].app.timezone
    captured = capsys.readouterr()
    output = captured.out
    assert "Official daily selection ready: YES" in output
    assert "Blockers: none" in output
    for line in (
        "Input instruments: 3",
        "Structural members: 3",
        "Exact-date risk records: 3",
        "Risk-complete members: 3",
        "Risk coverage: 100.00%",
        "Risk-eligible members: 2",
        "Eligible factor-input members: 2",
        "Scoreable members: 2",
        "Requested TopN: 10",
        "Returned items: 2",
        "Price factors operational: YES",
    ):
        assert line in output
    assert output.index("Rank 1: 600519.SH") < output.index("Rank 2: 000001.SZ")
    assert "confidence_adjusted_score=20.0000" in output
    assert "momentum=unavailable" in output and "low_volatility=unavailable" in output


@pytest.mark.parametrize("blocker", tuple(SelectionBlocker))
def test_run_current_reports_every_blocked_domain_state_as_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], blocker: SelectionBlocker) -> None:
    result = _result((), (blocker,))
    calls = _install(monkeypatch, tmp_path, result)
    assert main(["selection", "run-current"]) == 0
    captured = capsys.readouterr()
    output = captured.out
    assert f"Blockers: {blocker.value}" in output
    assert "Official daily selection ready: NO" in output
    assert "Official selection items: none" in output
    assert not captured.err
    assert calls["build"] == 1


@pytest.mark.parametrize("error", (SelectionDataError("selection"), StorageError("storage")))
def test_run_current_returns_one_for_local_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], error: Exception) -> None:
    _install(monkeypatch, tmp_path, error)
    assert main(["selection", "run-current"]) == 1
    captured = capsys.readouterr()
    assert "Daily-selection execution error:" in captured.err
    assert not captured.out
