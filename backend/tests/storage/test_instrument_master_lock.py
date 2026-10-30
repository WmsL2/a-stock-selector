"""Process, thread, and reentrancy contracts for the master writer lock."""

from __future__ import annotations

import errno
import multiprocessing
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import stock_selector.storage.instrument_master_lock as lock_module
from stock_selector.config import AppPaths
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.storage import LocalMarketRepository
from stock_selector.storage.instrument_master_lock import (
    InstrumentMasterLockBusyError,
    acquire_instrument_master_lock,
)


def _hold_process_lock(lock_path: str, ready: Any, release: Any) -> None:
    with acquire_instrument_master_lock(Path(lock_path), timeout_seconds=2.0):
        ready.set()
        release.wait(10.0)


def _instrument(name: str = "original") -> Instrument:
    return Instrument(
        symbol="600519.SH",
        name=name,
        exchange=Exchange.SSE,
        board=Board.SH_MAIN,
        listing_date=date(2001, 8, 27),
    )


def _repository(tmp_path: Path) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def test_independent_processes_cannot_hold_writer_lock_together(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    lock_path = tmp_path / "metadata" / "instrument_master.lock"
    process = context.Process(
        target=_hold_process_lock,
        args=(str(lock_path), ready, release),
    )
    process.start()
    try:
        assert ready.wait(10.0)
        with (
            pytest.raises(InstrumentMasterLockBusyError, match="busy"),
            acquire_instrument_master_lock(lock_path, timeout_seconds=0),
        ):
            pytest.fail("contending process acquired the writer lock")
    finally:
        release.set()
        process.join(10.0)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
    assert process.exitcode == 0


def test_threads_serialize_and_exception_releases_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "metadata" / "instrument_master.lock"
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()

    def first() -> None:
        with acquire_instrument_master_lock(lock_path, timeout_seconds=2.0):
            first_acquired.set()
            release_first.wait(5.0)

    def second() -> None:
        with acquire_instrument_master_lock(lock_path, timeout_seconds=2.0):
            second_acquired.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    assert first_acquired.wait(5.0)
    second_thread.start()
    assert not second_acquired.wait(0.1)
    release_first.set()
    assert second_acquired.wait(5.0)
    first_thread.join(5.0)
    second_thread.join(5.0)

    with (
        pytest.raises(RuntimeError, match="simulated"),
        acquire_instrument_master_lock(lock_path, timeout_seconds=0),
    ):
        raise RuntimeError("simulated")
    with acquire_instrument_master_lock(lock_path, timeout_seconds=0):
        pass


def test_stale_path_is_not_ownership_and_nested_repository_lock_is_reentrant(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    lock_path = repository.instrument_master_lock_path
    lock_path.write_bytes(b"stale-not-ownership")

    with repository.instrument_master_writer(timeout_seconds=0):
        repository.save_instruments((_instrument(),))

    assert repository.load_instruments() == (_instrument(),)
    assert lock_path.exists()


def test_contention_performs_no_master_persistence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.save_instruments((_instrument(),))
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_process_lock,
        args=(str(repository.instrument_master_lock_path), ready, release),
    )
    process.start()
    try:
        assert ready.wait(10.0)
        with (
            pytest.raises(InstrumentMasterLockBusyError),
            repository.instrument_master_writer(timeout_seconds=0),
        ):
            repository.save_instruments((_instrument("changed"),))
        assert repository.load_instruments() == (_instrument(),)
    finally:
        release.set()
        process.join(10.0)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
    assert process.exitcode == 0


def test_one_deadline_covers_thread_and_os_lock_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [100.0]
    thread_timeouts: list[float] = []

    class AdvancingThreadLock:
        def acquire(self, *, timeout: float) -> bool:
            thread_timeouts.append(timeout)
            clock[0] += 0.75
            return True

        def release(self) -> None:
            pass

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    def contend(_: object) -> None:
        raise OSError(errno.EACCES, "simulated contention")

    monkeypatch.setattr(lock_module, "_thread_lock_for", lambda _: AdvancingThreadLock())
    monkeypatch.setattr(lock_module.time, "monotonic", monotonic)
    monkeypatch.setattr(lock_module.time, "sleep", sleep)
    monkeypatch.setattr(lock_module, "_try_os_lock", contend)

    with (
        pytest.raises(InstrumentMasterLockBusyError),
        acquire_instrument_master_lock(
            tmp_path / "metadata" / "instrument_master.lock",
            timeout_seconds=1.0,
        ),
    ):
        pytest.fail("contended OS lock unexpectedly acquired")

    assert thread_timeouts == [1.0]
    assert clock[0] == pytest.approx(101.0)
