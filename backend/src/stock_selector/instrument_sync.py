"""Explicit, guarded synchronization of the local instrument master."""

from collections import Counter
from dataclasses import dataclass

from stock_selector.models import Board, Instrument
from stock_selector.providers.base import InstrumentProvider
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.storage.instrument_master_lock import (
    InstrumentMasterLockBusyError,
)

SUPPORTED_BOARDS = (
    Board.SH_MAIN,
    Board.SZ_MAIN,
    Board.CHINEXT,
    Board.STAR,
    Board.BSE,
)


class InstrumentSyncError(Exception):
    """Base error for a finite, operator-visible instrument-master sync."""


class InstrumentSyncValidationError(InstrumentSyncError):
    """Raised before a candidate is eligible for persistence."""


class InstrumentSyncComparisonError(InstrumentSyncError):
    """Raised when a candidate would silently alter stored identity coverage."""


class InstrumentSyncPersistenceError(InstrumentSyncError):
    """Raised when persistence or its mandatory readback cannot be confirmed."""


class InstrumentSyncBusyError(InstrumentSyncError):
    """Raised when another writer owns the instrument-master lock."""


@dataclass(frozen=True)
class InstrumentSyncRequest:
    """Operator intent and explicit completeness safeguards for one sync."""

    apply: bool = False
    expected_min_total: int | None = None
    expected_min_boards: dict[Board, int] | None = None

    def validate_usage(self) -> None:
        """Reject deterministic invalid APPLY usage before provider construction."""
        if not self.apply:
            return
        if self.expected_min_total is None or self.expected_min_total <= 0:
            raise InstrumentSyncValidationError(
                "--apply requires a positive --expected-min-total"
            )
        board_floors = self.expected_min_boards or {}
        missing = [
            board.value for board in SUPPORTED_BOARDS if board not in board_floors
        ]
        if missing:
            raise InstrumentSyncValidationError(
                "--apply requires one positive --expected-min-board for every supported board"
            )
        if set(board_floors) != set(SUPPORTED_BOARDS) or any(
            count <= 0 for count in board_floors.values()
        ):
            raise InstrumentSyncValidationError(
                "--expected-min-board values must be positive supported-board floors"
            )


@dataclass(frozen=True)
class InstrumentSyncReport:
    """Safe summary of one preview or apply operation."""

    mode: str
    provider: str
    candidate_total: int
    effective_candidate_total: int
    existing_total: int
    candidate_board_counts: dict[Board, int]
    effective_candidate_board_counts: dict[Board, int]
    existing_board_counts: dict[Board, int]
    added_count: int
    removed_count: int
    provider_missing_count: int
    retained_historical_count: int
    retained_historical_symbols: tuple[str, ...]
    blocked_removal_count: int
    blocked_removal_symbols: tuple[str, ...]
    lifecycle_preserved_count: int
    lifecycle_preserved_symbols: tuple[str, ...]
    lifecycle_conflict_count: int
    lifecycle_conflict_symbols: tuple[str, ...]
    changed_metadata_count: int
    persistence_performed: bool
    readback_verified: bool
    parquet_readback_verified: bool
    catalog_readback_verified: bool

    @property
    def provider_candidate_total(self) -> int:
        """Expose the legacy candidate total with explicit raw-provider semantics."""
        return self.candidate_total

    @property
    def provider_candidate_board_counts(self) -> dict[Board, int]:
        """Expose legacy candidate board counts as raw-provider coverage."""
        return self.candidate_board_counts


class InstrumentMasterSyncService:
    """Fetch once, validate, compare, and optionally replace only the master file."""

    def __init__(
        self, provider: InstrumentProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def sync(self, request: InstrumentSyncRequest) -> InstrumentSyncReport:
        request.validate_usage()
        provider_candidate = _validate_candidate(
            self._provider.get_instruments(), request
        )
        if request.apply:
            try:
                with self._repository.instrument_master_writer():
                    existing = self._repository.load_instruments()
                    merged = _merge_with_retained_history(
                        existing, provider_candidate
                    )
                    comparison = _compare(existing, merged.effective_candidate)
                    _require_preservation(comparison, merged)
                    self._repository.save_instruments(merged.effective_candidate)
                    parquet_verified = (
                        self._repository.load_instruments()
                        == merged.effective_candidate
                    )
                    catalog_verified = self._repository.catalog_instruments_match(
                        merged.effective_candidate
                    )
            except InstrumentMasterLockBusyError as exc:
                raise InstrumentSyncBusyError(
                    "instrument-master writer is busy; no master write was attempted"
                ) from exc
            except StorageError as exc:
                raise InstrumentSyncPersistenceError(
                    "instrument-master persistence could not be confirmed; inspect local master and catalog before retrying"
                ) from exc
            if not parquet_verified or not catalog_verified:
                raise InstrumentSyncPersistenceError(
                    "instrument-master readback did not match the approved candidate; inspect local master and catalog"
                )
            return _report(
                request,
                self._provider.info.name,
                provider_candidate,
                existing,
                merged,
                comparison,
                parquet_verified=True,
                catalog_verified=True,
            )

        existing = self._repository.load_instruments()
        merged = _merge_with_retained_history(existing, provider_candidate)
        comparison = _compare(existing, merged.effective_candidate)
        return _report(
            request,
            self._provider.info.name,
            provider_candidate,
            existing,
            merged,
            comparison,
            parquet_verified=False,
            catalog_verified=False,
        )


def _report(
    request: InstrumentSyncRequest,
    provider: str,
    provider_candidate: tuple[Instrument, ...],
    existing: tuple[Instrument, ...],
    merged: "_MergeResult",
    comparison: "_Comparison",
    *,
    parquet_verified: bool,
    catalog_verified: bool,
) -> InstrumentSyncReport:
    return InstrumentSyncReport(
            mode="apply" if request.apply else "preview",
            provider=provider,
            candidate_total=len(provider_candidate),
            effective_candidate_total=len(merged.effective_candidate),
            existing_total=len(existing),
            candidate_board_counts=_board_counts(provider_candidate),
            effective_candidate_board_counts=_board_counts(
                merged.effective_candidate
            ),
            existing_board_counts=_board_counts(existing),
            added_count=len(comparison.added),
            removed_count=len(comparison.removed),
            provider_missing_count=len(merged.provider_missing),
            retained_historical_count=len(merged.retained_historical),
            retained_historical_symbols=merged.retained_historical,
            blocked_removal_count=len(merged.blocked_removals),
            blocked_removal_symbols=merged.blocked_removals,
            lifecycle_preserved_count=len(merged.lifecycle_preserved),
            lifecycle_preserved_symbols=merged.lifecycle_preserved,
            lifecycle_conflict_count=len(merged.lifecycle_conflicts),
            lifecycle_conflict_symbols=merged.lifecycle_conflicts,
            changed_metadata_count=len(comparison.metadata_changed),
            persistence_performed=request.apply,
            readback_verified=parquet_verified and catalog_verified,
            parquet_readback_verified=parquet_verified,
            catalog_readback_verified=catalog_verified,
        )


@dataclass(frozen=True)
class _MergeResult:
    effective_candidate: tuple[Instrument, ...]
    provider_missing: tuple[str, ...]
    retained_historical: tuple[str, ...]
    blocked_removals: tuple[str, ...]
    lifecycle_preserved: tuple[str, ...]
    lifecycle_conflicts: tuple[str, ...]


def _merge_with_retained_history(
    existing: tuple[Instrument, ...], provider_candidate: tuple[Instrument, ...]
) -> _MergeResult:
    old = {item.symbol: item for item in existing}
    provider = {item.symbol: item for item in provider_candidate}
    effective = dict(provider)
    shared = tuple(sorted(old.keys() & provider.keys()))
    lifecycle_preserved = tuple(
        symbol
        for symbol in shared
        if old[symbol].delisting_date is not None
        and provider[symbol].delisting_date is None
    )
    for symbol in lifecycle_preserved:
        effective[symbol] = provider[symbol].model_copy(
            update={"delisting_date": old[symbol].delisting_date}
        )

    shared_conflicts = tuple(
        symbol
        for symbol in shared
        if (
            old[symbol].delisting_date is None
            and provider[symbol].delisting_date is not None
        )
        or (
            old[symbol].delisting_date is not None
            and provider[symbol].delisting_date is not None
            and old[symbol].delisting_date != provider[symbol].delisting_date
        )
    )
    new_dated = tuple(
        sorted(
            symbol
            for symbol in provider.keys() - old.keys()
            if provider[symbol].delisting_date is not None
        )
    )
    provider_missing = tuple(sorted(old.keys() - provider.keys()))
    retained_historical = tuple(
        symbol
        for symbol in provider_missing
        if old[symbol].delisting_date is not None
    )
    blocked_removals = tuple(
        symbol
        for symbol in provider_missing
        if old[symbol].delisting_date is None
    )
    for symbol in retained_historical:
        effective[symbol] = old[symbol]
    return _MergeResult(
        effective_candidate=tuple(effective[symbol] for symbol in sorted(effective)),
        provider_missing=provider_missing,
        retained_historical=retained_historical,
        blocked_removals=blocked_removals,
        lifecycle_preserved=lifecycle_preserved,
        lifecycle_conflicts=tuple(sorted((*shared_conflicts, *new_dated))),
    )


@dataclass(frozen=True)
class _Comparison:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    metadata_changed: tuple[str, ...]
    identity_changed: tuple[str, ...]
    board_shrunk: tuple[Board, ...]


def _validate_candidate(
    instruments: tuple[Instrument, ...], request: InstrumentSyncRequest
) -> tuple[Instrument, ...]:
    if not instruments:
        raise InstrumentSyncValidationError(
            "provider returned an empty instrument snapshot"
        )
    if any(not isinstance(item, Instrument) for item in instruments):
        raise InstrumentSyncValidationError(
            "provider returned an invalid instrument record"
        )
    # Rebuild domain records to keep the boundary explicit if a provider supplied models.
    try:
        normalized = tuple(
            Instrument.model_validate(item.model_dump()) for item in instruments
        )
    except ValueError as exc:
        raise InstrumentSyncValidationError(
            "provider returned an invalid instrument record"
        ) from exc
    symbols = tuple(item.symbol for item in normalized)
    if len(set(symbols)) != len(symbols):
        raise InstrumentSyncValidationError(
            "provider returned duplicate canonical symbols"
        )
    ordered = tuple(sorted(normalized, key=lambda item: item.symbol))
    board_counts = _board_counts(ordered)
    missing = [board.value for board in SUPPORTED_BOARDS if board_counts[board] == 0]
    if missing:
        raise InstrumentSyncValidationError(
            "provider snapshot is missing supported board coverage: "
            + ", ".join(missing)
        )
    if request.apply:
        assert request.expected_min_total is not None
        if len(ordered) < request.expected_min_total:
            raise InstrumentSyncValidationError(
                "candidate total is below --expected-min-total"
            )
        for board, minimum in (request.expected_min_boards or {}).items():
            if board_counts[board] < minimum:
                raise InstrumentSyncValidationError(
                    f"candidate {board.value} count is below its operator minimum"
                )
    return ordered


def _compare(
    existing: tuple[Instrument, ...], candidate: tuple[Instrument, ...]
) -> _Comparison:
    old = {item.symbol: item for item in existing}
    new = {item.symbol: item for item in candidate}
    shared = tuple(sorted(old.keys() & new.keys()))
    identity_changed = tuple(
        symbol
        for symbol in shared
        if (old[symbol].exchange, old[symbol].board, old[symbol].listing_date)
        != (new[symbol].exchange, new[symbol].board, new[symbol].listing_date)
    )
    metadata_changed = tuple(symbol for symbol in shared if old[symbol] != new[symbol])
    old_counts, new_counts = _board_counts(existing), _board_counts(candidate)
    return _Comparison(
        added=tuple(sorted(new.keys() - old.keys())),
        removed=tuple(sorted(old.keys() - new.keys())),
        metadata_changed=metadata_changed,
        identity_changed=identity_changed,
        board_shrunk=tuple(
            board for board in SUPPORTED_BOARDS if new_counts[board] < old_counts[board]
        ),
    )


def _require_preservation(
    comparison: _Comparison, merged: _MergeResult
) -> None:
    if merged.lifecycle_conflicts:
        raise InstrumentSyncComparisonError(
            "ordinary sync cannot establish or change delisting lifecycle metadata"
        )
    if comparison.removed:
        raise InstrumentSyncComparisonError(
            "candidate would remove existing instrument symbols"
        )
    if comparison.board_shrunk:
        raise InstrumentSyncComparisonError(
            "candidate would shrink existing board coverage"
        )
    if comparison.identity_changed:
        raise InstrumentSyncComparisonError(
            "candidate changes existing exchange, board, or listing-date identity"
        )


def _board_counts(instruments: tuple[Instrument, ...]) -> dict[Board, int]:
    counts = Counter(item.board for item in instruments)
    return {board: counts[board] for board in SUPPORTED_BOARDS}
