"""Shared in-process and cross-process coordination for instrument-master writers."""

from __future__ import annotations

import errno
import importlib
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from stock_selector.storage.errors import StorageIOError


class InstrumentMasterLockBusyError(StorageIOError):
    """Raised when another writer owns the instrument-master lock."""


_REGISTRY_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_HELD_BY_THREAD = threading.local()


def instrument_master_lock_path(metadata_dir: Path) -> Path:
    """Return the persistent rendezvous path; existence never implies ownership."""
    return metadata_dir / "instrument_master.lock"


@contextmanager
def acquire_instrument_master_lock(
    lock_path: Path, *, timeout_seconds: float = 5.0
) -> Iterator[None]:
    """Exclusively coordinate one complete master-writing workflow.

    The lock file persists after release and contains no ownership metadata. Its parent
    is created only when this write-authorized acquisition path is entered.
    """
    if timeout_seconds < 0:
        raise ValueError("instrument-master lock timeout must be non-negative")
    deadline = time.monotonic() + timeout_seconds
    resolved = lock_path.resolve()
    thread_lock = _thread_lock_for(resolved)
    if not thread_lock.acquire(timeout=_remaining_seconds(deadline)):
        raise InstrumentMasterLockBusyError("instrument-master writer lock is busy")
    held = _held_locks()
    try:
        current = held.get(resolved)
        if current is not None:
            held[resolved] = (current[0] + 1, current[1])
            try:
                yield
            finally:
                depth, handle = held[resolved]
                held[resolved] = (depth - 1, handle)
            return

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            handle = resolved.open("a+b")
        except OSError as exc:
            raise StorageIOError(
                f"failed to open instrument-master writer lock: {resolved}"
            ) from exc
        try:
            _ensure_lock_byte(handle)
            _acquire_os_lock(handle, deadline)
            held[resolved] = (1, handle)
            try:
                yield
            finally:
                held.pop(resolved, None)
                _release_os_lock(handle)
        finally:
            handle.close()
    finally:
        thread_lock.release()


def _thread_lock_for(path: Path) -> threading.RLock:
    with _REGISTRY_GUARD:
        return _THREAD_LOCKS.setdefault(path, threading.RLock())


def _held_locks() -> dict[Path, tuple[int, BinaryIO]]:
    held = getattr(_HELD_BY_THREAD, "locks", None)
    if held is None:
        held = {}
        _HELD_BY_THREAD.locks = held
    return held


def _ensure_lock_byte(handle: BinaryIO) -> None:
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
    except OSError as exc:
        raise StorageIOError("failed to initialize instrument-master writer lock") from exc


def _acquire_os_lock(handle: BinaryIO, deadline: float) -> None:
    while True:
        try:
            _try_os_lock(handle)
            return
        except OSError as exc:
            if not _is_lock_contention(exc):
                raise StorageIOError(
                    "failed to acquire instrument-master writer lock"
                ) from exc
            if time.monotonic() >= deadline:
                raise InstrumentMasterLockBusyError(
                    "instrument-master writer lock is busy"
                ) from exc
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _try_os_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    fcntl: Any = importlib.import_module("fcntl")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_os_lock(handle: BinaryIO) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl: Any = importlib.import_module("fcntl")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise StorageIOError("failed to release instrument-master writer lock") from exc


def _is_lock_contention(exc: OSError) -> bool:
    return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or getattr(
        exc, "winerror", None
    ) in {33, 36}
