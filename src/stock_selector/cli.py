"""Command-line interface for A Stock Selector."""

import argparse
import sys
from collections.abc import Sequence

from stock_selector import __version__
from stock_selector.config.loader import ConfigurationError, load_settings
from stock_selector.config.paths import AppPaths


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="A Stock Selector")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version", help="Show the A Stock Selector version.")
    config_parser = subparsers.add_parser("config", help="Inspect application configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("check", help="Validate the configured settings.")
    config_subparsers.add_parser("paths", help="Show project paths.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "version":
        print(f"A Stock Selector {__version__}")
    elif arguments.command == "config":
        return _run_config_command(arguments.config_command)
    else:
        parser.print_help()
    return 0


def _run_config_command(command: str | None) -> int:
    """Run a configuration inspection command without exposing full settings."""
    paths = AppPaths.from_project_root()
    if command == "paths":
        _print_paths(paths)
        return 0
    if command == "check":
        try:
            settings = load_settings(paths.config_dir)
        except ConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1
        enabled_weights = [
            group.weight
            for group in (
                settings.factors.quality,
                settings.factors.value,
                settings.factors.growth,
                settings.factors.momentum,
                settings.factors.low_volatility,
            )
            if group.enabled
        ]
        print("Configuration valid")
        print(f"Timezone: {settings.app.timezone}")
        print(f"Enabled factors: {len(enabled_weights)}")
        print(f"Factor weight sum: {sum(enabled_weights):.4f}")
        return 0
    print("A config subcommand is required: check or paths.", file=sys.stderr)
    return 2


def _print_paths(paths: AppPaths) -> None:
    """Print the project paths intended for local engineering checks."""
    print(f"Project root: {paths.project_root}")
    print(f"Config dir: {paths.config_dir}")
    print(f"Data dir: {paths.data_dir}")
    print(f"Logs dir: {paths.logs_dir}")
    print(f"Snapshots dir: {paths.snapshots_dir}")
