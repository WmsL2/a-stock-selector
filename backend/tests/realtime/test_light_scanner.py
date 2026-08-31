"""Task 17 contracts for pure deterministic realtime light scanning."""

from datetime import UTC, datetime
from math import inf, nan

import pytest
from pydantic import ValidationError

from stock_selector.models import RealtimeQuote
from stock_selector.quality.models import RealtimeFreshness
from stock_selector.realtime import (
    RealtimeCandidate,
    RealtimeCandidateSnapshotBlocker,
    RealtimeCandidateSnapshotDiagnostics,
    RealtimeCandidateSnapshotItem,
    RealtimeCandidateSnapshotResult,
    RealtimeDataError,
    RealtimeLightFlag,
    RealtimeLightScanBlocker,
    RealtimeLightScannerEngine,
    RealtimeLightScanPolicy,
)

AS_OF = datetime(2026, 8, 31, 9, tzinfo=UTC)
CALCULATION_AT = datetime(2026, 8, 31, 9, 0, 30, tzinfo=UTC)


def test_default_policy_and_invalid_thresholds() -> None:
    assert RealtimeLightScanPolicy() == RealtimeLightScanPolicy(
        strong_move_pct=3.0,
        high_turnover_rate_pct=3.0,
        high_volume_ratio=1.5,
    )
    for field in (
        "strong_move_pct",
        "high_turnover_rate_pct",
        "high_volume_ratio",
    ):
        for value in (0, -1, nan, inf):
            with pytest.raises(ValidationError):
                RealtimeLightScanPolicy(**{field: value})


def test_exact_signal_formulas_keep_percentage_units() -> None:
    result = _scan(
        _snapshot(
            _quote(
                "000001.SZ",
                price=103,
                open=100,
                high=105,
                low=99,
                prev_close=100,
                change_pct=2.5,
                turnover_rate=3.25,
                volume_ratio=1.75,
            )
        )
    )
    signals = result.items[0].signals
    assert signals.change_pct == 2.5
    assert signals.price_vs_open_pct == pytest.approx(3.0)
    assert signals.price_vs_prev_close_pct == pytest.approx(3.0)
    assert signals.session_range_pct == pytest.approx(6.0)
    assert signals.turnover_rate_pct == 3.25
    assert signals.volume_ratio == 1.75


@pytest.mark.parametrize(
    ("quote_fields", "expected"),
    [
        ({"open": None}, {"price_vs_open_pct": None}),
        (
            {"prev_close": None},
            {"price_vs_prev_close_pct": None, "session_range_pct": None},
        ),
        ({"high": None}, {"session_range_pct": None}),
        ({"low": None}, {"session_range_pct": None}),
    ],
)
def test_missing_ohlc_values_only_make_dependent_signals_missing(
    quote_fields: dict[str, float | None], expected: dict[str, float | None]
) -> None:
    item = _scan(_snapshot(_quote("000001.SZ", **quote_fields))).items[0]
    for name, value in expected.items():
        assert getattr(item.signals, name) is value
    assert item.snapshot_item.candidate.symbol == "000001.SZ"


def test_sina_style_missing_activity_values_are_ready_without_activity_flags() -> None:
    result = _scan(
        _snapshot(
            _quote("000001.SZ", change_pct=4, turnover_rate=None, volume_ratio=None)
        )
    )
    assert result.diagnostics.scan_ready is True
    assert result.items[0].signals.turnover_rate_pct is None
    assert result.items[0].signals.volume_ratio is None
    assert RealtimeLightFlag.HIGH_TURNOVER not in result.items[0].flags
    assert RealtimeLightFlag.HIGH_VOLUME_RATIO not in result.items[0].flags


def test_change_pct_never_falls_back_to_derived_previous_close_change() -> None:
    item = _scan(
        _snapshot(_quote("000001.SZ", price=104, prev_close=100, change_pct=None))
    ).items[0]
    assert item.signals.change_pct is None
    assert item.signals.price_vs_prev_close_pct == pytest.approx(4.0)
    assert RealtimeLightFlag.STRONG_UP_MOVE not in item.flags


def test_provider_change_and_derived_change_can_differ() -> None:
    item = _scan(
        _snapshot(_quote("000001.SZ", price=103, prev_close=100, change_pct=2.5))
    ).items[0]
    assert item.signals.change_pct == 2.5
    assert item.signals.price_vs_prev_close_pct == pytest.approx(3.0)
    assert RealtimeLightFlag.STRONG_UP_MOVE not in item.flags


def test_thresholds_are_inclusive_and_flags_follow_semantic_order() -> None:
    item = _scan(
        _snapshot(
            _quote(
                "000001.SZ", change_pct=3.0, turnover_rate=3.0, volume_ratio=1.5
            )
        )
    ).items[0]
    assert item.flags == (
        RealtimeLightFlag.STRONG_UP_MOVE,
        RealtimeLightFlag.HIGH_TURNOVER,
        RealtimeLightFlag.HIGH_VOLUME_RATIO,
    )
    down = _scan(_snapshot(_quote("000001.SZ", change_pct=-3.0))).items[0]
    assert down.flags == (RealtimeLightFlag.STRONG_DOWN_MOVE,)


def test_just_below_thresholds_do_not_flag() -> None:
    item = _scan(
        _snapshot(
            _quote(
                "000001.SZ",
                change_pct=-2.999,
                turnover_rate=2.999,
                volume_ratio=1.499,
            )
        )
    ).items[0]
    assert item.flags == ()


def test_rank_membership_and_exact_upstream_objects_are_preserved() -> None:
    snapshot = _snapshot(
        _quote("000001.SZ", change_pct=-9, turnover_rate=0),
        _quote("000002.SZ", change_pct=9, turnover_rate=9),
    )
    result = _scan(snapshot)
    assert tuple(item.snapshot_item.candidate.symbol for item in result.items) == (
        "000001.SZ",
        "000002.SZ",
    )
    assert tuple(item.snapshot_item.candidate.market_rank for item in result.items) == (1, 2)
    assert tuple(item.snapshot_item.candidate for item in result.items) == tuple(
        item.candidate for item in snapshot.items
    )
    assert tuple(item.snapshot_item.quote for item in result.items) == tuple(
        item.quote for item in snapshot.items
    )


def test_extreme_valid_values_do_not_filter_and_custom_policy_changes_only_flags() -> None:
    snapshot = _snapshot(
        _quote(
            "000001.SZ",
            price=1e150,
            open=1e149,
            high=1e150,
            low=1e149,
            prev_close=1e149,
            change_pct=3,
            turnover_rate=3,
            volume_ratio=1.5,
        )
    )
    default = _scan(snapshot)
    custom = _scan(
        snapshot,
        RealtimeLightScanPolicy(
            strong_move_pct=999, high_turnover_rate_pct=4, high_volume_ratio=2
        ),
    )
    assert len(default.items) == len(custom.items) == 1
    assert default.items[0].snapshot_item.candidate == custom.items[0].snapshot_item.candidate
    assert default.items[0].snapshot_item.candidate.market_rank == 1
    assert default.items[0].flags != custom.items[0].flags


def test_non_finite_derived_signal_raises_instead_of_becoming_missing() -> None:
    snapshot = _snapshot(
        _quote(
            "000001.SZ",
            price=1e308,
            open=1,
            high=1e308,
            low=1,
            prev_close=1,
        )
    )
    with pytest.raises(RealtimeDataError, match="derived realtime signal must be finite"):
        _scan(snapshot)


def test_blocked_upstream_and_ready_empty_are_explicit() -> None:
    blocked = _scan(_snapshot(_quote("000001.SZ"), ready=False))
    assert blocked.diagnostics.scan_ready is False
    assert blocked.items == ()
    assert blocked.diagnostics.blockers == (
        RealtimeLightScanBlocker.CANDIDATE_SNAPSHOT_NOT_READY,
    )
    assert blocked.diagnostics.upstream_blockers == (
        RealtimeCandidateSnapshotBlocker.REALTIME_FRESHNESS_NOT_ALLOWED,
    )
    empty = _scan(_snapshot())
    assert empty.diagnostics.scan_ready is True
    assert empty.items == ()
    assert empty.diagnostics.blockers == ()
    assert empty.diagnostics.overall_signal_coverage is None


def test_signal_availability_accounting_and_determinism() -> None:
    snapshot = _snapshot(
        _quote("000001.SZ", turnover_rate=None, volume_ratio=None),
        _quote(
            "000002.SZ",
            open=None,
            high=None,
            low=None,
            prev_close=None,
            change_pct=None,
        ),
    )
    result = _scan(snapshot)
    assert [item.available_signals for item in result.items] == [4, 2]
    assert [item.signal_completeness for item in result.items] == [4 / 6, 2 / 6]
    diagnostics = result.diagnostics
    assert diagnostics.change_pct_available_items == 1
    assert diagnostics.price_vs_open_available_items == 1
    assert diagnostics.price_vs_prev_close_available_items == 1
    assert diagnostics.session_range_available_items == 1
    assert diagnostics.turnover_rate_available_items == 1
    assert diagnostics.volume_ratio_available_items == 1
    assert diagnostics.available_signal_values == 6
    assert diagnostics.total_signal_slots == 12
    assert diagnostics.overall_signal_coverage == 0.5
    assert result == _scan(snapshot)


def _scan(snapshot: RealtimeCandidateSnapshotResult, policy: RealtimeLightScanPolicy | None = None):
    return RealtimeLightScannerEngine().scan(snapshot, policy)


def _snapshot(*quotes: RealtimeQuote, ready: bool = True) -> RealtimeCandidateSnapshotResult:
    items = tuple(
        RealtimeCandidateSnapshotItem(
            candidate=RealtimeCandidate(
                symbol=quote.symbol,
                as_of=AS_OF,
                base_score=80 - rank,
                market_rank=rank,
                data_completeness=1,
                confidence=1,
            ),
            quote=quote,
        )
        for rank, quote in enumerate(quotes, start=1)
    )
    return RealtimeCandidateSnapshotResult(
        as_of=AS_OF,
        diagnostics=RealtimeCandidateSnapshotDiagnostics(
            calculation_at=CALCULATION_AT,
            candidate_as_of=AS_OF,
            candidate_ready=ready,
            candidate_members=len(items),
            capture_available=bool(items),
            capture_scope=None if not items else "all_market",
            capture_source=None if not items else "test:realtime",
            capture_ingested_at=None if not items else AS_OF,
            received_quotes=len(items),
            freshness=RealtimeFreshness.FRESH if items else RealtimeFreshness.UNAVAILABLE,
            age_seconds=30.0 if items else None,
            freshness_allowed=ready,
            matched_candidate_quotes=len(items),
            missing_candidate_quotes=0,
            missing_candidate_symbols=(),
            snapshot_ready=ready,
            blockers=(
                ()
                if ready
                else (RealtimeCandidateSnapshotBlocker.REALTIME_FRESHNESS_NOT_ALLOWED,)
            ),
        ),
        items=items if ready else (),
    )


def _quote(symbol: str, **overrides: float | None) -> RealtimeQuote:
    values: dict[str, float | None] = {
        "price": 102,
        "open": 100,
        "high": 104,
        "low": 99,
        "prev_close": 100,
        "change_pct": 2,
        "turnover_rate": 2,
        "volume_ratio": 1,
    }
    values.update(overrides)
    return RealtimeQuote(
        symbol=symbol,
        ingested_at=AS_OF,
        source="test:realtime",
        **values,
    )
