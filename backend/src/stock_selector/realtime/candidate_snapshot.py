"""Pure candidate-to-capture join with explicit temporal and freshness gates."""

from datetime import datetime

from stock_selector.models import RealtimeQuote
from stock_selector.models.common import ensure_aware_datetime
from stock_selector.quality import DataQualityError, DataQualityEvaluator
from stock_selector.quality.models import RealtimeFreshness

from .errors import RealtimeDataError
from .models import (
    RealtimeCandidateResult,
    RealtimeCandidateSnapshotBlocker,
    RealtimeCandidateSnapshotDiagnostics,
    RealtimeCandidateSnapshotItem,
    RealtimeCandidateSnapshotResult,
    RealtimeCaptureResult,
)


class RealtimeCandidateSnapshotEngine:
    """Join an unchanged candidate pool to one supplied capture without I/O."""

    def build(
        self,
        candidates: RealtimeCandidateResult,
        capture: RealtimeCaptureResult | None,
        calculation_at: datetime,
        normal_max_seconds: int,
        warning_max_seconds: int,
    ) -> RealtimeCandidateSnapshotResult:
        """Build one deterministic official snapshot or a fully auditable empty state."""
        _validate_calculation_at(calculation_at)
        _validate_candidate_time(candidates, calculation_at)
        if capture is not None:
            _validate_capture(capture)
        freshness, age_seconds = _freshness(
            capture.ingested_at if capture is not None else None,
            calculation_at,
            normal_max_seconds,
            warning_max_seconds,
        )
        freshness_allowed = freshness in {
            RealtimeFreshness.FRESH,
            RealtimeFreshness.WARNING,
        }
        if not candidates.diagnostics.candidate_ready:
            return _result(
                candidates,
                capture,
                calculation_at,
                freshness,
                age_seconds,
                freshness_allowed,
                matched=0,
                missing=(),
                blockers=(RealtimeCandidateSnapshotBlocker.CANDIDATE_POOL_NOT_READY,),
                items=(),
            )
        if not candidates.candidates:
            return _result(
                candidates,
                capture,
                calculation_at,
                freshness,
                age_seconds,
                freshness_allowed,
                matched=0,
                missing=(),
                blockers=(),
                items=(),
            )
        if capture is None:
            return _result(
                candidates,
                None,
                calculation_at,
                freshness,
                age_seconds,
                freshness_allowed,
                matched=0,
                missing=tuple(sorted(candidate.symbol for candidate in candidates.candidates)),
                blockers=(
                    RealtimeCandidateSnapshotBlocker.REALTIME_SNAPSHOT_UNAVAILABLE,
                ),
                items=(),
            )
        if capture.ingested_at < candidates.as_of:
            raise RealtimeDataError("realtime capture must not predate candidate as_of")
        quotes = _index_quotes(capture)
        missing = tuple(
            sorted(
                candidate.symbol
                for candidate in candidates.candidates
                if candidate.symbol not in quotes
            )
        )
        matched = len(candidates.candidates) - len(missing)
        blockers: list[RealtimeCandidateSnapshotBlocker] = []
        if not freshness_allowed:
            blockers.append(RealtimeCandidateSnapshotBlocker.REALTIME_FRESHNESS_NOT_ALLOWED)
        if missing:
            blockers.append(
                RealtimeCandidateSnapshotBlocker.CANDIDATE_QUOTE_COVERAGE_INCOMPLETE
            )
        items = (
            tuple(
                RealtimeCandidateSnapshotItem(candidate=candidate, quote=quotes[candidate.symbol])
                for candidate in candidates.candidates
            )
            if not blockers
            else ()
        )
        return _result(
            candidates,
            capture,
            calculation_at,
            freshness,
            age_seconds,
            freshness_allowed,
            matched=matched,
            missing=missing,
            blockers=tuple(blockers),
            items=items,
        )


def _validate_candidate_time(
    candidates: RealtimeCandidateResult, calculation_at: datetime
) -> None:
    if candidates.as_of > calculation_at:
        raise RealtimeDataError("candidate as_of must not follow calculation_at")


def _validate_calculation_at(calculation_at: datetime) -> None:
    try:
        ensure_aware_datetime(calculation_at, "calculation_at")
    except ValueError as exc:
        raise RealtimeDataError("calculation_at must be timezone-aware") from exc


def _validate_capture(capture: RealtimeCaptureResult) -> None:
    quote_symbols = tuple(quote.symbol for quote in capture.quotes)
    if len(set(quote_symbols)) != len(quote_symbols):
        raise RealtimeDataError("realtime capture quotes must have unique symbols")
    if any(quote.ingested_at != capture.ingested_at for quote in capture.quotes):
        raise RealtimeDataError("realtime capture quote ingestion must match capture")
    if any(quote.source != capture.source for quote in capture.quotes):
        raise RealtimeDataError("realtime capture quote source must match capture")


def _freshness(
    ingested_at: datetime | None,
    calculation_at: datetime,
    normal_max_seconds: int,
    warning_max_seconds: int,
) -> tuple[RealtimeFreshness, float | None]:
    try:
        return DataQualityEvaluator().evaluate_freshness(
            ingested_at,
            calculation_at,
            normal_max_seconds,
            warning_max_seconds,
        )
    except DataQualityError as exc:
        raise RealtimeDataError("invalid realtime freshness input") from exc


def _index_quotes(capture: RealtimeCaptureResult) -> dict[str, RealtimeQuote]:
    return {quote.symbol: quote for quote in capture.quotes}


def _result(
    candidates: RealtimeCandidateResult,
    capture: RealtimeCaptureResult | None,
    calculation_at: datetime,
    freshness: RealtimeFreshness,
    age_seconds: float | None,
    freshness_allowed: bool,
    *,
    matched: int,
    missing: tuple[str, ...],
    blockers: tuple[RealtimeCandidateSnapshotBlocker, ...],
    items: tuple[RealtimeCandidateSnapshotItem, ...],
) -> RealtimeCandidateSnapshotResult:
    diagnostics = RealtimeCandidateSnapshotDiagnostics(
        calculation_at=calculation_at,
        candidate_as_of=candidates.as_of,
        candidate_ready=candidates.diagnostics.candidate_ready,
        candidate_members=len(candidates.candidates),
        capture_available=capture is not None,
        capture_scope=capture.scope if capture is not None else None,
        capture_source=capture.source if capture is not None else None,
        capture_ingested_at=capture.ingested_at if capture is not None else None,
        received_quotes=capture.received_quotes if capture is not None else 0,
        freshness=freshness,
        age_seconds=age_seconds,
        freshness_allowed=freshness_allowed,
        matched_candidate_quotes=matched,
        missing_candidate_quotes=len(missing),
        missing_candidate_symbols=missing,
        snapshot_ready=not blockers,
        blockers=blockers,
    )
    return RealtimeCandidateSnapshotResult(
        as_of=candidates.as_of,
        diagnostics=diagnostics,
        items=items,
    )
