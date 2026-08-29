"""Smoke tests for the project scaffold."""

import subprocess
import sys
from pathlib import Path

import stock_selector
from stock_selector.cli import build_parser


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
