"""Offline regressions for guarded instrument-master synchronization."""

from datetime import date
from typing import Any, cast

import pytest

from stock_selector.config import AppPaths
from stock_selector.instrument_sync import (
    InstrumentMasterSyncService,
    InstrumentSyncComparisonError,
    InstrumentSyncPersistenceError,
    InstrumentSyncRequest,
    InstrumentSyncValidationError,
)
from stock_selector.models import Board, Exchange, Instrument, SecurityStatus
from stock_selector.providers.errors import ProviderConnectionError, ProviderDataError
from stock_selector.storage import LocalMarketRepository, StorageError


def _instrument(board: Board, code: str, **changes: Any) -> Instrument:
    exchange = {
        Board.SH_MAIN: Exchange.SSE,
        Board.STAR: Exchange.SSE,
        Board.SZ_MAIN: Exchange.SZSE,
        Board.CHINEXT: Exchange.SZSE,
        Board.BSE: Exchange.BSE,
    }[board]
    values = {
        "symbol": f"{code}.{exchange.value}",
        "name": f"name-{code}",
        "exchange": exchange,
        "board": board,
        "listing_date": date(2020, 1, 1),
        "status": SecurityStatus.ACTIVE,
    }
    values.update(changes)
    return Instrument(**values)


def _five_board_candidate(**changes: Any) -> tuple[Instrument, ...]:
    items = (
        _instrument(Board.SH_MAIN, "600001"),
        _instrument(Board.SZ_MAIN, "000001"),
        _instrument(Board.CHINEXT, "300001"),
        _instrument(Board.STAR, "688001"),
        _instrument(Board.BSE, "430001"),
    )
    return tuple(sorted(changes.get("items", items), key=lambda item: item.symbol))


class FakeProvider:
    def __init__(self, result: tuple[Instrument, ...] | Exception) -> None:
        self.result = result
        self.calls = 0
        self.info = type("Info", (), {"name": "fake"})()

    def get_instruments(self) -> tuple[Instrument, ...]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def get_daily_bars(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect daily bars")

    def get_realtime_quotes(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect realtime quotes")

    def get_current_risk_states(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect risk states")

    def get_financial_records(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect financial records")

    def get_industry_records(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect industry records")

    def get_valuation_records(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect valuation records")

    def get_adjusted_daily_returns(self, *_: object) -> None:
        pytest.fail("instrument sync must not collect adjusted returns")


def _repository(tmp_path: Any) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _apply_request() -> InstrumentSyncRequest:
    return InstrumentSyncRequest(
        apply=True,
        expected_min_total=5,
        expected_min_boards={board: 1 for board in Board},
    )


def test_preview_fetches_once_and_never_replaces_existing_master(tmp_path: Any) -> None:
    class RecordingRepository(LocalMarketRepository):
        def __init__(self, paths: AppPaths) -> None:
            super().__init__(paths)
            self.save_calls = 0

        def save_instruments(self, instruments: tuple[Instrument, ...]) -> None:
            self.save_calls += 1
            super().save_instruments(instruments)

    repository = RecordingRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    old = _five_board_candidate()
    repository.save_instruments(old)
    candidate = _five_board_candidate(items=tuple(reversed(old)))
    provider = FakeProvider(candidate)

    report = InstrumentMasterSyncService(provider, repository).sync(
        InstrumentSyncRequest()
    )

    assert provider.calls == 1
    assert repository.save_calls == 1  # Initial fixture write only; preview adds none.
    assert repository.load_instruments() == old
    assert report.mode == "preview"
    assert not report.persistence_performed and not report.readback_verified


@pytest.mark.parametrize(
    "sync_request",
    (
        InstrumentSyncRequest(apply=True),
        InstrumentSyncRequest(apply=True, expected_min_total=5, expected_min_boards={}),
        InstrumentSyncRequest(
            apply=True,
            expected_min_total=0,
            expected_min_boards={board: 1 for board in Board},
        ),
    ),
)
def test_apply_rejects_invalid_floors_before_network(
    tmp_path: Any, sync_request: InstrumentSyncRequest
) -> None:
    provider = FakeProvider(_five_board_candidate())
    with pytest.raises(InstrumentSyncValidationError):
        InstrumentMasterSyncService(provider, _repository(tmp_path)).sync(sync_request)
    assert provider.calls == 0


def test_apply_validates_five_boards_and_readback(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    provider = FakeProvider(_five_board_candidate())
    report = InstrumentMasterSyncService(provider, repository).sync(_apply_request())
    assert provider.calls == 1
    assert report.candidate_total == 5
    assert report.persistence_performed and report.readback_verified
    assert len(repository.load_instruments()) == 5


@pytest.mark.parametrize(
    "candidate", ((), _five_board_candidate(items=_five_board_candidate()[:-1]))
)
def test_empty_or_missing_board_candidate_never_writes(
    tmp_path: Any, candidate: tuple[Instrument, ...]
) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate(
        items=_five_board_candidate() + (_instrument(Board.SH_MAIN, "600002"),)
    )
    repository.save_instruments(existing)
    with pytest.raises(InstrumentSyncValidationError):
        InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
            _apply_request()
        )
    assert repository.load_instruments() == existing


def test_apply_rejects_too_small_and_duplicate_candidate_without_writes(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    with pytest.raises(InstrumentSyncValidationError):
        InstrumentMasterSyncService(FakeProvider(existing), repository).sync(
            InstrumentSyncRequest(
                apply=True,
                expected_min_total=6,
                expected_min_boards={board: 1 for board in Board},
            )
        )
    with pytest.raises(InstrumentSyncValidationError):
        InstrumentMasterSyncService(
            FakeProvider(existing + (existing[0],)), repository
        ).sync(_apply_request())
    assert repository.load_instruments() == existing


def test_apply_rejects_one_board_below_its_floor_without_master_write(
    tmp_path: Any,
) -> None:
    class RecordingRepository(LocalMarketRepository):
        def __init__(self, paths: AppPaths) -> None:
            super().__init__(paths)
            self.save_calls = 0

        def save_instruments(self, instruments: tuple[Instrument, ...]) -> None:
            self.save_calls += 1
            super().save_instruments(instruments)

    repository = RecordingRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    candidate = _five_board_candidate(
        items=_five_board_candidate() + (_instrument(Board.SH_MAIN, "600002"),)
    )
    floors = {board: 1 for board in Board}
    floors[Board.BSE] = 2
    with pytest.raises(InstrumentSyncValidationError, match="bse count"):
        InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
            InstrumentSyncRequest(
                apply=True, expected_min_total=5, expected_min_boards=floors
            )
        )
    assert repository.save_calls == 0
    assert repository.load_instruments() == ()


@pytest.mark.parametrize(
    "error",
    (
        ProviderConnectionError("fake", "instruments", "offline"),
        ProviderDataError("fake", "instruments", "invalid"),
    ),
)
def test_provider_errors_preserve_existing_master(
    tmp_path: Any, error: Exception
) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    provider = FakeProvider(error)
    with pytest.raises((ProviderConnectionError, ProviderDataError)):
        InstrumentMasterSyncService(provider, repository).sync(_apply_request())
    assert provider.calls == 1
    assert repository.load_instruments() == existing


def test_apply_rejects_removal_board_shrink_and_identity_change(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate(
        items=_five_board_candidate() + (_instrument(Board.SH_MAIN, "600002"),)
    )
    repository.save_instruments(existing)
    with pytest.raises(InstrumentSyncComparisonError):
        InstrumentMasterSyncService(
            FakeProvider(
                tuple(item for item in existing if item.symbol != "600002.SH")
            ),
            repository,
        ).sync(_apply_request())
    changed = [
        _instrument(Board.SH_MAIN, "600001", listing_date=date(2021, 1, 1))
        if item.symbol == "600001.SH"
        else item
        for item in existing
    ]
    with pytest.raises(InstrumentSyncComparisonError):
        InstrumentMasterSyncService(FakeProvider(tuple(changed)), repository).sync(
            _apply_request()
        )
    assert repository.load_instruments() == existing


def test_apply_rejects_valid_board_identity_change_without_replacing_master(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate(
        items=_five_board_candidate() + (_instrument(Board.SH_MAIN, "600002"),)
    )
    repository.save_instruments(existing)
    candidate = tuple(
        _instrument(Board.STAR, "600001")
        if item.symbol == "600001.SH"
        else _instrument(Board.SH_MAIN, "688001")
        if item.symbol == "688001.SH"
        else item
        for item in existing
    )
    with pytest.raises(
        InstrumentSyncComparisonError, match="exchange, board, or listing-date"
    ):
        InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
            _apply_request()
        )
    assert repository.load_instruments() == existing


def test_safe_metadata_updates_and_new_listings_are_allowed_and_repeatable(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    changed = [
        _instrument(Board.SH_MAIN, "600001", name="renamed", status=SecurityStatus.ST)
        if item.symbol == "600001.SH"
        else item
        for item in existing
    ]
    changed.append(_instrument(Board.SH_MAIN, "600002"))
    service = InstrumentMasterSyncService(FakeProvider(tuple(changed)), repository)
    first = service.sync(_apply_request())
    second = InstrumentMasterSyncService(FakeProvider(tuple(changed)), repository).sync(
        _apply_request()
    )
    assert (first.added_count, first.changed_metadata_count) == (1, 1)
    assert (
        second.added_count,
        second.removed_count,
        second.changed_metadata_count,
    ) == (0, 0, 0)


def test_storage_errors_are_reported_without_claiming_rollback(tmp_path: Any) -> None:
    class FailingRepository(LocalMarketRepository):
        def save_instruments(self, instruments: tuple[Instrument, ...]) -> None:
            raise StorageError("simulated catalog failure")

    repository = FailingRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    with pytest.raises(InstrumentSyncPersistenceError, match="could not be confirmed"):
        InstrumentMasterSyncService(
            FakeProvider(_five_board_candidate()), repository
        ).sync(_apply_request())


def test_pre_replace_parquet_failure_preserves_existing_master(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    candidate = _five_board_candidate(
        items=existing + (_instrument(Board.SH_MAIN, "600002"),)
    )
    original_write = repository._parquet.write_instruments

    def fail_before_replace(_: tuple[Instrument, ...]) -> None:
        raise StorageError("simulated pre-replace write failure")

    repository._parquet.write_instruments = fail_before_replace  # type: ignore[method-assign]
    try:
        with pytest.raises(
            InstrumentSyncPersistenceError, match="could not be confirmed"
        ):
            InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
                _apply_request()
            )
    finally:
        repository._parquet.write_instruments = original_write  # type: ignore[method-assign]
    assert repository.load_instruments() == existing


def test_catalog_refresh_after_replace_is_reported_as_uncertain(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    candidate = _five_board_candidate(
        items=existing + (_instrument(Board.SH_MAIN, "600002"),)
    )
    original_refresh = repository._catalog.refresh_views

    def fail_after_replace() -> None:
        raise StorageError("simulated catalog refresh failure")

    repository._catalog.refresh_views = fail_after_replace  # type: ignore[method-assign]
    with pytest.raises(InstrumentSyncPersistenceError, match="could not be confirmed"):
        InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
            _apply_request()
        )
    repository._catalog.refresh_views = original_refresh  # type: ignore[method-assign]
    assert repository.load_instruments() == candidate


def test_same_count_readback_metadata_mismatch_is_not_success(tmp_path: Any) -> None:
    class MismatchedReadbackRepository(LocalMarketRepository):
        def __init__(self, paths: AppPaths) -> None:
            super().__init__(paths)
            self._return_mismatch = False

        def save_instruments(self, instruments: tuple[Instrument, ...]) -> None:
            super().save_instruments(instruments)
            self._return_mismatch = True

        def load_instruments(self) -> tuple[Instrument, ...]:
            records = super().load_instruments()
            if not self._return_mismatch:
                return records
            changed = list(records)
            changed[0] = changed[0].model_copy(update={"name": "different-safe-name"})
            return tuple(changed)

    repository = MismatchedReadbackRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    candidate = _five_board_candidate()
    with pytest.raises(InstrumentSyncPersistenceError, match="did not match"):
        InstrumentMasterSyncService(FakeProvider(candidate), repository).sync(
            _apply_request()
        )


def test_malformed_provider_result_preserves_existing_master(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    existing = _five_board_candidate()
    repository.save_instruments(existing)
    malformed = cast(tuple[Instrument, ...], (object(),))
    with pytest.raises(
        InstrumentSyncValidationError, match="invalid instrument record"
    ):
        InstrumentMasterSyncService(FakeProvider(malformed), repository).sync(
            _apply_request()
        )
    assert repository.load_instruments() == existing
