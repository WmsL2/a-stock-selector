"""Smoke tests for the project scaffold."""

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import stock_selector
import stock_selector.cli as cli_module
from stock_selector.cli import build_parser, main
from stock_selector.collection import (
    AdjustedReturnCollectionReport,
    AdjustedReturnCollectionRequest,
    AdjustedReturnCollectionStatus,
    AdjustedReturnSymbolResult,
    CollectionError,
)
from stock_selector.config import AppPaths, Settings
from stock_selector.config.loader import ConfigurationError
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe import UniverseError


def _patch_adjusted_cli(
    monkeypatch: pytest.MonkeyPatch, *, results: tuple[tuple[str, int, str | None], ...] = ()
) -> dict[str, object]:
    """Replace all CLI dependencies with offline recording fakes."""
    import stock_selector.collection as collection_module
    import stock_selector.providers as providers_module
    import stock_selector.storage as storage_module

    captured: dict[str, object] = {"provider": 0, "collector": 0, "requests": []}

    class FakeRepository:
        def __init__(self, paths: object) -> None:
            captured["repository"] = paths

        def initialize(self) -> None:
            captured["initialized"] = True

        def get_adjusted_return_stats(self) -> SimpleNamespace:
            return SimpleNamespace(symbols=0, rows=0, earliest_trade_date=None, latest_trade_date=None, latest_observed_at=None)

    class FakeProvider:
        def __init__(self) -> None:
            captured["provider"] = int(captured["provider"]) + 1

    class FakeCollector:
        def __init__(self, provider: object, repository: object) -> None:
            captured["collector"] = int(captured["collector"]) + 1

        def collect(self, request: AdjustedReturnCollectionRequest) -> AdjustedReturnCollectionReport:
            captured["requests"].append(request)  # type: ignore[union-attr]
            items = tuple(
                AdjustedReturnSymbolResult(
                    symbol=symbol,
                    status=(
                        AdjustedReturnCollectionStatus.FAILED if error else
                        AdjustedReturnCollectionStatus.SUCCESS if rows else
                        AdjustedReturnCollectionStatus.EMPTY
                    ),
                    rows_received=rows,
                    rows_persisted=rows,
                    error_type=error,
                    error_message="offline" if error else None,
                )
                for symbol, rows, error in results
            )
            return AdjustedReturnCollectionReport(
                requested_symbols=request.symbols, start_date=request.start_date, end_date=request.end_date,
                success_symbols=sum(item.status is AdjustedReturnCollectionStatus.SUCCESS for item in items),
                empty_symbols=sum(item.status is AdjustedReturnCollectionStatus.EMPTY for item in items),
                failed_symbols=sum(item.status is AdjustedReturnCollectionStatus.FAILED for item in items),
                rows_received=sum(item.rows_received for item in items),
                rows_persisted=sum(item.rows_persisted for item in items), results=items,
            )

    monkeypatch.setattr(storage_module, "LocalMarketRepository", FakeRepository)
    monkeypatch.setattr(providers_module, "AKShareProvider", FakeProvider)
    monkeypatch.setattr(collection_module, "AdjustedDailyReturnCollector", FakeCollector)
    return captured


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


def test_adjusted_daily_parser_and_valid_collection_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = build_parser().parse_args(["daily", "collect-adjusted-returns", "--symbols", "600519.SH", "000001.SZ", "--start", "2026-05-01", "--end", "2026-09-03"])
    assert parsed.daily_command == "collect-adjusted-returns"
    captured = _patch_adjusted_cli(monkeypatch, results=(("000001.SZ", 1, None), ("600519.SH", 0, None)))
    assert main(["daily", "collect-adjusted-returns", "--symbols", "600519.SH", "000001.SZ", "--start", "2026-05-01", "--end", "2026-09-03"]) == 0
    assert captured["provider"] == 1 and captured["collector"] == 1
    request = captured["requests"][0]  # type: ignore[index]
    assert request.symbols == ("000001.SZ", "600519.SH")
    assert (request.start_date, request.end_date) == (date(2026, 5, 1), date(2026, 9, 3))


@pytest.mark.parametrize(
    "symbols,start,end",
    [
        (["600519.SH"] * 2, "2026-05-01", "2026-09-03"),
        (["600519"], "2026-05-01", "2026-09-03"),
        (["600519.SH"], "2026-09-03", "2026-09-02"),
        ([f"{index:06d}.SZ" for index in range(21)], "2026-05-01", "2026-09-03"),
        (["600519.SH"], "2026-03-07", "2026-09-03"),
    ],
)
def test_adjusted_daily_invalid_requests_fail_before_provider(monkeypatch: pytest.MonkeyPatch, symbols, start: str, end: str) -> None:  # type: ignore[no-untyped-def]
    captured = _patch_adjusted_cli(monkeypatch)
    assert main(["daily", "collect-adjusted-returns", "--symbols", *symbols, "--start", start, "--end", end]) == 1
    assert captured["provider"] == 0


def test_adjusted_daily_20_symbols_and_180_inclusive_days_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    symbols = [f"{index:06d}.SZ" for index in range(20)]
    captured = _patch_adjusted_cli(monkeypatch, results=tuple((symbol, 0, None) for symbol in symbols))
    assert main(["daily", "collect-adjusted-returns", "--symbols", *symbols, "--start", "2026-03-08", "--end", "2026-09-03"]) == 0
    assert captured["provider"] == 1


def test_adjusted_daily_failed_report_returns_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _patch_adjusted_cli(monkeypatch, results=(("000001.SZ", 1, None), ("600519.SH", 0, "ProviderDataError")))
    assert main(["daily", "collect-adjusted-returns", "--symbols", "000001.SZ", "600519.SH", "--start", "2026-05-01", "--end", "2026-09-03"]) == 1
    assert "600519.SH failed ProviderDataError" in capsys.readouterr().out


def test_adjusted_status_is_offline_and_formats_empty_and_nonempty(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured = _patch_adjusted_cli(monkeypatch)
    assert build_parser().parse_args(["daily", "adjusted-status"]).daily_command == "adjusted-status"
    assert main(["daily", "adjusted-status"]) == 0
    output = capsys.readouterr().out
    assert "Stored symbols: 0" in output and "Latest observed at: unavailable" in output
    assert "Adjustment basis: hfq" in output and "RAW daily bars touched: NO" in output
    assert captured["provider"] == 0 and captured["collector"] == 0


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


def test_structural_batch_selection_reuses_exact_cursor_with_distinct_task_limits() -> None:
    members = ("000001.SZ", "000002.SZ", "000004.SZ", "600000.SH")
    assert cli_module._select_structural_batch(members, 1, None, maximum_limit=500) == (
        ("000001.SZ",),
        True,
    )
    assert cli_module._select_structural_batch(
        members, 2, "000002.SZ", maximum_limit=20
    ) == (
        ("000004.SZ", "600000.SH"),
        False,
    )
    assert cli_module._select_structural_batch(
        members, 500, "000004.SZ", maximum_limit=500
    ) == (
        ("600000.SH",),
        False,
    )
    assert cli_module._select_structural_batch(
        members, 1, "600000.SH", maximum_limit=20
    ) == ((), False)
    for limit in (0, -1, 501):
        with pytest.raises(ValueError, match="--limit"):
            cli_module._select_structural_batch(members, limit, None, maximum_limit=500)
    for limit in (0, -1, 21):
        with pytest.raises(ValueError, match="--limit"):
            cli_module._select_structural_batch(members, limit, None, maximum_limit=20)
    for cursor in ("600000", "600001.SH"):
        with pytest.raises(ValueError):
            cli_module._select_structural_batch(members, 1, cursor, maximum_limit=20)


def test_structural_core_cli_parser_is_bounded_and_current_only() -> None:
    arguments = build_parser().parse_args(
        [
            "fundamentals",
            "collect-structural-core",
            "--limit",
            "100",
            "--start-after",
            "000002.SZ",
        ]
    )
    assert arguments.limit == 100
    assert arguments.start_after == "000002.SZ"
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["fundamentals", "collect-structural-core", "--limit", "1", "--as-of", "2026-09-02"]
        )


def test_structural_valuation_cli_parser_is_tightly_bounded_and_current_only() -> None:
    arguments = build_parser().parse_args(
        [
            "fundamentals",
            "collect-structural-valuation",
            "--limit",
            "20",
            "--start-after",
            "000002.SZ",
        ]
    )
    assert arguments.limit == 20
    assert arguments.start_after == "000002.SZ"
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "fundamentals",
                "collect-structural-valuation",
                "--limit",
                "1",
                "--as-of",
                "2026-09-02",
            ]
        )


def test_structural_adjusted_return_cli_parser_is_tightly_bounded_and_current_only() -> None:
    arguments = build_parser().parse_args(
        ["daily", "collect-structural-adjusted-returns", "--limit", "20", "--start-after", "000002.SZ"]
    )
    assert arguments.limit == 20
    assert arguments.start_after == "000002.SZ"
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["daily", "collect-structural-adjusted-returns", "--limit", "1", "--symbols", "000001.SZ"]
        )


def test_structural_slow_inputs_cli_parser_is_tightly_bounded() -> None:
    arguments = build_parser().parse_args(
        ["refresh", "structural-slow-inputs", "--limit", "20", "--start-after", "000002.SZ"]
    )
    assert (arguments.limit, arguments.start_after) == (20, "000002.SZ")
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["refresh", "structural-slow-inputs", "--limit", "1", "--symbols", "000001.SZ"]
        )


def test_structural_slow_input_sweep_cli_parser_allows_only_cursor_and_limit() -> None:
    arguments = build_parser().parse_args(
        ["refresh", "structural-slow-inputs-sweep", "--limit", "100", "--start-after", "000002.SZ"]
    )
    assert (arguments.limit, arguments.start_after) == (100, "000002.SZ")
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["refresh", "structural-slow-inputs-sweep", "--limit", "1", "--symbols", "000001.SZ"]
        )


def test_structural_factor_input_status_parser_has_no_operational_arguments() -> None:
    arguments = build_parser().parse_args(["refresh", "structural-factor-input-status"])
    assert arguments.refresh_command == "structural-factor-input-status"
    for argument in ("--limit", "--start-after", "--symbols", "--as-of"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["refresh", "structural-factor-input-status", argument, "000001.SZ"]
            )
    assert build_parser().parse_args(
        ["refresh", "structural-slow-inputs", "--limit", "1"]
    ).refresh_command == "structural-slow-inputs"
    assert build_parser().parse_args(
        ["refresh", "structural-slow-inputs-sweep", "--limit", "1"]
    ).refresh_command == "structural-slow-inputs-sweep"


def test_structural_missing_slow_inputs_parser_is_bounded() -> None:
    arguments = build_parser().parse_args(
        ["refresh", "structural-missing-slow-inputs", "--limit", "100", "--start-after", "000002.SZ"]
    )
    assert (arguments.limit, arguments.start_after) == (100, "000002.SZ")
    for argument in ("--symbols", "--as-of", "--date", "--start", "--end"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["refresh", "structural-missing-slow-inputs", "--limit", "1", argument, "x"]
            )


def _patch_missing_refresh_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    missing_symbols: tuple[str, ...],
    selected_symbols: tuple[str, ...],
    missing_after_cursor: int | None = None,
    has_more: bool = False,
    failure: str | None = None,
    sweep_error: Exception | None = None,
) -> dict[str, object]:
    """Install offline recording fakes for the Task38 command graph."""
    current_at = datetime(2026, 9, 8, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    captured: dict[str, object] = {
        "now": 0,
        "universe": 0,
        "factor_read": 0,
        "audit": 0,
        "plan": 0,
        "provider": 0,
        "base": [],
        "wrappers": [],
        "task35": 0,
        "sweep": 0,
    }
    provider = object()

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

        def load_factor_input_symbols(self) -> tuple[str, ...]:
            captured["factor_read"] = int(captured["factor_read"]) + 1
            return ("000001.SZ",)

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["universe"] = int(captured["universe"]) + 1
            captured["universe_as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "600519.SH"))

    class Auditor:
        def audit(self, request: object) -> SimpleNamespace:
            captured["audit"] = int(captured["audit"]) + 1
            captured["coverage_request"] = request
            return SimpleNamespace(
                stored_factor_input_symbols=1,
                structural_factor_input_covered=3 - len(missing_symbols),
                structural_factor_input_missing=len(missing_symbols),
                missing_structural_symbols=missing_symbols,
            )

    class Planner:
        def plan(self, request: object) -> SimpleNamespace:
            captured["plan"] = int(captured["plan"]) + 1
            captured["plan_request"] = request
            return SimpleNamespace(
                as_of=current_at,
                structural_symbols=("000001.SZ", "000002.SZ", "600519.SH"),
                missing_after_cursor=(
                    len(selected_symbols)
                    if missing_after_cursor is None
                    else missing_after_cursor
                ),
                selected_symbols=selected_symbols,
                selected_count=len(selected_symbols),
                selected_first_symbol=selected_symbols[0] if selected_symbols else None,
                selected_last_symbol=selected_symbols[-1] if selected_symbols else None,
                has_more_missing_after_selection=has_more,
                next_start_after=selected_symbols[-1] if has_more and selected_symbols else None,
            )

    def base(name: str):
        class Base:
            def __init__(self, supplied_provider: object, _repository: object) -> None:
                cast = captured["base"]
                assert isinstance(cast, list)
                cast.append((name, supplied_provider))

        return Base

    class Core:
        def __init__(self, financial: object, industry: object, _repository: object) -> None:
            cast = captured["wrappers"]
            assert isinstance(cast, list)
            cast.append(("core", financial, industry))

    class Valuation:
        def __init__(self, collector: object, _repository: object) -> None:
            cast = captured["wrappers"]
            assert isinstance(cast, list)
            cast.append(("valuation", collector))

    class Adjusted:
        def __init__(self, collector: object, _repository: object) -> None:
            cast = captured["wrappers"]
            assert isinstance(cast, list)
            cast.append(("adjusted", collector))

    class Task35:
        def __init__(self, core: object, valuation: object, adjusted: object, _repository: object) -> None:
            captured["task35"] = int(captured["task35"]) + 1
            captured["task35_args"] = (core, valuation, adjusted)

    class Sweep:
        def __init__(self, task35: object) -> None:
            captured["sweep_task35"] = task35

        def collect(self, request: object) -> SimpleNamespace:
            captured["sweep"] = int(captured["sweep"]) + 1
            captured["sweep_request"] = request
            if sweep_error is not None:
                raise sweep_error
            failed = ("000002.SZ",) if failure else ()
            core = SimpleNamespace(
                financial_success=0 if failure == "financial" else 1,
                financial_empty=0,
                financial_failed=failed if failure == "financial" else (),
                industry_success=0 if failure == "industry" else 1,
                industry_empty=0,
                industry_failed=failed if failure == "industry" else (),
            )
            valuation = SimpleNamespace(
                success_symbols=0 if failure == "valuation" else 1,
                empty_symbols=0,
                failed_symbols=failed if failure == "valuation" else (),
            )
            adjusted = SimpleNamespace(
                success_symbols=0 if failure == "adjusted" else 1,
                empty_symbols=0,
                failed_symbols=failed if failure == "adjusted" else (),
                availability_as_of=current_at,
            )
            batch = SimpleNamespace(
                requested_symbols=selected_symbols,
                batch_first_symbol=selected_symbols[0],
                batch_last_symbol=selected_symbols[-1],
                core_report=core,
                valuation_report=valuation,
                adjusted_return_report=adjusted,
                factor_input_covered_after_run=len(selected_symbols),
            )
            return SimpleNamespace(
                batch_reports=(batch,), factor_input_covered_after_run=len(selected_symbols)
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(
        cli_module, "datetime", SimpleNamespace(now=lambda _timezone: _record_now(captured, current_at))
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.collection.StructuralFactorInputCoverageAuditor", Auditor)
    monkeypatch.setattr("stock_selector.collection.StructuralMissingRefreshPlanner", Planner)
    monkeypatch.setattr(
        "stock_selector.providers.AKShareProvider",
        lambda: _record_provider(captured, provider),
    )
    monkeypatch.setattr("stock_selector.collection.FinancialCollector", base("financial"))
    monkeypatch.setattr("stock_selector.collection.IndustryCollector", base("industry"))
    monkeypatch.setattr("stock_selector.collection.ValuationCollector", base("valuation"))
    monkeypatch.setattr("stock_selector.collection.AdjustedDailyReturnCollector", base("adjusted"))
    monkeypatch.setattr("stock_selector.collection.StructuralCoreFundamentalsCollector", Core)
    monkeypatch.setattr("stock_selector.collection.StructuralValuationCollector", Valuation)
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", Adjusted)
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputCollector", Task35)
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputSweepCollector", Sweep)
    captured["current_at"] = current_at
    return captured


def _record_now(captured: dict[str, object], current_at: datetime) -> datetime:
    captured["now"] = int(captured["now"]) + 1
    return current_at


def _record_provider(captured: dict[str, object], provider: object) -> object:
    captured["provider"] = int(captured["provider"]) + 1
    return provider


def test_structural_missing_slow_inputs_rejects_invalid_limits_before_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _patch_missing_refresh_dependencies(
        monkeypatch,
        tmp_path,
        missing_symbols=("000002.SZ",),
        selected_symbols=("000002.SZ",),
    )
    assert main(["refresh", "structural-missing-slow-inputs", "--limit", "0"]) == 1
    assert main(["refresh", "structural-missing-slow-inputs", "--limit", "101"]) == 1
    assert captured["provider"] == captured["sweep"] == 0


@pytest.mark.parametrize(
    ("missing_symbols", "start_after", "expected_message"),
    (
        ((), None, "Structural factor-input coverage already complete."),
        (("000001.SZ",), "600519.SH", "No missing structural factor-input members after start-after."),
    ),
)
def test_structural_missing_slow_inputs_stops_without_graph_when_no_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    missing_symbols: tuple[str, ...],
    start_after: str | None,
    expected_message: str,
) -> None:
    captured = _patch_missing_refresh_dependencies(
        monkeypatch, tmp_path, missing_symbols=missing_symbols, selected_symbols=()
    )
    arguments = ["refresh", "structural-missing-slow-inputs", "--limit", "2"]
    if start_after:
        arguments.extend(("--start-after", start_after))
    assert main(arguments) == 0
    assert captured["now"] == captured["universe"] == captured["factor_read"] == captured["audit"] == captured["plan"] == 1
    assert captured["provider"] == captured["task35"] == captured["sweep"] == 0
    output = capsys.readouterr().out
    assert expected_message in output
    if missing_symbols:
        assert "coverage already complete" not in output
        assert "Structural factor-input missing before refresh: 1" in output


@pytest.mark.parametrize(
    ("failure", "expected"),
    ((None, 0), ("financial", 1), ("industry", 1), ("valuation", 1), ("adjusted", 1)),
)
def test_structural_missing_slow_inputs_uses_one_preselection_and_shared_graph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: str | None,
    expected: int,
) -> None:
    captured = _patch_missing_refresh_dependencies(
        monkeypatch,
        tmp_path,
        missing_symbols=("000002.SZ", "600519.SH"),
        selected_symbols=("000002.SZ",),
        missing_after_cursor=2,
        has_more=True,
        failure=failure,
    )
    assert main(["refresh", "structural-missing-slow-inputs", "--limit", "1", "--start-after", "000001.SZ"]) == expected
    current_at = captured["current_at"]
    coverage_request = captured["coverage_request"]
    plan_request = captured["plan_request"]
    sweep_request = captured["sweep_request"]
    assert captured["now"] == captured["universe"] == captured["factor_read"] == captured["audit"] == captured["plan"] == captured["provider"] == captured["task35"] == captured["sweep"] == 1
    assert coverage_request.as_of == plan_request.as_of == sweep_request.as_of == current_at
    assert coverage_request.structural_symbols == plan_request.structural_symbols == ("000001.SZ", "000002.SZ", "600519.SH")
    assert coverage_request.factor_input_symbols == ("000001.SZ",)
    assert plan_request.missing_structural_symbols == ("000002.SZ", "600519.SH")
    assert (plan_request.limit, plan_request.start_after) == (1, "000001.SZ")
    assert sweep_request.symbols == ("000002.SZ",)
    assert sweep_request.has_more_structural_members is False
    base = captured["base"]
    assert isinstance(base, list)
    assert [item[0] for item in base] == ["financial", "industry", "valuation", "adjusted"]
    assert len({id(item[1]) for item in base}) == 1
    output = capsys.readouterr().out
    assert "Structural factor-input covered before refresh: 1" in output
    assert "Structural factor-input missing before refresh: 2" in output
    assert "Missing after start-after: 2" in output
    assert "Targeted requested: 1" in output
    assert "Targeted first: 000002.SZ" in output
    assert "Targeted last: 000002.SZ" in output
    assert "Batch requested: 1" in output
    assert "Batch first: 000002.SZ" in output
    assert "Batch last: 000002.SZ" in output
    assert "Targeted factor-input covered after run: 1 / 1" in output
    assert "Has more missing after selection: YES" in output
    assert "Next missing-scan start-after: 000002.SZ" in output


def test_structural_missing_slow_inputs_returns_one_for_sweep_storage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _patch_missing_refresh_dependencies(
        monkeypatch,
        tmp_path,
        missing_symbols=("000002.SZ",),
        selected_symbols=("000002.SZ",),
        sweep_error=StorageError("sweep storage"),
    )
    assert main(["refresh", "structural-missing-slow-inputs", "--limit", "1"]) == 1
    assert captured["sweep"] == 1


def test_task35_to_task37_parser_contracts_remain_unchanged() -> None:
    parser = build_parser()
    assert parser.parse_args(["refresh", "structural-slow-inputs", "--limit", "1"]).refresh_command == "structural-slow-inputs"
    assert parser.parse_args(["refresh", "structural-slow-inputs-sweep", "--limit", "1"]).refresh_command == "structural-slow-inputs-sweep"
    assert parser.parse_args(["refresh", "structural-factor-input-status"]).refresh_command == "structural-factor-input-status"


def test_selection_input_status_parser_has_no_operational_arguments() -> None:
    assert build_parser().parse_args(["selection", "input-status"]).selection_command == "input-status"
    for argument in ("--as-of", "--date", "--limit", "--start-after", "--symbols", "--refresh", "--persist"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["selection", "input-status", argument, "x"])


def test_selection_coverage_status_parser_has_no_operational_arguments() -> None:
    assert build_parser().parse_args(["selection", "coverage-status"]).selection_command == "coverage-status"
    for argument in ("--as-of", "--date", "--limit", "--start-after", "--symbols", "--symbol", "--refresh", "--persist", "--prepare", "--top-n"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["selection", "coverage-status", argument, "x"])


def test_selection_prepare_inputs_parser_is_tightly_bounded() -> None:
    arguments = build_parser().parse_args(
        ["selection", "prepare-inputs", "--limit", "100", "--start-after", "000002.SZ"]
    )
    assert (arguments.limit, arguments.start_after) == (100, "000002.SZ")
    for argument in ("--as-of", "--date", "--symbols", "--start", "--end", "--persist", "--all-market", "--top-n"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["selection", "prepare-inputs", "--limit", "1", argument, "x"])


def test_selection_run_current_parser_has_no_operational_arguments() -> None:
    assert build_parser().parse_args(["selection", "run-current"]).selection_command == "run-current"
    for argument in ("--as-of", "--date", "--limit", "--start-after", "--symbols", "--symbol", "--top-n", "--persist", "--refresh", "--prepare", "--all-market"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["selection", "run-current", argument, "x"])


def test_selection_without_subcommand_reports_all_available_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["selection"]) == 2
    assert "input-status, coverage-status, prepare-inputs, or run-current" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("complete", "eligible", "factor_symbols", "expected_ready", "expected_blocker", "structural_missing"),
    (
        (("000001.SZ",), (), ("000001.SZ",), "NO", "risk_state_coverage_incomplete", 1),
        (("000001.SZ", "000002.SZ"), (), (), "NO", "no_risk_eligible_members", 2),
        (("000001.SZ", "000002.SZ"), ("000001.SZ",), (), "NO", "eligible_factor_input_coverage_incomplete", 2),
        (("000001.SZ", "000002.SZ"), ("000001.SZ",), ("000001.SZ",), "YES", "none", 1),
        (("000001.SZ", "000002.SZ"), ("000001.SZ", "000002.SZ"), ("000001.SZ", "000002.SZ"), "YES", "none", 0),
    ),
)
def test_selection_input_status_uses_one_local_snapshot_and_reports_readiness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    complete: tuple[str, ...],
    eligible: tuple[str, ...],
    factor_symbols: tuple[str, ...],
    expected_ready: str,
    expected_blocker: str,
    structural_missing: int,
) -> None:
    current_at = datetime(2026, 9, 8, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    calls: dict[str, object] = {"now": 0, "build": 0, "risk_read": 0, "evaluate": 0, "factor_read": 0, "coverage": 0, "readiness": 0}

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

        def load_risk_states(self, as_of: date, symbols: tuple[str, ...]) -> tuple[SimpleNamespace, ...]:
            calls["risk_read"] = int(calls["risk_read"]) + 1
            calls["risk_request"] = (as_of, symbols)
            return tuple(SimpleNamespace(symbol=symbol) for symbol in symbols)

        def load_factor_input_symbols(self) -> tuple[str, ...]:
            calls["factor_read"] = int(calls["factor_read"]) + 1
            return factor_symbols

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, as_of: date) -> SimpleNamespace:
            calls["build"] = int(calls["build"]) + 1
            calls["build_as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "000002.SZ"))

    class Evaluator:
        def evaluate(self, structural: object, states: tuple[SimpleNamespace, ...], _config: object) -> SimpleNamespace:
            calls["evaluate"] = int(calls["evaluate"]) + 1
            return SimpleNamespace(
                eligible_members=eligible,
                decisions=tuple(SimpleNamespace(symbol=symbol, risk_complete=symbol in complete) for symbol in structural.members),
            )

    from stock_selector.collection import (
        StructuralFactorInputCoverageAuditor as CoverageAuditor,
    )
    from stock_selector.selection import (
        DailySelectionInputReadinessAuditor as ReadinessAuditor,
    )

    class Coverage(CoverageAuditor):
        def audit(self, request: object):  # type: ignore[no-untyped-def]
            calls["coverage"] = int(calls["coverage"]) + 1
            calls["coverage_request"] = request
            return super().audit(request)

    class Readiness(ReadinessAuditor):
        def audit(self, request: object):  # type: ignore[no-untyped-def]
            calls["readiness"] = int(calls["readiness"]) + 1
            calls["readiness_request"] = request
            return super().audit(request)

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _timezone: _record_now(calls, current_at)))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.risk.evaluator.RiskEligibilityEvaluator", Evaluator)
    monkeypatch.setattr("stock_selector.collection.StructuralFactorInputCoverageAuditor", Coverage)
    monkeypatch.setattr("stock_selector.selection.DailySelectionInputReadinessAuditor", Readiness)
    for target in (
        "stock_selector.providers.AKShareProvider",
        "stock_selector.collection.CurrentRiskStateCollector",
        "stock_selector.collection.StructuralSlowInputCollector",
        "stock_selector.collection.StructuralSlowInputSweepCollector",
        "stock_selector.collection.StructuralMissingRefreshPlanner",
        "stock_selector.selection.DailySelectionService",
        "stock_selector.factors.FiveFactorEngine",
        "stock_selector.scoring.BaseScoreEngine",
        "stock_selector.explanation.ExplanationEngine",
    ):
        monkeypatch.setattr(
            target,
            lambda target=target: (_ for _ in ()).throw(AssertionError(target)),
        )
    assert main(["selection", "input-status"]) == 0
    assert calls["now"] == calls["build"] == calls["risk_read"] == calls["evaluate"] == calls["factor_read"] == calls["coverage"] == calls["readiness"] == 1
    assert calls["build_as_of"] == current_at.date()
    assert calls["risk_request"] == (current_at.date(), ("000001.SZ", "000002.SZ"))
    request = calls["readiness_request"]
    coverage_request = calls["coverage_request"]
    assert coverage_request.as_of == current_at
    assert coverage_request.structural_symbols == ("000001.SZ", "000002.SZ")
    assert coverage_request.factor_input_symbols == factor_symbols
    assert request.as_of == current_at
    assert request.structural_symbols == ("000001.SZ", "000002.SZ")
    assert request.risk_record_symbols == ("000001.SZ", "000002.SZ")
    assert request.risk_complete_symbols == complete
    assert request.risk_eligible_symbols == eligible
    assert request.factor_input_symbols == factor_symbols
    output = capsys.readouterr().out
    assert f"Daily-selection upstream inputs ready: {expected_ready}" in output
    assert f"Blockers: {expected_blocker}" in output
    assert f"Structural factor-input missing: {structural_missing}" in output
    if expected_ready == "YES" and structural_missing == 1:
        assert "Structural factor-input covered: 1" in output
        assert "Eligible factor-input covered: 1" in output
        assert "Eligible factor-input missing: 0" in output
    assert "does not run factors/BaseScore and does not guarantee returned selection items" in output


def test_selection_input_status_returns_one_for_storage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_paths = AppPaths.from_project_root

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

        def load_risk_states(self, _as_of: date, _symbols: tuple[str, ...]) -> tuple[object, ...]:
            raise StorageError("risk read")

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ",))

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _timezone: datetime(2026, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai"))))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr(
        "stock_selector.providers.AKShareProvider",
        lambda: (_ for _ in ()).throw(AssertionError("provider must not be constructed")),
    )
    assert main(["selection", "input-status"]) == 1


@pytest.mark.parametrize(
    ("factor_symbols", "covered", "missing", "nonstructural", "coverage"),
    (
        (("000002.SZ", "600519.SH"), 1, 1, 1, "50.00%"),
        ((), 0, 2, 0, "0.00%"),
        (("000001.SZ", "000002.SZ"), 2, 0, 0, "100.00%"),
    ),
)
def test_structural_factor_input_status_uses_one_snapshot_read_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    factor_symbols: tuple[str, ...],
    covered: int,
    missing: int,
    nonstructural: int,
    coverage: str,
) -> None:
    current_at = datetime(2026, 9, 7, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    captured: dict[str, object] = {"now": 0, "universe": 0, "factor_read": 0, "audit": 0}

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

        def load_factor_input_symbols(self) -> tuple[str, ...]:
            captured["factor_read"] += 1
            return factor_symbols

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["universe"] += 1
            captured["universe_as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "000002.SZ"))

    class Auditor:
        def audit(self, request: object) -> SimpleNamespace:
            captured["audit"] += 1
            captured["request"] = request
            covered_symbols = tuple(
                symbol for symbol in request.structural_symbols if symbol in factor_symbols
            )
            missing_symbols = tuple(
                symbol for symbol in request.structural_symbols if symbol not in factor_symbols
            )
            assert len(covered_symbols) == covered
            assert len(missing_symbols) == missing
            return SimpleNamespace(
                as_of=current_at,
                structural_members=2,
                stored_factor_input_symbols=len(factor_symbols),
                structural_factor_input_covered=covered,
                structural_factor_input_missing=missing,
                nonstructural_stored_factor_input_symbols=nonstructural,
                first_missing_symbol=missing_symbols[0] if missing_symbols else None,
                last_missing_symbol=missing_symbols[-1] if missing_symbols else None,
            )

    def fake_now(_timezone: object) -> datetime:
        captured["now"] += 1
        return current_at

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path)
    )
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=fake_now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr(
        "stock_selector.providers.AKShareProvider",
        lambda: (_ for _ in ()).throw(AssertionError("provider must not be constructed")),
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralFactorInputCoverageAuditor", Auditor
    )

    assert main(["refresh", "structural-factor-input-status"]) == 0
    assert captured["now"] == captured["universe"] == captured["factor_read"] == captured["audit"] == 1
    assert captured["universe_as_of"] == current_at.date()
    assert captured["request"].structural_symbols == ("000001.SZ", "000002.SZ")
    assert captured["request"].factor_input_symbols == factor_symbols
    output = capsys.readouterr().out
    assert f"Structural factor-input covered: {covered}" in output
    assert f"Structural factor-input missing: {missing}" in output
    assert f"Structural coverage: {coverage}" in output
    assert f"Non-structural stored factor-input symbols: {nonstructural}" in output
    missing_symbols = tuple(
        symbol
        for symbol in captured["request"].structural_symbols
        if symbol not in factor_symbols
    )
    expected_marker = "complete" if not missing else missing_symbols[0]
    assert f"First missing symbol: {expected_marker}" in output
    assert f"Last missing symbol: {expected_marker if missing == 1 else (missing_symbols[-1] if missing else 'complete')}" in output


@pytest.mark.parametrize("failure", ("config", "storage", "universe", "contract"))
def test_structural_factor_input_status_returns_one_for_operational_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    original_paths = AppPaths.from_project_root

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            if failure == "storage":
                raise StorageError("storage")

        def load_factor_input_symbols(self) -> tuple[str, ...]:
            return ()

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, _as_of: date) -> SimpleNamespace:
            if failure == "universe":
                raise UniverseError("universe")
            return SimpleNamespace(members=("000001.SZ",))

    class Auditor:
        def audit(self, _request: object) -> None:
            raise ValueError("contract")

    monkeypatch.setattr(
        cli_module,
        "load_settings",
        (lambda _path: (_ for _ in ()).throw(ConfigurationError("config")))
        if failure == "config" else lambda _path: Settings(),
    )
    monkeypatch.setattr(
        cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path)
    )
    monkeypatch.setattr(
        cli_module,
        "datetime",
        SimpleNamespace(now=lambda _tz: datetime(2026, 9, 7, tzinfo=ZoneInfo("Asia/Shanghai"))),
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralFactorInputCoverageAuditor", Auditor
    )
    assert main(["refresh", "structural-factor-input-status"]) == 1


def test_structural_slow_input_sweep_stops_before_provider_for_invalid_or_empty_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original_paths = AppPaths.from_project_root
    provider_calls = 0
    sweep_calls = 0

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "000003.SZ"))

    def provider() -> object:
        nonlocal provider_calls
        provider_calls += 1
        return object()

    class SweepCollector:
        def __init__(self, *_: object) -> None:
            pass

        def collect(self, _request: object) -> None:
            nonlocal sweep_calls
            sweep_calls += 1

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path)
    )
    monkeypatch.setattr(
        cli_module,
        "datetime",
        SimpleNamespace(now=lambda _tz: datetime(2026, 9, 7, tzinfo=ZoneInfo("Asia/Shanghai"))),
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralSlowInputSweepCollector", SweepCollector
    )

    assert main(["refresh", "structural-slow-inputs-sweep", "--limit", "0"]) == 1
    assert main(["refresh", "structural-slow-inputs-sweep", "--limit", "101"]) == 1
    assert main(
        ["refresh", "structural-slow-inputs-sweep", "--limit", "1", "--start-after", "600519.SH"]
    ) == 1
    assert provider_calls == sweep_calls == 0
    assert main(
        ["refresh", "structural-slow-inputs-sweep", "--limit", "1", "--start-after", "000003.SZ"]
    ) == 0
    assert provider_calls == sweep_calls == 0
    assert "No remaining structural members." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("failure", "expected"),
    ((None, 0), ("financial", 1), ("industry", 1), ("valuation", 1), ("adjusted", 1)),
)
def test_structural_slow_input_sweep_cli_composes_one_shared_graph_and_reports_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: str | None,
    expected: int,
) -> None:
    current_at = datetime(2026, 9, 7, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    sentinel = object()
    captured: dict[str, object] = {"base": [], "constructors": [], "now": 0}

    class Repository:
        def __init__(self, _paths: object) -> None:
            pass

        def initialize(self) -> None:
            pass

    class Universe:
        def __init__(self, *_: object) -> None:
            pass

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["universe_as_of"] = as_of
            return SimpleNamespace(
                members=("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ")
            )

    def base_factory(name: str):
        def factory(provider: object, _repository: object) -> SimpleNamespace:
            captured["base"].append((name, provider))
            return SimpleNamespace(name=name)

        return factory

    def structural_factory(name: str):
        def factory(*dependencies: object) -> SimpleNamespace:
            captured["constructors"].append((name, dependencies))
            return SimpleNamespace(name=name)

        return factory

    class SweepCollector:
        def __init__(self, task35: object) -> None:
            captured["constructors"].append(("sweep", (task35,)))

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            failed = 1 if failure else 0
            core = SimpleNamespace(
                financial_success=len(request.symbols) - (failure == "financial"),
                financial_empty=0,
                financial_failed=failed if failure == "financial" else 0,
                industry_success=len(request.symbols) - (failure == "industry"),
                industry_empty=0,
                industry_failed=failed if failure == "industry" else 0,
            )
            valuation = SimpleNamespace(
                success_symbols=len(request.symbols) - (failure == "valuation"),
                empty_symbols=0,
                failed_symbols=failed if failure == "valuation" else 0,
            )
            adjusted = SimpleNamespace(
                success_symbols=len(request.symbols) - (failure == "adjusted"),
                empty_symbols=0,
                failed_symbols=failed if failure == "adjusted" else 0,
                availability_as_of=current_at,
            )
            batch = SimpleNamespace(
                requested_symbols=request.symbols,
                batch_first_symbol=request.symbols[0],
                batch_last_symbol=request.symbols[-1],
                core_report=core,
                valuation_report=valuation,
                adjusted_return_report=adjusted,
                factor_input_covered_after_run=len(request.symbols),
            )
            return SimpleNamespace(
                as_of=current_at,
                requested_symbols=request.symbols,
                batch_reports=(batch,),
                factor_input_covered_after_run=len(request.symbols),
                batch_first_symbol=request.symbols[0],
                batch_last_symbol=request.symbols[-1],
                has_more_structural_members=True,
                next_start_after=request.symbols[-1],
            )

    def fake_now(_timezone: object) -> datetime:
        captured["now"] += 1
        return current_at

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path)
    )
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=fake_now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: sentinel)
    monkeypatch.setattr("stock_selector.collection.FinancialCollector", base_factory("financial"))
    monkeypatch.setattr("stock_selector.collection.IndustryCollector", base_factory("industry"))
    monkeypatch.setattr("stock_selector.collection.ValuationCollector", base_factory("valuation"))
    monkeypatch.setattr(
        "stock_selector.collection.AdjustedDailyReturnCollector", base_factory("adjusted")
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralCoreFundamentalsCollector",
        structural_factory("core"),
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralValuationCollector",
        structural_factory("valuation"),
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralAdjustedReturnCollector",
        structural_factory("adjusted"),
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralSlowInputCollector",
        structural_factory("slow_inputs"),
    )
    monkeypatch.setattr(
        "stock_selector.collection.StructuralSlowInputSweepCollector", SweepCollector
    )

    assert main(["refresh", "structural-slow-inputs-sweep", "--limit", "3"]) == expected
    assert captured["now"] == 1
    assert captured["universe_as_of"] == current_at.date()
    assert captured["request"].symbols == ("000001.SZ", "000002.SZ", "000003.SZ")
    assert captured["request"].has_more_structural_members is True
    assert [name for name, _ in captured["base"]] == [
        "financial",
        "industry",
        "valuation",
        "adjusted",
    ]
    assert all(provider is sentinel for _, provider in captured["base"])
    assert [name for name, _ in captured["constructors"]] == [
        "core",
        "valuation",
        "adjusted",
        "slow_inputs",
        "sweep",
    ]
    output = capsys.readouterr().out
    assert "Batch 1/1" in output
    assert "Adjusted availability as of:" in output
    assert "Factor input covered after batch: 3" in output


def test_structural_slow_inputs_cli_composes_one_shared_provider_and_partial_cursor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current_at = datetime(2026, 9, 6, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    captured: dict[str, object] = {"base": [], "now": 0}
    sentinel = object()

    class Repository:
        def __init__(self, _paths: object) -> None: pass
        def initialize(self) -> None: pass

    class Universe:
        def __init__(self, *_: object) -> None: pass
        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["universe_as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "000003.SZ"))

    def base_factory(name: str):
        def factory(provider: object, _repository: object) -> SimpleNamespace:
            captured["base"].append((name, provider))
            return SimpleNamespace(name=name)
        return factory

    class SlowCollector:
        def __init__(self, *_dependencies: object) -> None: pass
        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            statuses = SimpleNamespace(value="success")
            core_items = tuple(SimpleNamespace(symbol=s, financial_status=statuses, industry_status=statuses) for s in request.symbols)
            valuation_items = tuple(SimpleNamespace(status=statuses) for _ in request.symbols)
            adjusted_items = tuple(SimpleNamespace(status=statuses) for _ in request.symbols)
            core = SimpleNamespace(financial_success=2, financial_empty=0, financial_failed=0, financial_rows_persisted=2, industry_success=2, industry_empty=0, industry_failed=0, industry_rows_persisted=2, results=core_items)
            valuation = SimpleNamespace(success_symbols=2, empty_symbols=0, failed_symbols=0, rows_persisted=2, valuation_available_after_run=2, results=valuation_items)
            adjusted = SimpleNamespace(success_symbols=2, empty_symbols=0, failed_symbols=0, rows_received=2, rows_persisted=2, availability_as_of=current_at, adjusted_return_available_after_run=2, results=adjusted_items)
            return SimpleNamespace(as_of=current_at, requested_symbols=request.symbols, core_report=core, valuation_report=valuation, adjusted_return_report=adjusted, factor_input_covered_after_run=2, batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1], has_more_structural_members=request.has_more_structural_members, next_start_after=request.symbols[-1])

    def fake_now(_tz: object) -> datetime:
        captured["now"] += 1
        return current_at

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=fake_now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: sentinel)
    monkeypatch.setattr("stock_selector.collection.FinancialCollector", base_factory("financial"))
    monkeypatch.setattr("stock_selector.collection.IndustryCollector", base_factory("industry"))
    monkeypatch.setattr("stock_selector.collection.ValuationCollector", base_factory("valuation"))
    monkeypatch.setattr("stock_selector.collection.AdjustedDailyReturnCollector", base_factory("adjusted"))
    monkeypatch.setattr("stock_selector.collection.StructuralCoreFundamentalsCollector", lambda *_: SimpleNamespace())
    monkeypatch.setattr("stock_selector.collection.StructuralValuationCollector", lambda *_: SimpleNamespace())
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", lambda *_: SimpleNamespace())
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputCollector", SlowCollector)

    assert main(["refresh", "structural-slow-inputs", "--limit", "2"]) == 0
    assert captured["now"] == 1 and captured["universe_as_of"] == current_at.date()
    assert captured["request"].symbols == ("000001.SZ", "000002.SZ")
    assert captured["request"].has_more_structural_members is True
    assert [name for name, _ in captured["base"]] == ["financial", "industry", "valuation", "adjusted"]
    assert all(provider is sentinel for _, provider in captured["base"])
    output = capsys.readouterr().out
    assert "Has more: YES" in output and "Next start-after: 000002.SZ" in output
    assert "financial=success industry=success valuation=success adjusted=success" in output


def test_structural_slow_inputs_cli_stops_before_provider_for_invalid_or_empty_batches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original_paths = AppPaths.from_project_root
    constructions = 0
    collector_calls = 0
    class Repository:
        def __init__(self, _paths: object) -> None: pass
        def initialize(self) -> None: pass
    class Universe:
        def __init__(self, *_: object) -> None: pass
        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "000003.SZ"))
    def provider() -> object:
        nonlocal constructions
        constructions += 1
        return object()
    class Collector:
        def __init__(self, *_: object) -> None: pass
        def collect(self, _request: object) -> None:
            nonlocal collector_calls
            collector_calls += 1
    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: datetime(2026, 9, 6, tzinfo=ZoneInfo("Asia/Shanghai"))))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider)
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputCollector", Collector)
    assert main(["refresh", "structural-slow-inputs", "--limit", "0"]) == 1
    assert main(["refresh", "structural-slow-inputs", "--limit", "21"]) == 1
    assert main(["refresh", "structural-slow-inputs", "--limit", "2", "--start-after", "600519.SH"]) == 1
    assert constructions == collector_calls == 0
    assert main(["refresh", "structural-slow-inputs", "--limit", "2", "--start-after", "000003.SZ"]) == 0
    assert constructions == collector_calls == 0
    assert "No remaining structural members." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("financial_failed", "industry_failed", "valuation_failed", "adjusted_failed", "expected"),
    ((1, 0, 0, 0, 1), (0, 1, 0, 0, 1), (0, 0, 1, 0, 1), (0, 0, 0, 1, 1), (0, 0, 0, 0, 0)),
)
def test_structural_slow_inputs_cli_exit_reflects_each_nested_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, financial_failed: int, industry_failed: int,
    valuation_failed: int, adjusted_failed: int, expected: int,
) -> None:
    current_at = datetime(2026, 9, 6, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_paths = AppPaths.from_project_root
    class Repository:
        def __init__(self, _paths: object) -> None: pass
        def initialize(self) -> None: pass
    class Universe:
        def __init__(self, *_: object) -> None: pass
        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ",))
    class Collector:
        def __init__(self, *_: object) -> None: pass
        def collect(self, request: object) -> SimpleNamespace:
            status = SimpleNamespace(value="empty")
            core = SimpleNamespace(financial_success=0, financial_empty=1-financial_failed, financial_failed=financial_failed, financial_rows_persisted=0, industry_success=0, industry_empty=1-industry_failed, industry_failed=industry_failed, industry_rows_persisted=0, results=(SimpleNamespace(symbol="000001.SZ", financial_status=status, industry_status=status),))
            valuation = SimpleNamespace(success_symbols=0, empty_symbols=1-valuation_failed, failed_symbols=valuation_failed, rows_persisted=0, valuation_available_after_run=0, results=(SimpleNamespace(status=status),))
            adjusted = SimpleNamespace(success_symbols=0, empty_symbols=1-adjusted_failed, failed_symbols=adjusted_failed, rows_received=0, rows_persisted=0, availability_as_of=current_at, adjusted_return_available_after_run=0, results=(SimpleNamespace(status=status),))
            return SimpleNamespace(as_of=current_at, requested_symbols=request.symbols, core_report=core, valuation_report=valuation, adjusted_return_report=adjusted, factor_input_covered_after_run=0, batch_first_symbol="000001.SZ", batch_last_symbol="000001.SZ", has_more_structural_members=False, next_start_after=None)
    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: object())
    monkeypatch.setattr("stock_selector.collection.FinancialCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.IndustryCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.ValuationCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.AdjustedDailyReturnCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.StructuralCoreFundamentalsCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.StructuralValuationCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", lambda *_: object())
    monkeypatch.setattr("stock_selector.collection.StructuralSlowInputCollector", Collector)
    assert main(["refresh", "structural-slow-inputs", "--limit", "1"]) == expected


def test_structural_adjusted_return_cli_uses_one_current_timestamp_and_current_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current_at = datetime(2026, 9, 2, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    captured: dict[str, object] = {}
    now_calls = 0
    original_from_project_root = AppPaths.from_project_root

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["as_of"] = as_of
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "600519.SH"))

    class FakeStructuralCollector:
        def __init__(self, *_dependencies: object) -> None:
            return None

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at, start_date=current_at.date() - timedelta(days=179), end_date=current_at.date(),
                availability_as_of=current_at,
                requested_symbols=("000002.SZ", "600519.SH"), success_symbols=1, empty_symbols=1,
                failed_symbols=0, rows_received=1, rows_persisted=1, adjusted_return_available_after_run=1,
                results=(), batch_first_symbol="000002.SZ", batch_last_symbol="600519.SH",
                has_more_structural_members=False, next_start_after=None,
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_from_project_root(tmp_path))
    def fake_now(_tz: object) -> datetime:
        nonlocal now_calls
        now_calls += 1
        return current_at

    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=fake_now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: "provider")
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", FakeStructuralCollector)

    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2", "--start-after", "000001.SZ"]) == 0
    request = captured["request"]
    assert captured["as_of"] == current_at.date()
    assert request.symbols == ("000002.SZ", "600519.SH")
    assert request.as_of is current_at
    assert now_calls == 1
    assert request.end_date == current_at.date()
    assert request.start_date == request.end_date - timedelta(days=179)
    assert (request.end_date - request.start_date).days + 1 == 180
    output = capsys.readouterr().out
    assert f"Availability as of: {current_at.isoformat()}" in output
    assert "Next start-after: complete" in output


def test_structural_adjusted_return_cli_validates_before_provider_and_exit_statuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current_at = datetime(2026, 9, 2, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    original_from_project_root = AppPaths.from_project_root
    provider_constructions = 0
    collector_calls = 0
    failed_symbols = 0

    def provider_factory() -> str:
        nonlocal provider_constructions
        provider_constructions += 1
        return "provider"

    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "0"]) == 1
    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "21"]) == 1
    assert provider_constructions == 0

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "600519.SH"))

    class FakeStructuralCollector:
        def __init__(self, *_dependencies: object) -> None:
            return None

        def collect(self, request: object) -> SimpleNamespace:
            nonlocal collector_calls
            collector_calls += 1
            return SimpleNamespace(
                as_of=current_at, start_date=current_at.date() - timedelta(days=179), end_date=current_at.date(),
                availability_as_of=current_at,
                requested_symbols=request.symbols, success_symbols=1, empty_symbols=1 - failed_symbols,
                failed_symbols=failed_symbols, rows_received=1, rows_persisted=1,
                adjusted_return_available_after_run=1, results=(), batch_first_symbol=request.symbols[0],
                batch_last_symbol=request.symbols[-1], has_more_structural_members=False, next_start_after=None,
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_from_project_root(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", FakeStructuralCollector)

    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2", "--start-after", "000003.SZ"]) == 1
    assert provider_constructions == 0
    assert collector_calls == 0

    failed_symbols = 1
    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2"]) == 1
    failed_symbols = 0
    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2"]) == 0
    assert provider_constructions == 2
    assert collector_calls == 2
    assert "Structural adjusted-return collection error" in capsys.readouterr().err


def test_structural_adjusted_return_cli_reports_next_cursor_for_partial_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current_at = datetime(2026, 9, 2, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    captured: dict[str, object] = {}
    original_from_project_root = AppPaths.from_project_root

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("000001.SZ", "000002.SZ", "000003.SZ"))

    class FakeStructuralCollector:
        def __init__(self, *_dependencies: object) -> None:
            return None

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at, start_date=request.start_date, end_date=request.end_date,
                availability_as_of=current_at,
                requested_symbols=request.symbols, success_symbols=2, empty_symbols=0, failed_symbols=0,
                rows_received=2, rows_persisted=2, adjusted_return_available_after_run=2, results=(),
                batch_first_symbol="000001.SZ", batch_last_symbol="000002.SZ",
                has_more_structural_members=True, next_start_after="000002.SZ",
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_from_project_root(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: "provider")
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", FakeStructuralCollector)

    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2"]) == 0
    assert captured["request"].symbols == ("000001.SZ", "000002.SZ")
    assert captured["request"].has_more_structural_members is True
    output = capsys.readouterr().out
    assert "Has more: YES" in output
    assert "Next start-after: 000002.SZ" in output


def test_structural_core_cli_uses_bounded_structural_scope_once(
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
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["as_of"] = as_of
            return SimpleNamespace(
                members=("000001.SZ", "000002.SZ", "600000.SH", "600519.SH")
            )

    class FakeCoreCollector:
        def __init__(self, *dependencies: object) -> None:
            captured["collector_dependencies"] = dependencies

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at.date(),
                requested_symbols=("000002.SZ", "600000.SH"),
                financial_start_period=date(2024, 1, 1),
                financial_end_period=current_at.date(),
                financial_success=2,
                financial_empty=0,
                financial_failed=0,
                financial_rows_persisted=2,
                industry_success=2,
                industry_empty=0,
                industry_failed=0,
                industry_rows_persisted=2,
                fully_successful_symbols=2,
                core_covered_after_run=2,
                results=(),
                batch_first_symbol="000002.SZ",
                batch_last_symbol="600000.SH",
                has_more_structural_members=True,
                next_start_after="600000.SH",
            )

    provider_calls = 0

    def provider_factory() -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "provider"

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr(
        cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at)
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralCoreFundamentalsCollector", FakeCoreCollector
    )

    assert main(
        [
            "fundamentals",
            "collect-structural-core",
            "--limit",
            "2",
            "--start-after",
            "000001.SZ",
        ]
    ) == 0
    assert provider_calls == 1
    assert captured["as_of"] == current_at.date()
    assert captured["request"].symbols == ("000002.SZ", "600000.SH")
    assert captured["request"].has_more_structural_members is True
    assert "Next start-after: 600000.SH" in capsys.readouterr().out


def test_structural_core_cli_reports_domain_failure_and_skips_end_or_bad_cursor_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_from_project_root = AppPaths.from_project_root
    captured: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("688001.SH",))

    class FailingCoreCollector:
        def __init__(self, *_dependencies: object) -> None:
            return None

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=date(2026, 9, 2),
                requested_symbols=("688001.SH",),
                financial_start_period=date(2024, 1, 1),
                financial_end_period=date(2026, 9, 2),
                financial_success=0,
                financial_empty=0,
                financial_failed=1,
                financial_rows_persisted=0,
                industry_success=1,
                industry_empty=0,
                industry_failed=0,
                industry_rows_persisted=1,
                fully_successful_symbols=0,
                core_covered_after_run=0,
                results=(
                    SimpleNamespace(
                        symbol="688001.SH",
                        financial_status=SimpleNamespace(value="failed"),
                        industry_status=SimpleNamespace(value="success"),
                    ),
                ),
                batch_first_symbol="688001.SH",
                batch_last_symbol="688001.SH",
                has_more_structural_members=False,
                next_start_after=None,
            )

    provider_calls = 0

    def provider_factory() -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "provider"

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralCoreFundamentalsCollector", FailingCoreCollector
    )

    assert main(["fundamentals", "collect-structural-core", "--limit", "1"]) == 1
    assert provider_calls == 1
    assert "Financial failed: 688001.SH" in capsys.readouterr().out
    assert main(
        [
            "fundamentals",
            "collect-structural-core",
            "--limit",
            "1",
            "--start-after",
            "688001.SH",
        ]
    ) == 0
    assert "No remaining structural members." in capsys.readouterr().out
    assert provider_calls == 1
    assert main(
        [
            "fundamentals",
            "collect-structural-core",
            "--limit",
            "1",
            "--start-after",
            "600000.SH",
        ]
    ) == 1
    assert "current structural member" in capsys.readouterr().err
    assert provider_calls == 1


def test_structural_valuation_cli_uses_one_current_timestamp_and_one_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current_at = datetime(2026, 9, 2, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    captured: dict[str, object] = {}
    original_from_project_root = AppPaths.from_project_root

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            captured["initialized"] = True

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, as_of: date) -> SimpleNamespace:
            captured["structural_as_of"] = as_of
            return SimpleNamespace(
                members=("000001.SZ", "000002.SZ", "600000.SH", "600519.SH")
            )

    class FakeValuationCollector:
        def __init__(self, *dependencies: object) -> None:
            captured["collector_dependencies"] = dependencies

        def collect(self, request: object) -> SimpleNamespace:
            captured["request"] = request
            return SimpleNamespace(
                as_of=current_at,
                requested_symbols=("000002.SZ", "600000.SH"),
                success_symbols=2,
                empty_symbols=0,
                failed_symbols=0,
                rows_persisted=2,
                valuation_available_after_run=2,
                results=(),
                batch_first_symbol="000002.SZ",
                batch_last_symbol="600000.SH",
                has_more_structural_members=True,
                next_start_after="600000.SH",
            )

    provider_calls = 0

    def provider_factory() -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "provider"

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr(
        cli_module, "datetime", SimpleNamespace(now=lambda _timezone: current_at)
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralValuationCollector", FakeValuationCollector
    )

    assert main(
        [
            "fundamentals",
            "collect-structural-valuation",
            "--limit",
            "2",
            "--start-after",
            "000001.SZ",
        ]
    ) == 0
    assert provider_calls == 1
    assert captured["structural_as_of"] == current_at.date()
    assert captured["request"].symbols == ("000002.SZ", "600000.SH")
    assert captured["request"].as_of is current_at
    assert "Valuation available after run: 2" in capsys.readouterr().out


def test_structural_valuation_cli_exit_and_no_provider_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_from_project_root = AppPaths.from_project_root
    outcome = "failed"

    class FakeRepository:
        def __init__(self, _paths: object) -> None:
            return None

        def initialize(self) -> None:
            return None

    class FakeUniverseService:
        def __init__(self, _repository: object, _settings: object) -> None:
            return None

        def build_current(self, _as_of: date) -> SimpleNamespace:
            return SimpleNamespace(members=("688001.SH",))

    class FakeValuationCollector:
        def __init__(self, *_dependencies: object) -> None:
            return None

        def collect(self, _request: object) -> SimpleNamespace:
            failed = int(outcome == "failed")
            empty = int(outcome == "empty")
            return SimpleNamespace(
                as_of=datetime(2026, 9, 2, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
                requested_symbols=("688001.SH",),
                success_symbols=0,
                empty_symbols=empty,
                failed_symbols=failed,
                rows_persisted=0,
                valuation_available_after_run=0,
                results=(
                    SimpleNamespace(
                        symbol="688001.SH",
                        status=SimpleNamespace(value=outcome),
                    ),
                ),
                batch_first_symbol="688001.SH",
                batch_last_symbol="688001.SH",
                has_more_structural_members=False,
                next_start_after=None,
            )

    provider_calls = 0

    def provider_factory() -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "provider"

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(
        cli_module.AppPaths,
        "from_project_root",
        lambda: original_from_project_root(tmp_path),
    )
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", provider_factory)
    monkeypatch.setattr(
        "stock_selector.collection.StructuralValuationCollector", FakeValuationCollector
    )

    assert main(["fundamentals", "collect-structural-valuation", "--limit", "1"]) == 1
    assert "Valuation failed: 688001.SH" in capsys.readouterr().out
    assert provider_calls == 1
    outcome = "empty"
    assert main(["fundamentals", "collect-structural-valuation", "--limit", "1"]) == 0
    assert provider_calls == 2
    assert main(
        [
            "fundamentals",
            "collect-structural-valuation",
            "--limit",
            "1",
            "--start-after",
            "688001.SH",
        ]
    ) == 0
    assert "No remaining structural members." in capsys.readouterr().out
    assert provider_calls == 2
    for limit in (0, -1, 21):
        assert main(
            ["fundamentals", "collect-structural-valuation", "--limit", str(limit)]
        ) == 1
    assert main(
        [
            "fundamentals",
            "collect-structural-valuation",
            "--limit",
            "1",
            "--start-after",
            "600000.SH",
        ]
    ) == 1
    assert provider_calls == 2


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
