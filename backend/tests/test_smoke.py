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
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.storage import LocalMarketRepository


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


def test_structural_adjusted_return_cli_uses_one_current_timestamp_and_current_window(
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
                requested_symbols=("000002.SZ", "600519.SH"), success_symbols=1, empty_symbols=1,
                failed_symbols=0, rows_received=1, rows_persisted=1, adjusted_return_available_after_run=1,
                results=(), batch_first_symbol="000002.SZ", batch_last_symbol="600519.SH",
                has_more_structural_members=False, next_start_after=None,
            )

    monkeypatch.setattr(cli_module, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_from_project_root(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=lambda _tz: current_at))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", FakeRepository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", FakeUniverseService)
    monkeypatch.setattr("stock_selector.providers.AKShareProvider", lambda: "provider")
    monkeypatch.setattr("stock_selector.collection.StructuralAdjustedReturnCollector", FakeStructuralCollector)

    assert main(["daily", "collect-structural-adjusted-returns", "--limit", "2", "--start-after", "000001.SZ"]) == 0
    request = captured["request"]
    assert captured["as_of"] == current_at.date()
    assert request.symbols == ("000002.SZ", "600519.SH")
    assert request.as_of is current_at
    assert (request.end_date - request.start_date).days + 1 == 180
    assert "Next start-after: complete" in capsys.readouterr().out


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
