"""Smoke tests for the project scaffold."""

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import stock_selector
import stock_selector.cli as cli_module
from stock_selector.cli import build_parser, main
from stock_selector.collection import CollectionError
from stock_selector.config import AppPaths, Settings
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.storage import LocalMarketRepository


def run_module(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the installed package as a Python module."""
    return subprocess.run(
        [sys.executable, "-m", "stock_selector", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_package_can_be_imported() -> None:
    """The package can be imported after editable installation."""
    assert stock_selector is not None


def test_package_version() -> None:
    """The package exposes its scaffold version."""
    assert stock_selector.__version__ == "0.1.0"


def test_cli_help() -> None:
    """The CLI help command exits successfully and identifies the project."""
    result = run_module("--help")
    assert result.returncode == 0
    assert "A Stock Selector" in result.stdout


def test_cli_version() -> None:
    """The CLI version command exits successfully and prints the version."""
    result = run_module("version")
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_cli_without_arguments() -> None:
    """The CLI exits successfully without arguments or a traceback."""
    result = run_module()
    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_storage_cli_parser_accepts_bounded_smoke_arguments() -> None:
    """Storage smoke requires one explicit symbol and inclusive date range."""
    arguments = build_parser().parse_args(
        [
            "storage",
            "smoke",
            "600519.SH",
            "--start",
            "2026-08-03",
            "--end",
            "2026-08-07",
        ]
    )
    assert arguments.storage_command == "smoke"
    assert arguments.symbol == "600519.SH"


def test_universe_cli_parser_accepts_offline_status_command() -> None:
    """Universe status remains an explicit read-only command."""
    arguments = build_parser().parse_args(["universe", "status"])
    assert arguments.universe_command == "status"


def test_quality_cli_parser_accepts_offline_status_command() -> None:
    """Quality status remains an explicit offline command."""
    arguments = build_parser().parse_args(["quality", "status"])
    assert arguments.quality_command == "status"


def test_daily_cli_parser_requires_explicit_symbols_and_range() -> None:
    """Daily collection has no implicit market-wide scope or range."""
    arguments = build_parser().parse_args(
        [
            "daily",
            "collect",
            "--symbols",
            "600519.SH",
            "--start",
            "2026-08-03",
            "--end",
            "2026-08-07",
        ]
    )
    assert arguments.daily_command == "collect"
    assert arguments.symbols == ["600519.SH"]


def test_realtime_cli_parser_makes_scope_and_persistence_explicit() -> None:
    all_market = build_parser().parse_args(["realtime", "capture", "--all-market"])
    explicit = build_parser().parse_args(
        ["realtime", "capture", "--symbol", "600519.SH", "--persist"]
    )
    status = build_parser().parse_args(["realtime", "status"])
    assert all_market.all_market is True
    assert all_market.persist is False
    assert explicit.symbols == ["600519.SH"]
    assert explicit.persist is True
    assert status.realtime_command == "status"


def test_realtime_cli_rejects_full_market_persistence_before_runtime_access(
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    assert main(["realtime", "capture", "--all-market", "--persist"]) == 2
    assert "--persist requires one or more --symbol" in capsys.readouterr().err


def test_risk_cli_parser_is_current_day_only() -> None:
    arguments = build_parser().parse_args(["risk", "collect-current"])
    assert arguments.risk_command == "collect-current"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["risk", "collect-current", "--as-of", "2026-09-02"])


def test_risk_cli_composes_structural_scope_and_collects_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current_at = datetime(2026, 9, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    captured: dict[str, object] = {}
    original_from_project_root = AppPaths.from_project_root

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            captured["initialized"] = True

    class FakeUniverseService:
        def __init__(self, repository: object, settings: object) -> None:
            captured["universe_dependencies"] = (repository, settings)

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["structural_as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "600519.SH"))

    class FakeCollector:
        def __init__(self, provider: object, repository: object) -> None:
            captured["collector_dependencies"] = (provider, repository)

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at.date(),
                requested_symbols=("000001.SZ", "600519.SH"),
                states_received=2,
                states_persisted=2,
                st_members=0,
                suspended_members=1,
                delisting_period_members=0,
                source="fake:risk",
                observed_at=current_at,
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: "provider")
    monkeypatch.setattr("stock_selector.collection.CurrentRiskStateCollector", FakeCollector)

    assert main(["risk", "collect-current"]) == 0
    assert captured["initialized"] is True
    assert captured["structural_as_of"] == current_at.date()
    assert captured["request"].symbols == ("000001.SZ", "600519.SH")
    assert captured["request"].as_of == current_at.date()
    assert "Risk coverage: 100%" in capsys.readouterr().out


def test_risk_cli_uses_cdr_filtered_members_from_real_structural_universe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_at = datetime(2026, 9, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    captured: dict[str, object] = {}
    original_from_project_root = AppPaths.from_project_root

    class SeededRepository(LocalMarketRepository):
        def initialize(self) -> None:
            super().initialize()
            self.save_instruments(
                (
                    Instrument(
                        symbol="688001.SH",
                        name="STAR A 股",
                        exchange=Exchange.SSE,
                        board=Board.STAR,
                        listing_date=date(2020, 1, 1),
                    ),
                    Instrument(
                        symbol="689009.SH",
                        name="STAR CDR",
                        exchange=Exchange.SSE,
                        board=Board.STAR,
                        listing_date=date(2020, 1, 1),
                    ),
                )
            )

    class FakeCollector:
        def __init__(self, _provider: object, _repository: object) -> None:
            return None

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at.date(),
                requested_symbols=("688001.SH",),
                states_received=1,
                states_persisted=1,
                st_members=0,
                suspended_members=0,
                delisting_period_members=0,
                source="fake:risk",
                observed_at=current_at,
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr(
        cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at)
    )
    monkeypatch.setattr(
        "stock_selector.storage.LocalMarketRepository", SeededRepository
    )
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: "provider")
    monkeypatch.setattr("stock_selector.collection.CurrentRiskStateCollector", FakeCollector)

    assert main(["risk", "collect-current"]) == 0
    assert captured["request"].symbols == ("688001.SH",)


def test_risk_cli_expected_failure_and_missing_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_from_project_root = AppPaths.from_project_root

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FailingUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, _as_of: date) -> SimpleNamespace:
            raise CollectionError("expected offline failure")

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FailingUniverseService)

    assert main(["risk", "collect-current"]) == 1
    assert "Risk collection error: expected offline failure" in capsys.readouterr().err
    assert main(["risk"]) == 2
    assert "risk subcommand is required" in capsys.readouterr().err


def test_config_check() -> None:
    """The CLI validates the default project configuration."""
    result = run_module("config", "check")
    assert result.returncode == 0
    assert "Configuration valid" in result.stdout


def test_config_paths() -> None:
    """The CLI exposes key project paths for engineering checks."""
    result = run_module("config", "paths")
    assert result.returncode == 0
    assert "Project root" in result.stdout


def test_localhost_development_scripts_are_explicit() -> None:
    """Development scripts must retain localhost-only bindings."""
    workspace_root = Path(__file__).resolve().parents[2]
    backend_script = (workspace_root / "scripts" / "start-backend.ps1").read_text(
        encoding="utf-8"
    )
    frontend_script = (workspace_root / "scripts" / "start-frontend.ps1").read_text(
        encoding="utf-8"
    )

    assert "--host 127.0.0.1" in backend_script
    assert "--host 127.0.0.1" in frontend_script
    assert (workspace_root / "scripts" / "test-all.ps1").is_file()
