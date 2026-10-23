"""Read-only daily preflight integration contracts."""

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config import AppPaths, Settings
from stock_selector.daily_preflight import DailyPreflightOutcome, DailyPreflightService
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
)
from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository, StorageIOError

NOW = datetime(2026, 10, 23, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
SYMBOLS = ("000001.SZ", "600519.SH")


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths.from_project_root(tmp_path)


def _repository(tmp_path: Path) -> LocalMarketRepository:
    repository = LocalMarketRepository(_paths(tmp_path))
    repository.initialize()
    repository.save_instruments(
        tuple(
            Instrument(
                symbol=symbol,
                name=symbol,
                exchange=Exchange.SZSE if symbol.endswith("SZ") else Exchange.SSE,
                board=Board.SZ_MAIN if symbol.endswith("SZ") else Board.SH_MAIN,
                listing_date=date(2000, 1, 1),
            )
            for symbol in SYMBOLS
        )
    )
    return repository


def _risk(symbol: str, *, as_of: date | None = None, suspended: bool = False) -> DatedRiskState:
    return DatedRiskState(
        symbol=symbol,
        as_of=as_of or NOW.date(),
        is_st=False,
        is_suspended=suspended,
        is_delisting_period=False,
        observed_at=NOW,
        source="test",
    )


def _seed_membership(repository: LocalMarketRepository, symbols: tuple[str, ...]) -> None:
    for symbol in symbols:
        repository.upsert_financial_records(
            (
                FinancialRecord(
                    symbol=symbol,
                    report_period=date(2025, 12, 31),
                    announcement_date=date(2026, 3, 1),
                    available_at=NOW,
                    roe=1,
                    roa=1,
                    gross_margin=1,
                    net_margin=1,
                    revenue=1,
                    net_profit=1,
                    deducted_net_profit=1,
                    source="test",
                ),
            )
        )
        repository.upsert_industry_records(
            (
                IndustryRecord(
                    symbol=symbol,
                    industry_code="C15",
                    industry_name="test",
                    classification="test",
                    effective_from=date(2020, 1, 1),
                    source="test",
                ),
            )
        )


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def _run(tmp_path: Path):  # type: ignore[no-untyped-def]
    return DailyPreflightService(_paths(tmp_path), Settings()).run(NOW)


def test_cold_repository_is_blocked_without_creating_runtime(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.BLOCKED
    assert result.local_storage_state.value == "cold"
    assert result.readiness_blockers == ("no_structural_members",)
    assert not (tmp_path / "runtime").exists()


def test_initialized_empty_repository_is_blocked_without_false_error(tmp_path: Path) -> None:
    LocalMarketRepository(_paths(tmp_path)).initialize()

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.BLOCKED
    assert result.local_storage_state.value == "available"
    assert result.readiness_blockers == ("no_structural_members",)


def test_missing_catalog_with_evidence_is_error_without_repair(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.catalog_path.unlink()
    before = _snapshot(tmp_path)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.ERROR
    assert result.structural_members is None
    assert "catalog is missing" in (result.error or "")
    assert _snapshot(tmp_path) == before


def test_corrupt_catalog_is_error_without_repair(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.catalog_path.write_bytes(b"not a duckdb catalog")
    before = _snapshot(tmp_path)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.ERROR
    assert result.structural_members is None
    assert _snapshot(tmp_path) == before


def test_exact_date_risk_and_membership_readiness_are_truthful_and_read_only(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in SYMBOLS))
    _seed_membership(repository, SYMBOLS)
    before = _snapshot(tmp_path)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.READY
    assert result.upstream_inputs_ready is True
    assert result.risk_complete_members == len(SYMBOLS)
    assert result.eligible_factor_input_missing == 0
    assert result.provider_unchecked is True
    assert _snapshot(tmp_path) == before


def test_stale_and_partial_risk_are_blocked_without_carry_forward(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.upsert_risk_states((_risk(SYMBOLS[0], as_of=date(2026, 10, 22)),))
    _seed_membership(repository, SYMBOLS)

    stale = _run(tmp_path)
    assert stale.outcome is DailyPreflightOutcome.BLOCKED
    assert stale.risk_complete_members == 0
    assert stale.readiness_blockers == ("risk_state_coverage_incomplete",)

    repository.upsert_risk_states((_risk(SYMBOLS[0]),))
    partial = _run(tmp_path)
    assert partial.risk_complete_members == 1
    assert partial.readiness_blockers == ("risk_state_coverage_incomplete",)


def test_risk_ineligible_factor_gap_does_not_block_but_eligible_gap_does(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.upsert_risk_states((_risk(SYMBOLS[0]), _risk(SYMBOLS[1], suspended=True)))
    _seed_membership(repository, (SYMBOLS[0],))
    ready = _run(tmp_path)
    assert ready.outcome is DailyPreflightOutcome.READY

    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in SYMBOLS))
    blocked = _run(tmp_path)
    assert blocked.outcome is DailyPreflightOutcome.BLOCKED
    assert blocked.readiness_blockers == ("eligible_factor_input_coverage_incomplete",)


def test_complete_risk_with_no_eligible_members_is_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.upsert_risk_states(
        tuple(_risk(symbol, suspended=True) for symbol in SYMBOLS)
    )
    _seed_membership(repository, SYMBOLS)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.BLOCKED
    assert result.risk_complete_members == len(SYMBOLS)
    assert result.risk_eligible_members == 0
    assert result.readiness_blockers == ("no_risk_eligible_members",)


def test_read_only_repository_rejects_mutations_before_filesystem_access(tmp_path: Path) -> None:
    _repository(tmp_path)
    read_only = LocalMarketRepository.open_read_only(_paths(tmp_path))
    before = _snapshot(tmp_path)

    with pytest.raises(StorageIOError, match="read-only"):
        read_only.save_instruments(())

    assert _snapshot(tmp_path) == before



def test_ready_without_hfq_and_with_future_pit_records_keeps_membership_semantics(tmp_path: Path) -> None:
    """Readiness is authoritative stored membership, not a hidden scoreability check."""
    repository = _repository(tmp_path)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in SYMBOLS))
    future = NOW.replace(day=24)
    for symbol in SYMBOLS:
        repository.upsert_financial_records((
            FinancialRecord(symbol=symbol, report_period=date(2025, 12, 31),
                            announcement_date=date(2026, 10, 24), available_at=future,
                            roe=1, source='test'),
        ))
        repository.upsert_industry_records((
            IndustryRecord(symbol=symbol, industry_code='C15', industry_name='test',
                           classification='test', effective_from=date(2020, 1, 1), source='test'),
        ))

    result = _run(tmp_path)

    assert repository.load_adjusted_return_symbols() == ()
    assert result.outcome is DailyPreflightOutcome.READY
    assert result.upstream_inputs_ready is True
    assert result.readiness_blockers == ()


def test_repeated_preflight_is_deterministic_and_creates_no_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in SYMBOLS))
    _seed_membership(repository, SYMBOLS)
    before = _snapshot(tmp_path)
    before_paths = {path.relative_to(tmp_path) for path in tmp_path.rglob('*')}
    catalog_size = repository.catalog_path.stat().st_size

    first = _run(tmp_path)
    second = _run(tmp_path)

    assert first == second
    assert first.outcome is DailyPreflightOutcome.READY
    assert _snapshot(tmp_path) == before
    assert repository.catalog_path.stat().st_size == catalog_size
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob('*')} == before_paths
    unexpected = [
        path for path in tmp_path.rglob('*')
        if path.is_file() and path.name.endswith(('.wal', '.tmp', '.log'))
    ]
    assert unexpected == []


@pytest.mark.parametrize('mutation', ('unsupported_schema', 'missing_view', 'missing_metadata'))
def test_invalid_catalog_shapes_are_error_without_repair(tmp_path: Path, mutation: str) -> None:
    import duckdb

    repository = _repository(tmp_path)
    repository.save_instruments((
        Instrument(symbol=SYMBOLS[0], name='test', exchange=Exchange.SZSE,
                   board=Board.SZ_MAIN, listing_date=date(2000, 1, 1)),
    ))
    connection = duckdb.connect(str(repository.catalog_path))
    try:
        if mutation == 'unsupported_schema':
            connection.execute('UPDATE storage_metadata SET schema_version = 999')
        elif mutation == 'missing_view':
            connection.execute('DROP VIEW instruments')
        else:
            connection.execute('DROP TABLE storage_metadata')
    finally:
        connection.close()
    before = _snapshot(tmp_path)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.ERROR
    assert result.structural_members is None
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize('failure', ('permission denied', 'database is locked'))
def test_read_only_catalog_connection_failures_are_error_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import duckdb

    from stock_selector.storage import duckdb_catalog

    _repository(tmp_path)
    before = _snapshot(tmp_path)

    def fail_connect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise duckdb.IOException(failure)

    monkeypatch.setattr(duckdb_catalog.duckdb, 'connect', fail_connect)
    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.ERROR
    assert result.structural_members is None
    assert _snapshot(tmp_path) == before


def test_preflight_never_calls_provider_network_scoring_refresh_or_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the real ready path while all forbidden collaborators fail fast."""
    import socket

    import requests

    from stock_selector.factors.engine import FiveFactorEngine
    from stock_selector.providers.akshare_provider import AKShareProvider
    from stock_selector.scoring.engine import BaseScoreEngine
    from stock_selector.selection.current_refresh import CurrentSelectionRefreshService
    from stock_selector.selection.daily import DailySelectionService
    from stock_selector.selection.research import SelectionResearchArtifactStore

    repository = _repository(tmp_path)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in SYMBOLS))
    _seed_membership(repository, SYMBOLS)

    def forbidden(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError('forbidden collaborator was called')

    monkeypatch.setattr(AKShareProvider, '__init__', forbidden)
    for name in dir(AKShareProvider):
        if name.startswith('fetch_'):
            monkeypatch.setattr(AKShareProvider, name, forbidden)
    monkeypatch.setattr(requests.api, 'request', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(DailySelectionService, '__init__', forbidden)
    monkeypatch.setattr(FiveFactorEngine, 'compute', forbidden)
    monkeypatch.setattr(BaseScoreEngine, 'compute', forbidden)
    monkeypatch.setattr(CurrentSelectionRefreshService, '__init__', forbidden)
    monkeypatch.setattr(SelectionResearchArtifactStore, 'export', forbidden)

    result = _run(tmp_path)

    assert result.outcome is DailyPreflightOutcome.READY
    assert result.provider_unchecked is True



def test_configured_tokyo_date_is_used_without_shanghai_date_substitution(tmp_path: Path) -> None:
    from stock_selector.config.models import AppConfig

    as_of = datetime(2026, 10, 23, 0, 30, tzinfo=ZoneInfo('Asia/Tokyo'))
    repository = _repository(tmp_path)
    repository.upsert_risk_states(tuple(
        DatedRiskState(symbol=symbol, as_of=as_of.date(), is_st=False, is_suspended=False,
                        is_delisting_period=False, observed_at=as_of, source='test')
        for symbol in SYMBOLS
    ))
    _seed_membership(repository, SYMBOLS)

    result = DailyPreflightService(
        _paths(tmp_path), Settings(app=AppConfig(timezone='Asia/Tokyo'))
    ).run(as_of)

    assert result.outcome is DailyPreflightOutcome.READY
    assert result.as_of == as_of
    assert result.current_risk_timezone_note == (
        'Current-risk providers use Asia/Shanghai dates; the configured-timezone '
        'date 2026-10-23 differs from Shanghai date 2026-10-22.'
    )
