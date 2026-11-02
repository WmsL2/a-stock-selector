"""Explicit offline lifecycle repair; apply is restricted to isolated test roots.

Boundaries are inclusive calendar dates, not claims about last actual trading.
Evidence references are operator assertions, not automatically verified sources.
Preview is deterministic but neither an approval nor a concurrent snapshot.
"""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from stock_selector.config.paths import AppPaths
from stock_selector.models import Instrument
from stock_selector.models.common import validate_symbol
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.storage.instrument_master_lock import InstrumentMasterLockBusyError


class LifecycleRepairError(Exception):
    """Finite lifecycle repair failure with no implicit retry or recovery."""


class LifecycleRepairValidationError(LifecycleRepairError):
    """Invalid intent, evidence, baseline, or lifecycle state."""

    def __init__(
        self, message: str, report: "LifecycleRepairReport | None" = None
    ) -> None:
        super().__init__(message)
        self.report = report


class LifecycleRepairBusyError(LifecycleRepairError):
    """The shared writer lock could not be acquired before persistence."""


class LifecycleRepairPersistenceError(LifecycleRepairError):
    """Storage failure; persistence is uncertain once save has been entered."""

    def __init__(self, message: str, *, persistence_uncertain: bool) -> None:
        super().__init__(message)
        self.persistence_uncertain = persistence_uncertain


@dataclass(frozen=True)
class LifecycleRepairEntry:
    """One explicit inclusive boundary, evidence basis, and compare-and-set value."""

    symbol: str
    delisting_date: date
    evidence_reference: str
    operator_reason: str
    expected_previous: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str):
            raise LifecycleRepairValidationError("invalid canonical symbol")
        try:
            validate_symbol(self.symbol)
        except ValueError as exc:
            raise LifecycleRepairValidationError("invalid canonical symbol") from exc
        if not re.fullmatch(r"[0-9]{6}\.(?:SH|SZ|BJ)", self.symbol):
            raise LifecycleRepairValidationError(
                "canonical symbols require ASCII digits"
            )
        if type(self.delisting_date) is not date or (
            self.expected_previous is not None
            and type(self.expected_previous) is not date
        ):
            raise LifecycleRepairValidationError(
                "lifecycle values must be date objects"
            )
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.evidence_reference, self.operator_reason)
        ):
            raise LifecycleRepairValidationError(
                "evidence reference and reason required"
            )


@dataclass(frozen=True)
class LifecycleRepairRequest:
    """Explicit entries only; no symbol discovery or date normalization."""

    entries: tuple[LifecycleRepairEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not self.entries:
            raise LifecycleRepairValidationError("nonempty immutable entries required")
        if any(not isinstance(entry, LifecycleRepairEntry) for entry in self.entries):
            raise LifecycleRepairValidationError("invalid repair entry")
        symbols = [entry.symbol for entry in self.entries]
        if len(set(symbols)) != len(symbols):
            raise LifecycleRepairValidationError("duplicate repair symbols")


@dataclass(frozen=True)
class LifecycleRepairChange:
    """Audit evidence for one symbol, including explicit validation issues."""

    entry: LifecycleRepairEntry
    previous: date | None
    outcome: str


@dataclass(frozen=True)
class LifecycleRepairReport:
    """Deterministic canonical report; rejected reports accompany exceptions."""

    mode: str
    master_fingerprint: str
    existing_master_rows: int
    requested_count: int
    changed_count: int
    already_correct_count: int
    preserved_historical_rows: int
    unknown_symbols: tuple[str, ...]
    conflicting_symbols: tuple[str, ...]
    changes: tuple[LifecycleRepairChange, ...]
    validation_status: str
    persistence_performed: bool = False
    parquet_readback_verified: bool = False
    catalog_readback_verified: bool = False


def master_fingerprint(instruments: tuple[Instrument, ...]) -> str:
    """SHA-256 of all fields, sorted by exact symbol, using versioned UTF-8 JSON.

    This is a logical baseline, not a physical-file or approval digest. Its hash
    does not provide concurrency protection; apply must hold the shared lock.
    """
    ordered = _validated_master(instruments)
    payload = {
        "contract": "lifecycle-master-v1",
        "rows": [item.model_dump(mode="json") for item in ordered],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InstrumentLifecycleRepairService:
    """Use a caller-opened repository; never initialize storage or call providers."""

    def __init__(self, repository: LocalMarketRepository) -> None:
        self._repository = repository

    def preview(self, request: LifecycleRepairRequest) -> LifecycleRepairReport:
        """Read the entire master without acquiring a writer lock or persisting."""
        report, _ = _plan(self._repository.load_instruments(), request, "preview")
        return report

    def apply_for_testing(
        self,
        request: LifecycleRepairRequest,
        *,
        operator_approved: bool,
        expected_master_fingerprint: str,
        isolated_project_root: Path,
        timeout_seconds: float = 5.0,
    ) -> LifecycleRepairReport:
        """Apply only in an explicitly supplied isolated synthetic repository.

        The caller must create/initialize its own synthetic AppPaths. A fresh
        fingerprint is required even for a fully idempotent reapplication.
        Expected previous values gate changes; an already-equal date is an
        explicit no-op and never a lifecycle overwrite. No production apply API exists.
        """
        if operator_approved is not True:
            raise LifecycleRepairValidationError("explicit operator approval required")
        if not isinstance(expected_master_fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_master_fingerprint
        ):
            raise LifecycleRepairValidationError("expected master fingerprint required")
        self._require_isolated_root(isolated_project_root)
        persistence_started = False
        try:
            with self._repository.instrument_master_writer(
                timeout_seconds=timeout_seconds
            ):
                current = self._repository.load_instruments()
                report, replacement = _plan(current, request, "apply_for_testing")
                if report.master_fingerprint != expected_master_fingerprint:
                    raise LifecycleRepairValidationError(
                        "stale master fingerprint", report
                    )
                if report.changed_count:
                    persistence_started = True
                    self._repository.save_instruments(replacement)
                if self._repository.load_instruments() != replacement:
                    raise StorageError("complete Parquet readback mismatch")
                if not self._repository.catalog_instruments_match(replacement):
                    raise StorageError("complete DuckDB catalog readback mismatch")
                report = replace(
                    report,
                    persistence_performed=persistence_started,
                    parquet_readback_verified=True,
                    catalog_readback_verified=True,
                )
            return report
        except InstrumentMasterLockBusyError as exc:
            if persistence_started:
                raise LifecycleRepairPersistenceError(
                    "persistence uncertain; inspect master and catalog before recovery",
                    persistence_uncertain=True,
                ) from exc
            raise LifecycleRepairBusyError("writer busy; no save attempted") from exc
        except (StorageError, OSError) as exc:
            raise LifecycleRepairPersistenceError(
                "persistence uncertain; inspect master and catalog before recovery"
                if persistence_started
                else "storage check failed; no save attempted",
                persistence_uncertain=persistence_started,
            ) from exc

    def _require_isolated_root(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise LifecycleRepairValidationError(
                "explicit isolated project root required"
            )
        resolved = root.resolve()
        production = AppPaths.from_project_root().runtime_dir.resolve()
        paths = self._repository.paths
        if resolved == AppPaths.from_project_root().project_root.resolve():
            raise LifecycleRepairValidationError("production apply is disabled")
        locations = (
            paths.runtime_dir,
            paths.processed_data_dir,
            paths.metadata_dir,
            paths.processed_data_dir / "instruments" / "instruments.parquet",
            self._repository.catalog_path,
            self._repository.instrument_master_lock_path,
        )
        if paths.project_root.resolve() != resolved or any(
            not location.resolve().is_relative_to(resolved)
            or location.resolve().is_relative_to(production)
            for location in locations
        ):
            raise LifecycleRepairValidationError(
                "repository is not isolated from production"
            )


def _validated_master(instruments: tuple[Instrument, ...]) -> tuple[Instrument, ...]:
    if any(not isinstance(item, Instrument) for item in instruments):
        raise LifecycleRepairValidationError("invalid master record")
    if len({item.symbol for item in instruments}) != len(instruments):
        raise LifecycleRepairValidationError("duplicate master symbols")
    try:
        validated = tuple(
            Instrument.model_validate(item.model_dump()) for item in instruments
        )
    except ValueError as exc:
        raise LifecycleRepairValidationError("invalid master domain record") from exc
    if validated != instruments:
        raise LifecycleRepairValidationError(
            "master domain validation would change metadata"
        )
    return tuple(sorted(validated, key=lambda item: item.symbol))


def _plan(
    instruments: tuple[Instrument, ...],
    request: LifecycleRepairRequest,
    mode: str,
) -> tuple[LifecycleRepairReport, tuple[Instrument, ...]]:
    if not isinstance(request, LifecycleRepairRequest):
        raise LifecycleRepairValidationError("typed lifecycle repair request required")
    # Recheck explicit intent at the service boundary as well as construction.
    request.__post_init__()
    for entry in request.entries:
        entry.__post_init__()
    current = _validated_master(instruments)
    existing = {item.symbol: item for item in current}
    replacement = dict(existing)
    changes: list[LifecycleRepairChange] = []
    unknown: list[str] = []
    conflicts: list[str] = []
    for entry in sorted(request.entries, key=lambda value: value.symbol):
        item = existing.get(entry.symbol)
        outcome = "change"
        if item is None:
            outcome = "unknown_symbol"
            unknown.append(entry.symbol)
        elif item.delisting_date == entry.delisting_date:
            outcome = "already_correct"
        elif item.delisting_date != entry.expected_previous:
            outcome = "unexpected_previous"
        elif item.delisting_date is not None:
            outcome = "conflicting_existing_date"
        elif entry.delisting_date < item.listing_date:
            outcome = "before_listing_date"
        else:
            values = item.model_dump()
            values["delisting_date"] = entry.delisting_date
            replacement[item.symbol] = Instrument.model_validate(values)
        if outcome not in {"change", "already_correct", "unknown_symbol"}:
            conflicts.append(entry.symbol)
        changes.append(
            LifecycleRepairChange(
                entry,
                item.delisting_date if item is not None else None,
                outcome,
            )
        )
    report = LifecycleRepairReport(
        mode=mode,
        master_fingerprint=master_fingerprint(current),
        existing_master_rows=len(current),
        requested_count=len(request.entries),
        changed_count=sum(change.outcome == "change" for change in changes),
        already_correct_count=sum(
            change.outcome == "already_correct" for change in changes
        ),
        preserved_historical_rows=len(current),
        unknown_symbols=tuple(unknown),
        conflicting_symbols=tuple(conflicts),
        changes=tuple(changes),
        validation_status="rejected" if unknown or conflicts else "valid",
    )
    if unknown or conflicts:
        raise LifecycleRepairValidationError("lifecycle validation rejected", report)
    return report, tuple(replacement[symbol] for symbol in sorted(replacement))
