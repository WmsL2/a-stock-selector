"""Command-line interface for A Stock Selector."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from pydantic import ValidationError

from stock_selector import __version__
from stock_selector.config.loader import ConfigurationError, load_settings
from stock_selector.config.paths import AppPaths

if TYPE_CHECKING:
    from stock_selector.providers.akshare_provider import AKShareProvider
    from stock_selector.providers.requests import (
        DailyBarsRequest,
        RealtimeQuotesRequest,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="A Stock Selector")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version", help="Show the A Stock Selector version.")
    config_parser = subparsers.add_parser("config", help="Inspect application configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("check", help="Validate the configured settings.")
    config_subparsers.add_parser("paths", help="Show project paths.")
    data_parser = subparsers.add_parser("data", help="Run one AKShare provider check.")
    data_subparsers = data_parser.add_subparsers(dest="data_command")
    data_subparsers.add_parser(
        "instruments-once", help="Fetch and summarize one instrument snapshot."
    )
    data_subparsers.add_parser(
        "realtime-once", help="Fetch and summarize one real-time snapshot."
    )
    daily_parser = data_subparsers.add_parser(
        "daily-once", help="Fetch and summarize unadjusted daily bars."
    )
    daily_parser.add_argument("symbol", help="Canonical symbol, for example 600519.SH.")
    daily_parser.add_argument("--start", required=True, help="Inclusive start date: YYYY-MM-DD.")
    daily_parser.add_argument("--end", required=True, help="Inclusive end date: YYYY-MM-DD.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "version":
        print(f"A Stock Selector {__version__}")
    elif arguments.command == "config":
        return _run_config_command(arguments.config_command)
    elif arguments.command == "data":
        return _run_data_command(arguments)
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


def _run_data_command(arguments: argparse.Namespace) -> int:
    """Run one explicit AKShare action, importing the provider only when needed."""
    from stock_selector.providers import (
        AKShareProvider,
        DailyBarsRequest,
        ProviderError,
        RealtimeQuotesRequest,
    )

    try:
        provider = AKShareProvider()
        if arguments.data_command == "instruments-once":
            _print_instrument_summary(provider)
        elif arguments.data_command == "realtime-once":
            _print_realtime_summary(provider, RealtimeQuotesRequest())
        elif arguments.data_command == "daily-once":
            request = DailyBarsRequest(
                symbol=arguments.symbol,
                start_date=date.fromisoformat(arguments.start),
                end_date=date.fromisoformat(arguments.end),
            )
            _print_daily_summary(provider, request)
        else:
            print("A data subcommand is required.", file=sys.stderr)
            return 2
    except (ProviderError, ValidationError, ValueError) as exc:
        print(f"Data provider error: {exc}", file=sys.stderr)
        return 1
    return 0


def _provider_label(provider: AKShareProvider) -> str:
    """Return a concise provider identity without implementation details."""
    return f"{provider.info.name} {provider.info.version or 'unknown'}"


def _print_instrument_summary(provider: AKShareProvider) -> None:
    """Print compact instrument counts without exposing the full listing."""
    instruments = provider.get_instruments()
    board_counts = Counter(instrument.board.value for instrument in instruments)
    print(f"Provider: {_provider_label(provider)}")
    print(f"Total instruments: {len(instruments)}")
    for board, label in (
        ("sh_main", "SH Main"),
        ("star", "STAR"),
        ("sz_main", "SZ Main"),
        ("chinext", "ChiNext"),
        ("bse", "BSE"),
    ):
        print(f"{label}: {board_counts[board]}")
    print("Validation: PASS")


def _print_realtime_summary(
    provider: AKShareProvider, request: RealtimeQuotesRequest
) -> None:
    """Print compact real-time metadata and at most three representative rows."""
    quotes = provider.get_realtime_quotes(request)
    print(f"Provider: {_provider_label(provider)}")
    print(f"Rows: {len(quotes)}")
    if quotes:
        print(f"Ingested at: {quotes[0].ingested_at.isoformat()}")
    print("Source timestamp: unavailable")
    for quote in quotes[:3]:
        print(f"{quote.symbol} price={quote.price} change_pct={quote.change_pct}")
    print("Validation: PASS")


def _print_daily_summary(provider: AKShareProvider, request: DailyBarsRequest) -> None:
    """Print compact daily-bar metadata and at most three representative rows."""
    bars = provider.get_daily_bars(request)
    print(f"Provider: {_provider_label(provider)}")
    print(f"Symbol: {request.symbol}")
    print(f"Rows: {len(bars)}")
    if bars:
        print(f"First date: {bars[0].trade_date}")
        print(f"Last date: {bars[-1].trade_date}")
    for bar in bars[:3]:
        print(f"{bar.trade_date} close={bar.close} volume={bar.volume}")
    print("Validation: PASS")
