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
    storage_parser = subparsers.add_parser(
        "storage", help="Inspect or run explicit local storage operations."
    )
    storage_subparsers = storage_parser.add_subparsers(dest="storage_command")
    storage_subparsers.add_parser("status", help="Show offline selective storage coverage.")
    storage_smoke = storage_subparsers.add_parser(
        "smoke", help="Persist and validate one explicitly requested symbol."
    )
    storage_smoke.add_argument("symbol", help="Canonical symbol, for example 600519.SH.")
    storage_smoke.add_argument(
        "--start", required=True, help="Inclusive start date: YYYY-MM-DD."
    )
    storage_smoke.add_argument("--end", required=True, help="Inclusive end date: YYYY-MM-DD.")
    universe_parser = subparsers.add_parser(
        "universe", help="Inspect the offline point-in-time structural universe."
    )
    universe_subparsers = universe_parser.add_subparsers(dest="universe_command")
    universe_subparsers.add_parser(
        "status", help="Show current structural membership and deferred risk filters."
    )
    daily_parser = subparsers.add_parser(
        "daily", help="Inspect or explicitly collect bounded RAW daily prices."
    )
    daily_subparsers = daily_parser.add_subparsers(dest="daily_command")
    daily_subparsers.add_parser("status", help="Show offline RAW daily storage status.")
    daily_collect = daily_subparsers.add_parser(
        "collect", help="Collect explicitly named symbols over an inclusive finite date range."
    )
    daily_collect.add_argument("--symbols", nargs="+", required=True, help="Canonical symbols.")
    daily_collect.add_argument("--start", required=True, help="Inclusive start date: YYYY-MM-DD.")
    daily_collect.add_argument("--end", required=True, help="Inclusive end date: YYYY-MM-DD.")
    quality_parser = subparsers.add_parser(
        "quality", help="Inspect offline dated-risk coverage and realtime freshness."
    )
    quality_subparsers = quality_parser.add_subparsers(dest="quality_command")
    quality_subparsers.add_parser("status", help="Show conservative local quality status.")
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
    elif arguments.command == "storage":
        return _run_storage_command(arguments)
    elif arguments.command == "universe":
        return _run_universe_command(arguments.universe_command)
    elif arguments.command == "daily":
        return _run_daily_command(arguments)
    elif arguments.command == "quality":
        return _run_quality_command(arguments.quality_command)
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


def _run_storage_command(arguments: argparse.Namespace) -> int:
    """Run an offline status read or an explicitly bounded provider-to-storage smoke."""
    from stock_selector.providers import ProviderError
    from stock_selector.storage import LocalMarketRepository, StorageError

    try:
        repository = LocalMarketRepository(AppPaths.from_project_root())
        repository.initialize()
        if arguments.storage_command == "status":
            _print_storage_status(repository)
        elif arguments.storage_command == "smoke":
            _run_storage_smoke(repository, arguments)
        else:
            print("A storage subcommand is required: status or smoke.", file=sys.stderr)
            return 2
    except (ProviderError, StorageError, ValidationError, ValueError) as exc:
        print(f"Storage error: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_universe_command(command: str | None) -> int:
    """Print an offline structural universe without provider or risk-filter access."""
    from stock_selector.storage import LocalMarketRepository, StorageError
    from stock_selector.universe import CurrentUniverseService, UniverseError

    if command != "status":
        print("A universe subcommand is required: status.", file=sys.stderr)
        return 2
    try:
        paths = AppPaths.from_project_root()
        settings = load_settings(paths.config_dir)
        repository = LocalMarketRepository(paths)
        repository.initialize()
        snapshot = CurrentUniverseService(repository, settings).build_current()
        instruments = repository.load_instruments()
    except (ConfigurationError, StorageError, UniverseError) as exc:
        print(f"Universe error: {exc}", file=sys.stderr)
        return 1
    _print_universe_status(snapshot, instruments)
    return 0


def _run_quality_command(command: str | None) -> int:
    """Print offline quality status without provider calls or fake risk data."""
    from stock_selector.quality import CurrentQualityService, DataQualityError
    from stock_selector.risk import RiskError
    from stock_selector.storage import LocalMarketRepository, StorageError
    from stock_selector.universe import UniverseError

    if command != "status":
        print("A quality subcommand is required: status.", file=sys.stderr)
        return 2
    try:
        paths = AppPaths.from_project_root()
        settings = load_settings(paths.config_dir)
        repository = LocalMarketRepository(paths)
        repository.initialize()
        status = CurrentQualityService(repository, settings).build_current()
    except (
        ConfigurationError,
        DataQualityError,
        RiskError,
        StorageError,
        UniverseError,
    ) as exc:
        print(f"Quality error: {exc}", file=sys.stderr)
        return 1
    _print_quality_status(status)
    return 0


def _run_daily_command(arguments: argparse.Namespace) -> int:
    """Run explicit local status or bounded provider-to-storage daily collection."""
    from stock_selector.collection import (
        CollectionError,
        DailyCollectionRequest,
        DailyPriceCollector,
    )
    from stock_selector.providers import AKShareProvider
    from stock_selector.storage import LocalMarketRepository, StorageError

    try:
        repository = LocalMarketRepository(AppPaths.from_project_root())
        repository.initialize()
        if arguments.daily_command == "status":
            _print_daily_status(repository)
            return 0
        if arguments.daily_command == "collect":
            request = DailyCollectionRequest(
                symbols=tuple(arguments.symbols),
                start_date=date.fromisoformat(arguments.start),
                end_date=date.fromisoformat(arguments.end),
            )
            report = DailyPriceCollector(AKShareProvider(), repository).collect(request)
            _print_daily_collection_report(report)
            return 1 if report.failed_symbols else 0
    except (CollectionError, StorageError) as exc:
        print(f"Daily collection error: {exc}", file=sys.stderr)
        return 1
    except (ValidationError, ValueError) as exc:
        print(f"Daily collection usage error: {exc}", file=sys.stderr)
        return 2
    print("A daily subcommand is required: status or collect.", file=sys.stderr)
    return 2


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
        print(f"Market source: {quotes[0].source}")
    else:
        print("Market source: unavailable")
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


def _print_storage_status(repository) -> None:  # type: ignore[no-untyped-def]
    """Print offline coverage without calling a provider or claiming full detail coverage."""
    stats = repository.get_stats()
    print(f"Storage root: {repository.paths.processed_data_dir}")
    print(f"DuckDB: {repository.catalog_path}")
    print(f"Instrument universe: {stats.instrument_rows}")
    print(f"Daily stored symbols: {stats.daily_symbols}")
    print(f"Daily rows: {stats.daily_bar_rows}")
    print(
        "Earliest daily trade date: "
        f"{stats.earliest_daily_trade_date.isoformat() if stats.earliest_daily_trade_date else 'unavailable'}"
    )
    print(
        "Latest daily trade date: "
        f"{stats.latest_daily_trade_date.isoformat() if stats.latest_daily_trade_date else 'unavailable'}"
    )
    print(f"Realtime stored symbols: {stats.realtime_symbols}")
    print(f"Realtime snapshots: {stats.realtime_snapshots}")
    print(f"Realtime rows: {stats.realtime_quote_rows}")
    print(
        "Latest realtime: "
        f"{stats.latest_realtime_at.isoformat() if stats.latest_realtime_at else 'unavailable'}"
    )
    print(f"Risk state rows: {stats.risk_state_rows}")
    print(f"Risk state dates: {stats.risk_state_dates}")
    print(
        "Latest risk state date: "
        f"{stats.latest_risk_state_date.isoformat() if stats.latest_risk_state_date else 'unavailable'}"
    )
    print(f"Disk usage: {_format_bytes(stats.disk_usage_bytes)}")


def _print_daily_status(repository) -> None:  # type: ignore[no-untyped-def]
    """Print honest offline coverage for selective RAW daily persistence."""
    stats = repository.get_stats()
    print(f"Stored symbols: {stats.daily_symbols}")
    print(f"Stored rows: {stats.daily_bar_rows}")
    print(
        "Earliest trade date: "
        f"{stats.earliest_daily_trade_date.isoformat() if stats.earliest_daily_trade_date else 'unavailable'}"
    )
    print(
        "Latest trade date: "
        f"{stats.latest_daily_trade_date.isoformat() if stats.latest_daily_trade_date else 'unavailable'}"
    )
    print("Adjustment basis: raw")
    print("Corporate-action adjusted: NO")
    print("Full-market completeness verified: NO")
    print("Trading-calendar gap check applied: NO")


def _print_daily_collection_report(report) -> None:  # type: ignore[no-untyped-def]
    """Print compact per-symbol outcomes without exposing every stored bar."""
    print(f"Requested symbols: {len(report.requested_symbols)}")
    print(f"Date range: {report.start_date.isoformat()} to {report.end_date.isoformat()}")
    print(f"Adjustment: {report.adjustment.value}")
    print(f"Succeeded: {report.succeeded_symbols}")
    print(f"Empty: {report.empty_symbols}")
    print(f"Failed: {report.failed_symbols}")
    print(f"Rows received: {report.total_rows_received}")
    for result in report.results:
        if result.status.value == "success":
            print(f"{result.symbol} success rows={result.rows_persisted} source={result.source}")
        elif result.status.value == "empty":
            print(f"{result.symbol} empty")
        else:
            print(f"{result.symbol} failed {result.error_type}: {result.error_message}")


def _print_universe_status(snapshot, instruments) -> None:  # type: ignore[no-untyped-def]
    """Print one current structural snapshot without claiming risk filtering."""
    from stock_selector.models import Board
    from stock_selector.universe import UniverseExclusionReason

    included = set(snapshot.members)
    boards = Counter(
        instrument.board for instrument in instruments if instrument.symbol in included
    )
    exclusions = Counter(
        reason for decision in snapshot.decisions for reason in decision.reasons
    )
    print(f"As of: {snapshot.as_of.isoformat()}")
    print("Data scope: current_instrument_master")
    print(f"Input instruments: {snapshot.input_count}")
    print(f"Structural universe: {len(snapshot.members)}")
    print(f"Excluded: {snapshot.input_count - len(snapshot.members)}")
    print("By board:")
    for board, label in (
        (Board.SH_MAIN, "SH Main"),
        (Board.SZ_MAIN, "SZ Main"),
        (Board.CHINEXT, "ChiNext"),
        (Board.STAR, "STAR"),
        (Board.BSE, "BSE"),
    ):
        print(f"{label}: {boards[board]}")
    print("Structural exclusions:")
    for reason, label in (
        (UniverseExclusionReason.BOARD_DISABLED, "Board disabled"),
        (UniverseExclusionReason.NOT_YET_LISTED, "Not yet listed"),
        (UniverseExclusionReason.DELISTED, "Delisted"),
        (UniverseExclusionReason.MIN_LISTING_DAYS, "Min listing days"),
    ):
        print(f"{label}: {exclusions[reason]}")
    print("Risk filters applied: NO")
    print("Historical survivorship safe: NO")
    print("ST / suspension / delisting-period filters are not yet applied.")


def _print_quality_status(status) -> None:  # type: ignore[no-untyped-def]
    """Print uncertainty-preserving risk coverage and local ingestion freshness."""
    print(f"As of: {status.as_of.isoformat()}")
    print(f"Structural instruments: {status.structural_instruments}")
    print(f"Risk state records: {status.risk_state_records}")
    print(f"Risk complete instruments: {status.risk_complete_instruments}")
    print(f"Risk coverage: {status.risk_coverage_ratio:.1%}")
    print(f"Risk filter ready: {'YES' if status.risk_filter_ready else 'NO'}")
    print(
        "Risk eligible instruments: "
        f"{status.risk_eligible_instruments if status.risk_eligible_instruments is not None else 'unavailable'}"
    )
    print(
        "Latest realtime: "
        f"{status.latest_realtime_at.isoformat() if status.latest_realtime_at else 'unavailable'}"
    )
    print(
        "Realtime age: "
        f"{status.realtime_age_seconds:.1f}s"
        if status.realtime_age_seconds is not None
        else "Realtime age: unavailable"
    )
    print(f"Realtime freshness: {status.realtime_freshness.value}")
    print("Unknown risk fields are not treated as safe.")


def _run_storage_smoke(repository, arguments: argparse.Namespace) -> None:  # type: ignore[no-untyped-def]
    """Fetch and persist only one explicitly requested daily and realtime symbol."""
    from stock_selector.providers import (
        AKShareProvider,
        DailyBarsRequest,
        RealtimeQuotesRequest,
    )

    provider = AKShareProvider()
    instruments = provider.get_instruments()
    repository.save_instruments(instruments)
    daily_request = DailyBarsRequest(
        symbol=arguments.symbol,
        start_date=date.fromisoformat(arguments.start),
        end_date=date.fromisoformat(arguments.end),
    )
    daily_bars = provider.get_daily_bars(daily_request)
    repository.upsert_daily_bars(daily_bars)
    quotes = provider.get_realtime_quotes(
        RealtimeQuotesRequest(symbols=(daily_request.symbol,))
    )
    repository.save_realtime_snapshot(quotes)
    stored_instruments = repository.load_instruments()
    stored_daily = repository.load_daily_bars(daily_request.symbol)
    stored_quotes = repository.load_latest_realtime_snapshot()
    if (
        len(stored_instruments) != len(instruments)
        or not stored_daily
        or not stored_quotes
        or stored_daily != daily_bars
        or stored_quotes != quotes
    ):
        raise ValueError("storage smoke round-trip validation failed")
    stats = repository.get_stats()
    print(f"Instrument universe rows: {stats.instrument_rows}")
    print(f"Daily stored symbol: {daily_request.symbol}")
    print(f"Daily rows: {len(stored_daily)}")
    print(f"Daily source: {stored_daily[0].source}")
    print(f"Daily adjustment: {stored_daily[0].adjustment.value}")
    print(f"Realtime stored symbol: {stored_quotes[0].symbol}")
    print(f"Realtime rows: {len(stored_quotes)}")
    print(f"Realtime source: {stored_quotes[0].source}")
    print(f"Disk usage: {_format_bytes(stats.disk_usage_bytes)}")
    print("Round-trip validation: PASS")


def _format_bytes(value: int) -> str:
    """Format a nonnegative disk size with the smallest readable binary unit."""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")
