"""Synthetic offline lifecycle contracts; no exchange evidence is asserted here."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from stock_selector.config import AppPaths
from stock_selector.config.models import UniverseConfig
from stock_selector.instrument_lifecycle_repair import (
    InstrumentLifecycleRepairService,
    LifecycleRepairBusyError,
    LifecycleRepairEntry,
    LifecycleRepairPersistenceError,
    LifecycleRepairRequest,
    LifecycleRepairValidationError,
    master_fingerprint,
)
from stock_selector.instrument_sync import (
    InstrumentMasterSyncService,
    InstrumentSyncRequest,
)
from stock_selector.models import Board, Exchange, Instrument, SecurityStatus
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe.builder import AshareUniverseBuilder
from stock_selector.universe.models import UniverseExclusionReason

SCENARIOS = (
    ("000016.SZ", date(2026, 10, 22)),
    ("601059.SH", date(2026, 10, 18)),
    ("601198.SH", date(2026, 10, 18)),
)


def _instrument(symbol: str, **changes: Any) -> Instrument:
    exchange = Exchange(symbol[-2:])
    board = {
        Exchange.SSE: Board.SH_MAIN,
        Exchange.SZSE: Board.SZ_MAIN,
        Exchange.BSE: Board.BSE,
    }[exchange]
    values = {
        "symbol": symbol,
        "name": f"synthetic-{symbol}",
        "exchange": exchange,
        "board": board,
        "listing_date": date(2000, 1, 1),
    }
    values.update(changes)
    return Instrument.model_validate(values)


def _master() -> tuple[Instrument, ...]:
    records = tuple(_instrument(symbol) for symbol, _ in SCENARIOS) + (
        _instrument("600519.SH", status=SecurityStatus.ST),
        _instrument(
            "600001.SH", delisting_date=date(2010, 1, 1), status=SecurityStatus.DELISTED
        ),
        _instrument("688001.SH", board=Board.STAR),
        _instrument("300001.SZ", board=Board.CHINEXT),
        _instrument("430001.BJ"),
    )
    return tuple(sorted(records, key=lambda item: item.symbol))


def _entry(
    symbol: str = "000016.SZ",
    boundary: date = date(2026, 10, 22),
    previous: date | None = None,
) -> LifecycleRepairEntry:
    return LifecycleRepairEntry(
        symbol,
        boundary,
        "synthetic://gate4-contract-case",
        "isolated contract verification",
        previous,
    )


def _request() -> LifecycleRepairRequest:
    return LifecycleRepairRequest(
        tuple(_entry(symbol, day) for symbol, day in SCENARIOS)
    )


def _repository(tmp_path: Path) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(_master())
    return repository


def _apply(
    repository: LocalMarketRepository, request: LifecycleRepairRequest, **overrides: Any
):  # type: ignore[no-untyped-def]
    fingerprint = overrides.pop("expected_master_fingerprint", None)
    if fingerprint is None:
        fingerprint = master_fingerprint(repository.load_instruments())
    options = {
        "operator_approved": True,
        "expected_master_fingerprint": fingerprint,
        "isolated_project_root": repository.paths.project_root,
    }
    options.update(overrides)
    return InstrumentLifecycleRepairService(repository).apply_for_testing(
        request, **options
    )


def test_single_and_multi_preview_are_sorted_deterministic(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = InstrumentLifecycleRepairService(repository)
    single = service.preview(LifecycleRepairRequest((_entry(),)))
    assert (
        single.existing_master_rows,
        single.requested_count,
        single.changed_count,
    ) == (8, 1, 1)
    assert single.already_correct_count == 0
    assert single.preserved_historical_rows == 8
    assert single.changes[0].previous is None
    assert single.changes[0].entry.delisting_date == date(2026, 10, 22)
    forward = service.preview(_request())
    reverse = service.preview(
        LifecycleRepairRequest(tuple(reversed(_request().entries)))
    )
    assert forward == reverse
    assert forward.validation_status == "valid"
    assert forward.changed_count == 3
    assert not forward.persistence_performed


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "000016.sz"},
        {"symbol": " 000016.SZ"},
        {"symbol": "００００１６.SZ"},
        {"symbol": "000016"},
        {"delisting_date": "2026-10-22"},
        {"delisting_date": None},
        {"delisting_date": datetime(2026, 10, 22, tzinfo=UTC)},
        {"expected_previous": "2026-10-22"},
        {"evidence_reference": " "},
        {"operator_reason": ""},
    ],
)
def test_entry_rejects_invalid_symbols_dates_or_evidence(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(LifecycleRepairValidationError):
        replace(_entry(), **changes)


def test_empty_duplicate_and_untyped_requests_rejected() -> None:
    for entries in ((), (_entry(), _entry()), (object(),), [_entry()]):
        with pytest.raises(LifecycleRepairValidationError):
            LifecycleRepairRequest(entries)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LifecycleRepairEntry(**{**_entry().__dict__, "name": "identity change"})


@pytest.mark.parametrize(
    ("entry", "outcome"),
    [
        (_entry("999999.SH"), "unknown_symbol"),
        (_entry(boundary=date(1999, 12, 31)), "before_listing_date"),
        (_entry(previous=date(2020, 1, 1)), "unexpected_previous"),
        (_entry("600001.SH", previous=date(2010, 1, 1)), "conflicting_existing_date"),
    ],
)
def test_master_validation_returns_auditable_rejected_report(
    tmp_path: Path,
    entry: LifecycleRepairEntry,
    outcome: str,
) -> None:
    repository = _repository(tmp_path)
    before = repository.load_instruments()
    for action in (
        InstrumentLifecycleRepairService(repository).preview,
        lambda request: _apply(repository, request),
    ):
        with pytest.raises(LifecycleRepairValidationError) as caught:
            action(LifecycleRepairRequest((entry,)))
        report = caught.value.report
        assert report is not None
        assert report.validation_status == "rejected"
        assert report.changes[0].outcome == outcome
        assert not report.persistence_performed
        assert report.unknown_symbols == (
            (entry.symbol,) if outcome == "unknown_symbol" else ()
        )
        assert report.conflicting_symbols == (
            () if outcome == "unknown_symbol" else (entry.symbol,)
        )
    assert repository.load_instruments() == before


def test_preview_uses_read_only_repository_and_never_locks_or_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    readonly = LocalMarketRepository.open_read_only(repository.paths)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("preview attempted a write, lock, initialization, or refresh")

    for name in ("save_instruments", "initialize", "instrument_master_writer"):
        monkeypatch.setattr(readonly, name, forbidden)
    monkeypatch.setattr(readonly._catalog, "refresh_views", forbidden)
    report = InstrumentLifecycleRepairService(readonly).preview(_request())
    assert not report.persistence_performed
    assert files == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_cold_preview_creates_no_lock_or_directories(tmp_path: Path) -> None:
    root = tmp_path / "cold"
    readonly = LocalMarketRepository.open_read_only(AppPaths.from_project_root(root))
    with pytest.raises(LifecycleRepairValidationError):
        InstrumentLifecycleRepairService(readonly).preview(_request())
    assert not root.exists()


def test_apply_preserves_complete_master_and_metadata(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    before = repository.load_instruments()
    report = _apply(repository, _request())
    after = repository.load_instruments()
    boundaries = dict(SCENARIOS)
    assert len(before) == len(after) == report.preserved_historical_rows
    assert {item.symbol for item in before} == {item.symbol for item in after}
    for old, new in zip(before, after, strict=True):
        values = old.model_dump()
        if old.symbol in boundaries:
            values["delisting_date"] = boundaries[old.symbol]
        assert new.model_dump() == values
    assert report.persistence_performed
    assert report.parquet_readback_verified and report.catalog_readback_verified


def test_idempotent_apply_never_saves_or_refreshes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _apply(repository, _request())
    request = LifecycleRepairRequest(tuple(_entry(s, d, d) for s, d in SCENARIOS))
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("idempotent apply attempted persistence")

    monkeypatch.setattr(repository, "save_instruments", forbidden)
    monkeypatch.setattr(repository._catalog, "refresh_views", forbidden)
    report = _apply(repository, request)
    assert report.changed_count == 0 and report.already_correct_count == 3
    assert not report.persistence_performed
    assert report.parquet_readback_verified and report.catalog_readback_verified
    assert files == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_identical_evidence_reapplication_requires_fresh_baseline_but_no_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    request = _request()
    original_fingerprint = master_fingerprint(repository.load_instruments())
    _apply(repository, request)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("repeat evidence attempted save")

    monkeypatch.setattr(repository, "save_instruments", forbidden)
    preview = InstrumentLifecycleRepairService(repository).preview(request)
    assert preview.changed_count == 0 and preview.already_correct_count == 3
    report = _apply(repository, request)
    assert not report.persistence_performed
    with pytest.raises(LifecycleRepairValidationError, match="stale"):
        _apply(repository, request, expected_master_fingerprint=original_fingerprint)


def test_apply_requires_explicit_intent_fingerprint_and_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    for overrides in (
        {"operator_approved": False},
        {"operator_approved": 1},
        {"expected_master_fingerprint": ""},
        {"isolated_project_root": tmp_path / "different"},
    ):
        with pytest.raises(LifecycleRepairValidationError):
            _apply(repository, _request(), **overrides)
    # Even rejection tests use only synthetic paths; never inspect real runtime.
    simulated_production = AppPaths.from_project_root(tmp_path / "pretend_production")
    original_paths = AppPaths.from_project_root
    monkeypatch.setattr(
        AppPaths,
        "from_project_root",
        classmethod(
            lambda cls, project_root=None: (
                simulated_production
                if project_root is None
                else original_paths(project_root)
            )
        ),
    )
    production = LocalMarketRepository(simulated_production)
    with pytest.raises(LifecycleRepairValidationError, match="production apply"):
        InstrumentLifecycleRepairService(production).apply_for_testing(
            _request(),
            operator_approved=True,
            expected_master_fingerprint="0" * 64,
            isolated_project_root=production.paths.project_root,
        )
    redirected = replace(repository.paths, metadata_dir=production.paths.metadata_dir)
    with pytest.raises(LifecycleRepairValidationError, match="not isolated"):
        InstrumentLifecycleRepairService(
            LocalMarketRepository(redirected)
        ).apply_for_testing(
            _request(),
            operator_approved=True,
            expected_master_fingerprint="0" * 64,
            isolated_project_root=tmp_path,
        )


def test_fingerprint_covers_every_field_and_is_order_independent() -> None:
    rows = _master()
    assert master_fingerprint(rows) == master_fingerprint(tuple(reversed(rows)))
    assert master_fingerprint(rows) != master_fingerprint(
        (
            rows[0].model_copy(update={"name": "changed"}),
            *rows[1:],
        )
    )
    with pytest.raises(LifecycleRepairValidationError, match="duplicate master"):
        master_fingerprint((*rows, rows[0]))
    with pytest.raises(LifecycleRepairValidationError, match="domain record"):
        master_fingerprint((rows[0].model_copy(update={"board": Board.BSE}),))


def test_stale_fingerprint_rejects_unrelated_metadata_change(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    fingerprint = master_fingerprint(repository.load_instruments())
    rows = repository.load_instruments()
    repository.save_instruments(
        (rows[0].model_copy(update={"name": "concurrent"}), *rows[1:])
    )
    current = repository.load_instruments()
    with pytest.raises(LifecycleRepairValidationError, match="stale"):
        _apply(repository, _request(), expected_master_fingerprint=fingerprint)
    assert repository.load_instruments() == current


def test_revalidation_occurs_inside_writer_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    fingerprint = master_fingerprint(repository.load_instruments())
    original_writer = repository.instrument_master_writer

    @contextmanager
    def racing_writer(*, timeout_seconds: float = 5.0):  # type: ignore[no-untyped-def]
        with original_writer(timeout_seconds=timeout_seconds):
            rows = repository.load_instruments()
            changed = tuple(
                item.model_copy(update={"delisting_date": date(2026, 10, 21)})
                if item.symbol == "000016.SZ"
                else item
                for item in rows
            )
            with monkeypatch.context() as patch:
                patch.setattr(repository, "instrument_master_writer", original_writer)
                repository.save_instruments(changed)
            yield

    monkeypatch.setattr(repository, "instrument_master_writer", racing_writer)
    with pytest.raises(LifecycleRepairValidationError) as caught:
        _apply(repository, _request(), expected_master_fingerprint=fingerprint)
    assert caught.value.report is not None
    assert caught.value.report.conflicting_symbols == ("000016.SZ",)


def test_real_writer_contention_causes_no_save(tmp_path: Path) -> None:
    import threading

    repository = _repository(tmp_path)
    before = repository.load_instruments()
    ready, release = threading.Event(), threading.Event()

    def holder() -> None:
        with repository.instrument_master_writer():
            ready.set()
            release.wait(5)

    worker = threading.Thread(target=holder)
    worker.start()
    try:
        assert ready.wait(5)
        with pytest.raises(LifecycleRepairBusyError):
            _apply(repository, _request(), timeout_seconds=0)
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert repository.load_instruments() == before


@pytest.mark.parametrize("fault", ["parquet", "catalog", "save_after_write", "refresh"])
def test_readback_and_persistence_failures_are_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    repository = _repository(tmp_path)
    fingerprint = master_fingerprint(repository.load_instruments())
    original_save = repository.save_instruments
    original_load = repository.load_instruments
    previous = original_load()

    def save_then_fault(rows: tuple[Instrument, ...]) -> None:
        original_save(rows)
        if fault == "save_after_write":
            raise StorageError("synthetic post-save failure")
        if fault == "parquet":
            monkeypatch.setattr(repository, "load_instruments", lambda: previous)
        if fault == "catalog":
            monkeypatch.setattr(
                repository, "catalog_instruments_match", lambda _: False
            )

    if fault == "refresh":

        def fail_refresh() -> None:
            raise StorageError("synthetic refresh failure")

        monkeypatch.setattr(repository._catalog, "refresh_views", fail_refresh)
    else:
        monkeypatch.setattr(repository, "save_instruments", save_then_fault)
    with pytest.raises(LifecycleRepairPersistenceError) as caught:
        _apply(repository, _request(), expected_master_fingerprint=fingerprint)
    assert caught.value.persistence_uncertain
    assert "uncertain" in str(caught.value)
    assert caught.value.__cause__ is not None
    # Direct saved-data readback confirms no automatic rollback was attempted.
    assert {row.symbol: row.delisting_date for row in original_load()}[
        "000016.SZ"
    ] == date(2026, 10, 22)


def test_pre_save_read_failure_does_not_claim_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    fingerprint = master_fingerprint(repository.load_instruments())

    def fail_load() -> tuple[Instrument, ...]:
        raise StorageError("synthetic read failure")

    monkeypatch.setattr(repository, "load_instruments", fail_load)
    with pytest.raises(LifecycleRepairPersistenceError) as caught:
        _apply(repository, _request(), expected_master_fingerprint=fingerprint)
    assert not caught.value.persistence_uncertain


@pytest.mark.parametrize(("symbol", "boundary"), SCENARIOS)
def test_inclusive_boundary_and_historical_membership(
    tmp_path: Path,
    symbol: str,
    boundary: date,
) -> None:
    repository = _repository(tmp_path)
    original = repository.load_instruments()
    _apply(repository, _request())
    repaired = repository.load_instruments()
    builder = AshareUniverseBuilder()
    for day in (date(2020, 1, 1), boundary - timedelta(days=1), boundary):
        before = builder.build(original, UniverseConfig(), day)
        after = builder.build(repaired, UniverseConfig(), day)
        assert (symbol in before.members) == (symbol in after.members)
        assert symbol in after.members
    excluded = builder.build(repaired, UniverseConfig(), boundary + timedelta(days=1))
    decision = next(item for item in excluded.decisions if item.symbol == symbol)
    assert not decision.included
    assert decision.reasons == (UniverseExclusionReason.DELISTED,)


def test_ordinary_sync_preserves_repaired_and_provider_absent_history(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _apply(repository, _request())
    repaired = repository.load_instruments()
    provider_rows = tuple(
        item.model_copy(update={"delisting_date": None})
        for item in repaired
        if item.symbol != "600001.SH"
    )

    class SyntheticProvider:
        info = type("Info", (), {"name": "synthetic"})()

        def get_instruments(self) -> tuple[Instrument, ...]:
            return provider_rows

    report = InstrumentMasterSyncService(SyntheticProvider(), repository).sync(  # type: ignore[arg-type]
        InstrumentSyncRequest(
            apply=True,
            expected_min_total=7,
            expected_min_boards={board: 1 for board in Board},
        )
    )
    assert report.lifecycle_preserved_count == 3
    assert report.retained_historical_symbols == ("600001.SH",)
    assert repository.load_instruments() == repaired


def test_synthetic_5550_master_retains_all_rows_with_5547_current_members(
    tmp_path: Path,
) -> None:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    rows = tuple(_instrument(symbol) for symbol, _ in SCENARIOS) + tuple(
        _instrument(f"{100000 + index:06d}.SH") for index in range(5547)
    )
    repository.save_instruments(rows)
    builder = AshareUniverseBuilder()
    before = builder.build(rows, UniverseConfig(), date(2026, 10, 26))
    assert len(before.members) == 5550
    report = _apply(repository, _request())
    after = repository.load_instruments()
    assert len(after) == report.preserved_historical_rows == 5550
    current = builder.build(after, UniverseConfig(), date(2026, 10, 26))
    assert len(current.members) == 5547
    assert set(before.members) - set(current.members) == {s for s, _ in SCENARIOS}
    historical = builder.build(after, UniverseConfig(), date(2020, 1, 1))
    assert len(historical.members) == 5550
