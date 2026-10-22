"""Explicit, guarded synchronization of the local instrument master."""

from collections import Counter
from dataclasses import dataclass

from stock_selector.models import Board, Instrument
from stock_selector.providers.base import InstrumentProvider
from stock_selector.storage import LocalMarketRepository, StorageError

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
    existing_total: int
    candidate_board_counts: dict[Board, int]
    existing_board_counts: dict[Board, int]
    added_count: int
    removed_count: int
    changed_metadata_count: int
    persistence_performed: bool
    readback_verified: bool


class InstrumentMasterSyncService:
    """Fetch once, validate, compare, and optionally replace only the master file."""

    def __init__(
        self, provider: InstrumentProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def sync(self, request: InstrumentSyncRequest) -> InstrumentSyncReport:
        request.validate_usage()
        candidate = _validate_candidate(self._provider.get_instruments(), request)
        existing = self._repository.load_instruments()
        comparison = _compare(existing, candidate)
        if request.apply:
            _require_preservation(comparison)
            try:
                self._repository.save_instruments(candidate)
                readback = self._repository.load_instruments()
            except StorageError as exc:
                raise InstrumentSyncPersistenceError(
                    "instrument-master persistence could not be confirmed; inspect local master and catalog before retrying"
                ) from exc
            if readback != candidate:
                raise InstrumentSyncPersistenceError(
                    "instrument-master readback did not match the approved candidate; inspect local master and catalog"
                )
        return InstrumentSyncReport(
            mode="apply" if request.apply else "preview",
            provider=self._provider.info.name,
            candidate_total=len(candidate),
            existing_total=len(existing),
            candidate_board_counts=_board_counts(candidate),
            existing_board_counts=_board_counts(existing),
            added_count=len(comparison.added),
            removed_count=len(comparison.removed),
            changed_metadata_count=len(comparison.metadata_changed),
            persistence_performed=request.apply,
            readback_verified=request.apply,
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


def _require_preservation(comparison: _Comparison) -> None:
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
