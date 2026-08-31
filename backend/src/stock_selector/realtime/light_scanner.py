"""Pure deterministic Task 17 per-candidate realtime observations."""

import math

from .errors import RealtimeDataError
from .models import (
    RealtimeCandidateSnapshotItem,
    RealtimeCandidateSnapshotResult,
    RealtimeLightFlag,
    RealtimeLightScanBlocker,
    RealtimeLightScanDiagnostics,
    RealtimeLightScanItem,
    RealtimeLightScanPolicy,
    RealtimeLightScanResult,
    RealtimeLightSignals,
)


class RealtimeLightScannerEngine:
    """Annotate an already-ready Task 16 snapshot without I/O or re-gating."""

    def scan(
        self,
        snapshot: RealtimeCandidateSnapshotResult,
        policy: RealtimeLightScanPolicy | None = None,
    ) -> RealtimeLightScanResult:
        """Return one descriptive scan while preserving every upstream item and rank."""
        resolved_policy = policy or RealtimeLightScanPolicy()
        if not snapshot.diagnostics.snapshot_ready:
            return _result(snapshot, resolved_policy, ())
        items = tuple(
            _item(snapshot_item, resolved_policy) for snapshot_item in snapshot.items
        )
        return _result(snapshot, resolved_policy, items)


def _item(
    snapshot_item: RealtimeCandidateSnapshotItem,
    policy: RealtimeLightScanPolicy,
) -> RealtimeLightScanItem:
    quote = snapshot_item.quote
    signals = RealtimeLightSignals(
        change_pct=quote.change_pct,
        price_vs_open_pct=_percentage_change(quote.price, quote.open),
        price_vs_prev_close_pct=_percentage_change(quote.price, quote.prev_close),
        session_range_pct=(
            _percentage_range(quote.high, quote.low, quote.prev_close)
            if quote.high is not None and quote.low is not None
            else None
        ),
        turnover_rate_pct=quote.turnover_rate,
        volume_ratio=quote.volume_ratio,
    )
    flags = _flags(signals, policy)
    available = sum(value is not None for value in signals.model_dump().values())
    return RealtimeLightScanItem(
        snapshot_item=snapshot_item,
        signals=signals,
        flags=flags,
        available_signals=available,
        signal_completeness=available / 6,
    )


def _percentage_change(price: float, reference: float | None) -> float | None:
    if reference is None:
        return None
    return _finite_derived((price / reference - 1) * 100)


def _percentage_range(
    high: float, low: float, prev_close: float | None
) -> float | None:
    if prev_close is None:
        return None
    return _finite_derived((high - low) / prev_close * 100)


def _finite_derived(value: float) -> float:
    if not math.isfinite(value):
        raise RealtimeDataError("derived realtime signal must be finite")
    return value


def _flags(
    signals: RealtimeLightSignals, policy: RealtimeLightScanPolicy
) -> tuple[RealtimeLightFlag, ...]:
    flags: list[RealtimeLightFlag] = []
    if signals.change_pct is not None and signals.change_pct >= policy.strong_move_pct:
        flags.append(RealtimeLightFlag.STRONG_UP_MOVE)
    if signals.change_pct is not None and signals.change_pct <= -policy.strong_move_pct:
        flags.append(RealtimeLightFlag.STRONG_DOWN_MOVE)
    if (
        signals.turnover_rate_pct is not None
        and signals.turnover_rate_pct >= policy.high_turnover_rate_pct
    ):
        flags.append(RealtimeLightFlag.HIGH_TURNOVER)
    if (
        signals.volume_ratio is not None
        and signals.volume_ratio >= policy.high_volume_ratio
    ):
        flags.append(RealtimeLightFlag.HIGH_VOLUME_RATIO)
    return tuple(flags)


def _result(
    snapshot: RealtimeCandidateSnapshotResult,
    policy: RealtimeLightScanPolicy,
    items: tuple[RealtimeLightScanItem, ...],
) -> RealtimeLightScanResult:
    diagnostics = RealtimeLightScanDiagnostics(
        calculation_at=snapshot.diagnostics.calculation_at,
        candidate_as_of=snapshot.as_of,
        upstream_snapshot_ready=snapshot.diagnostics.snapshot_ready,
        upstream_blockers=snapshot.diagnostics.blockers,
        input_items=len(snapshot.items),
        output_items=len(items),
        scan_ready=snapshot.diagnostics.snapshot_ready,
        blockers=(
            ()
            if snapshot.diagnostics.snapshot_ready
            else (RealtimeLightScanBlocker.CANDIDATE_SNAPSHOT_NOT_READY,)
        ),
        flagged_items=sum(bool(item.flags) for item in items),
        change_pct_available_items=sum(item.signals.change_pct is not None for item in items),
        price_vs_open_available_items=sum(
            item.signals.price_vs_open_pct is not None for item in items
        ),
        price_vs_prev_close_available_items=sum(
            item.signals.price_vs_prev_close_pct is not None for item in items
        ),
        session_range_available_items=sum(
            item.signals.session_range_pct is not None for item in items
        ),
        turnover_rate_available_items=sum(
            item.signals.turnover_rate_pct is not None for item in items
        ),
        volume_ratio_available_items=sum(
            item.signals.volume_ratio is not None for item in items
        ),
        available_signal_values=sum(item.available_signals for item in items),
        total_signal_slots=len(snapshot.items) * 6,
        overall_signal_coverage=(
            None
            if not snapshot.items
            else sum(item.available_signals for item in items) / (len(snapshot.items) * 6)
        ),
    )
    return RealtimeLightScanResult(
        as_of=snapshot.as_of,
        policy=policy,
        diagnostics=diagnostics,
        items=items,
    )
