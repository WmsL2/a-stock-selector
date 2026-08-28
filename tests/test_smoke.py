"""Smoke tests for the project scaffold."""

import subprocess
import sys

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
