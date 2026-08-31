"""Task 16 contracts for the pure candidate-to-capture snapshot join."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from stock_selector.models import RealtimeQuote
from stock_selector.quality.models import RealtimeFreshness
from stock_selector.realtime import (
    RealtimeCandidate,
    RealtimeCandidateBlocker,
    RealtimeCandidateDiagnostics,
    RealtimeCandidatePolicy,
    RealtimeCandidateResult,
    RealtimeCandidateSnapshotBlocker,
    RealtimeCandidateSnapshotEngine,
    RealtimeCandidateSnapshotItem,
    RealtimeCaptureResult,
    RealtimeCaptureScope,
    RealtimeDataError,
)

AS_OF = datetime(2026, 8, 31, 9, tzinfo=UTC)


def test_all_market_join_preserves_candidate_rank_and_ignores_extra_quotes() -> None:
    candidates = _candidate_result("000002.SZ", "000001.SZ", "600519.SH")
    capture = _capture(
        _quote("000001.SZ", change_pct=99, turnover_rate=99),
        _quote("000002.SZ", change_pct=-99, turnover_rate=0),
        _quote("600519.SH", change_pct=0, turnover_rate=1),
        _quote("000003.SZ"),
    )
    result = _build(candidates, capture, AS_OF + timedelta(seconds=30))
    assert result.diagnostics.snapshot_ready is True
    assert tuple(item.candidate.symbol for item in result.items) == (
        "000002.SZ",
        "000001.SZ",
        "600519.SH",
    )
    assert result.diagnostics.matched_candidate_quotes == 3
    assert result.diagnostics.missing_candidate_symbols == ()


def test_explicit_symbol_capture_is_valid_when_it_covers_every_candidate() -> None:
    candidates = _candidate_result("000001.SZ", "000002.SZ")
    capture = _capture(
        _quote("000001.SZ"),
        _quote("000002.SZ"),
        scope=RealtimeCaptureScope.EXPLICIT_SYMBOLS,
    )
    result = _build(candidates, capture, AS_OF + timedelta(seconds=60))
    assert result.diagnostics.capture_scope is RealtimeCaptureScope.EXPLICIT_SYMBOLS
    assert result.diagnostics.snapshot_ready is True


def test_candidate_pool_not_ready_is_the_only_blocker() -> None:
    result = _build(
        _candidate_result(ready=False),
        _capture(_quote("000001.SZ")),
        AS_OF + timedelta(seconds=30),
    )
    assert result.items == ()
    assert result.diagnostics.blockers == (
        RealtimeCandidateSnapshotBlocker.CANDIDATE_POOL_NOT_READY,
    )


def test_ready_empty_pool_needs_no_capture() -> None:
    result = _build(_candidate_result(), None, AS_OF + timedelta(seconds=30))
    assert result.diagnostics.snapshot_ready is True
    assert result.diagnostics.freshness is RealtimeFreshness.UNAVAILABLE
    assert result.diagnostics.blockers == ()
    assert result.items == ()


def test_nonempty_pool_without_capture_is_blocked() -> None:
    result = _build(
        _candidate_result("000001.SZ"), None, AS_OF + timedelta(seconds=30)
    )
    assert result.items == ()
    assert result.diagnostics.missing_candidate_symbols == ("000001.SZ",)
    assert result.diagnostics.blockers == (
        RealtimeCandidateSnapshotBlocker.REALTIME_SNAPSHOT_UNAVAILABLE,
    )


def test_incomplete_candidate_quote_coverage_never_leaks_partial_items() -> None:
    result = _build(
        _candidate_result("000001.SZ", "000002.SZ", "000003.SZ"),
        _capture(_quote("000001.SZ"), _quote("000003.SZ")),
        AS_OF + timedelta(seconds=30),
    )
    assert result.diagnostics.snapshot_ready is False
    assert result.items == ()
    assert result.diagnostics.matched_candidate_quotes == 2
    assert result.diagnostics.missing_candidate_quotes == 1
    assert result.diagnostics.missing_candidate_symbols == ("000002.SZ",)
    assert result.diagnostics.blockers == (
        RealtimeCandidateSnapshotBlocker.CANDIDATE_QUOTE_COVERAGE_INCOMPLETE,
    )


def test_stale_and_incomplete_coverage_use_stable_blocker_order() -> None:
    result = _build(
        _candidate_result("000001.SZ", "000002.SZ"),
        _capture(_quote("000001.SZ")),
        AS_OF + timedelta(seconds=121),
    )
    assert result.diagnostics.blockers == (
        RealtimeCandidateSnapshotBlocker.REALTIME_FRESHNESS_NOT_ALLOWED,
        RealtimeCandidateSnapshotBlocker.CANDIDATE_QUOTE_COVERAGE_INCOMPLETE,
    )


@pytest.mark.parametrize(
    ("age", "freshness", "ready"),
    [
        (30, RealtimeFreshness.FRESH, True),
        (60, RealtimeFreshness.FRESH, True),
        (61, RealtimeFreshness.WARNING, True),
        (120, RealtimeFreshness.WARNING, True),
        (121, RealtimeFreshness.STALE, False),
    ],
)
def test_snapshot_reuses_ingestion_freshness_boundaries(
    age: int, freshness: RealtimeFreshness, ready: bool
) -> None:
    result = _build(
        _candidate_result("000001.SZ"),
        _capture(_quote("000001.SZ")),
        AS_OF + timedelta(seconds=age),
    )
    assert result.diagnostics.freshness is freshness
    assert result.diagnostics.snapshot_ready is ready
    assert (result.items == ()) is (not ready)


def test_old_source_timestamp_does_not_override_fresh_ingestion() -> None:
    result = _build(
        _candidate_result("000001.SZ"),
        _capture(
            _quote(
                "000001.SZ", source_timestamp=AS_OF - timedelta(days=1)
            )
        ),
        AS_OF + timedelta(seconds=30),
    )
    assert result.diagnostics.freshness is RealtimeFreshness.FRESH
    assert result.diagnostics.snapshot_ready is True


@pytest.mark.parametrize(
    "case",
    ["future_candidate", "future_capture", "capture_predates_candidate"],
)
def test_rejects_invalid_temporal_ordering(case: str) -> None:
    if case == "future_candidate":
        candidates = _candidate_result("000001.SZ")
        calculation_at = AS_OF - timedelta(seconds=1)
        capture = None
    elif case == "future_capture":
        candidates = _candidate_result("000001.SZ")
        calculation_at = AS_OF
        capture = _capture(_quote("000001.SZ", ingested_at=AS_OF + timedelta(seconds=1)))
    else:
        candidates = _candidate_result("000001.SZ")
        calculation_at = AS_OF + timedelta(seconds=30)
        capture = _capture(_quote("000001.SZ", ingested_at=AS_OF - timedelta(seconds=1)))
    with pytest.raises(RealtimeDataError):
        _build(candidates, capture, calculation_at)


def test_rejects_duplicate_or_capture_identity_mismatched_quotes() -> None:
    duplicate = _capture(_quote("000001.SZ"), _quote("000001.SZ"))
    with pytest.raises(RealtimeDataError, match="unique"):
        _build(_candidate_result("000001.SZ"), duplicate, AS_OF + timedelta(seconds=30))
    mismatched = _capture(
        _quote("000001.SZ", source="other"),
        source="test:realtime",
    )
    with pytest.raises(RealtimeDataError, match="source"):
        _build(_candidate_result("000001.SZ"), mismatched, AS_OF + timedelta(seconds=30))
    mismatched_ingestion = _capture(
        _quote("000001.SZ", ingested_at=AS_OF - timedelta(seconds=1))
    )
    with pytest.raises(RealtimeDataError, match="ingestion"):
        _build(
            _candidate_result("000001.SZ"),
            mismatched_ingestion.model_copy(update={"ingested_at": AS_OF}),
            AS_OF + timedelta(seconds=30),
        )


def test_item_identity_and_identical_input_determinism() -> None:
    with pytest.raises(ValidationError, match="symbols"):
        RealtimeCandidateSnapshotItem(
            candidate=_candidate_result("000001.SZ").candidates[0],
            quote=_quote("000002.SZ"),
        )
    candidates = _candidate_result("000001.SZ")
    capture = _capture(_quote("000001.SZ"))
    calculation_at = AS_OF + timedelta(seconds=30)
    assert _build(candidates, capture, calculation_at) == _build(
        candidates, capture, calculation_at
    )


def _build(
    candidates: RealtimeCandidateResult,
    capture: RealtimeCaptureResult | None,
    calculation_at: datetime,
):
    return RealtimeCandidateSnapshotEngine().build(
        candidates,
        capture,
        calculation_at,
        normal_max_seconds=60,
        warning_max_seconds=120,
    )


def _candidate_result(
    *symbols: str, ready: bool = True
) -> RealtimeCandidateResult:
    policy = RealtimeCandidatePolicy()
    candidates = tuple(
        RealtimeCandidate(
            symbol=symbol,
            as_of=AS_OF,
            base_score=80 - rank,
            market_rank=rank,
            data_completeness=1,
            confidence=1,
        )
        for rank, symbol in enumerate(symbols, start=1)
    )
    diagnostics = RealtimeCandidateDiagnostics(
        as_of=AS_OF,
        policy=policy,
        candidate_ready=ready,
        blockers=(
            ()
            if ready
            else (RealtimeCandidateBlocker.NO_SCOREABLE_INSTRUMENTS,)
        ),
        structural_members=max(len(candidates), 1),
        risk_complete_members=max(len(candidates), 1) if ready else 0,
        risk_eligible_members=max(len(candidates), 1) if ready else 0,
        base_score_input_members=len(candidates),
        scoreable_risk_eligible_members=max(len(candidates), 1) if ready else 0,
        top_bucket_size=max(len(candidates), 1) if ready else 0,
        top_bucket_members=max(len(candidates), 1) if ready else 0,
        threshold_qualified_members=max(len(candidates), 1) if ready else 0,
        final_candidate_members=len(candidates),
    )
    return RealtimeCandidateResult(
        as_of=AS_OF,
        policy=policy,
        diagnostics=diagnostics,
        candidates=candidates,
    )


def _capture(
    *quotes: RealtimeQuote,
    scope: RealtimeCaptureScope = RealtimeCaptureScope.ALL_MARKET,
    source: str = "test:realtime",
) -> RealtimeCaptureResult:
    return RealtimeCaptureResult(
        scope=scope,
        requested_symbols=(
            tuple(sorted(quote.symbol for quote in quotes))
            if scope is RealtimeCaptureScope.EXPLICIT_SYMBOLS
            else None
        ),
        received_quotes=len(quotes),
        received_symbols=tuple(quote.symbol for quote in quotes),
        source=source,
        ingested_at=quotes[0].ingested_at if quotes else AS_OF,
        source_timestamp_available_quotes=sum(
            quote.source_timestamp is not None for quote in quotes
        ),
        persist_requested_symbols=(),
        persisted_quotes=0,
        persisted_symbols=(),
        persistence_performed=False,
        quotes=quotes,
    )


def _quote(
    symbol: str,
    *,
    ingested_at: datetime = AS_OF,
    source: str = "test:realtime",
    source_timestamp: datetime | None = None,
    change_pct: float | None = None,
    turnover_rate: float | None = None,
) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=10,
        change_pct=change_pct,
        turnover_rate=turnover_rate,
        ingested_at=ingested_at,
        source=source,
        source_timestamp=source_timestamp,
    )
