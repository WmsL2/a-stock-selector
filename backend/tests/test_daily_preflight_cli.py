"""CLI exit-code and no-workflow contracts for daily preflight."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from stock_selector import cli
from stock_selector.cli import main
from stock_selector.config import AppPaths, Settings
from stock_selector.daily_preflight import DailyPreflightOutcome

NOW = datetime(2026, 10, 23, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_daily_preflight_cold_cli_is_blocked_and_does_not_initialize(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    original_paths = AppPaths.from_project_root
    monkeypatch.setattr(cli.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _timezone: NOW))

    assert main(["selection", "daily-preflight"]) == 3
    assert "Outcome: BLOCKED" in capsys.readouterr().out
    assert not (tmp_path / "runtime").exists()


def test_daily_preflight_cli_maps_ready_and_error_without_selection(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    original_paths = AppPaths.from_project_root
    monkeypatch.setattr(cli.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli, "load_settings", lambda _path: Settings())
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _timezone: NOW))

    class Service:
        def __init__(self, *_args): pass
        def run(self, received):
            assert received == NOW
            return SimpleNamespace(
                as_of=NOW, configured_timezone="Asia/Shanghai", outcome=DailyPreflightOutcome.READY,
                local_storage_state=SimpleNamespace(value="available"), structural_members=1,
                risk_complete_members=1, risk_eligible_members=1,
                eligible_factor_input_covered=1, eligible_factor_input_missing=0,
                upstream_inputs_ready=True, readiness_blockers=(), provider_unchecked=True,
                current_risk_timezone_note=None, error=None,
                recommended_next_operator_action="human approval",
            )

    monkeypatch.setattr("stock_selector.daily_preflight.DailyPreflightService", Service)
    assert main(["selection", "daily-preflight"]) == 0
    with pytest.raises(SystemExit) as raised:
        main(["selection", "daily-preflight", "--unknown"])
    assert raised.value.code == 2



def test_daily_preflight_cli_maps_actual_corrupt_catalog_to_error(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    from stock_selector.storage import LocalMarketRepository

    original_paths = AppPaths.from_project_root
    paths = original_paths(tmp_path)
    repository = LocalMarketRepository(paths)
    repository.initialize()
    repository.catalog_path.write_bytes(b'not a duckdb catalog')
    monkeypatch.setattr(cli.AppPaths, 'from_project_root', lambda: paths)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: Settings())
    monkeypatch.setattr(cli, 'datetime', SimpleNamespace(now=lambda _timezone: NOW))

    assert main(['selection', 'daily-preflight']) == 1
    output = capsys.readouterr()
    assert 'Outcome: ERROR' in output.out
    assert 'Structural members: unavailable' in output.out
    assert 'READY' not in output.out
    assert 'Traceback' not in output.out + output.err


def test_daily_preflight_cli_reads_one_configured_timezone_instant_and_passes_it_unchanged(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from stock_selector.config.models import AppConfig
    from stock_selector.daily_preflight import DailyPreflightService

    original_paths = AppPaths.from_project_root
    paths = original_paths(tmp_path)
    settings = Settings(app=AppConfig(timezone='Asia/Tokyo'))
    instant = datetime(2026, 10, 23, 0, 30, tzinfo=ZoneInfo('Asia/Tokyo'))
    seen = []
    original_run = DailyPreflightService.run

    def capture(self, received):  # type: ignore[no-untyped-def]
        seen.append(received)
        return original_run(self, received)

    def one_now(timezone):  # type: ignore[no-untyped-def]
        assert timezone == ZoneInfo('Asia/Tokyo')
        return instant

    monkeypatch.setattr(cli.AppPaths, 'from_project_root', lambda: paths)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: settings)
    monkeypatch.setattr(cli, 'datetime', SimpleNamespace(now=one_now))
    monkeypatch.setattr(DailyPreflightService, 'run', capture)

    assert main(['selection', 'daily-preflight']) == 3
    assert seen == [instant]
