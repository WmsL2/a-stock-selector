"""Task 18 contracts for Task10-backed realtime signal normalization."""

from datetime import UTC, datetime

import pytest

from stock_selector.models import RealtimeQuote
from stock_selector.preprocessing import FactorPreprocessingDataError
from stock_selector.realtime import (
    RealtimeCandidate,
    RealtimeCandidateSnapshotItem,
    RealtimeDataError,
    RealtimeLightFlag,
    RealtimeLightScanBlocker,
    RealtimeLightScanDiagnostics,
    RealtimeLightScanItem,
    RealtimeLightScanPolicy,
    RealtimeLightScanResult,
    RealtimeLightSignals,
    RealtimeSignalNormalizationBlocker,
    RealtimeSignalNormalizerEngine,
)

AS_OF = datetime(2026, 8, 31, 9, tzinfo=UTC)
CALCULATION_AT = datetime(2026, 8, 31, 9, 0, 30, tzinfo=UTC)


def test_basic_percentiles_are_raw_value_magnitudes_not_desirability() -> None:
    result = _normalize(_scan(10, 20, 30))
    assert [item.percentiles.change_pct_percentile for item in result.items] == [
        0.0,
        50.0,
        100.0,
    ]
    assert [item.percentiles.session_range_pct_percentile for item in result.items] == [
        0.0,
        50.0,
        100.0,
    ]


def test_ties_singletons_missingness_and_signal_local_denominators() -> None:
    tied = _normalize(_scan(10, 20, 20, 40))
    assert [item.percentiles.change_pct_percentile for item in tied.items] == [
        0.0,
        pytest.approx(50.0),
        pytest.approx(50.0),
        100.0,
    ]
    scan = _scan(10, 20, 30, turnover=(1, None, 3), volume=(None, 5, None))
    result = _normalize(scan)
    assert [item.percentiles.turnover_rate_pct_percentile for item in result.items] == [
        0.0,
        None,
        100.0,
    ]
    assert [item.percentiles.volume_ratio_percentile for item in result.items] == [
        None,
        50.0,
        None,
    ]
    assert [item.percentiles.change_pct_percentile for item in result.items] == [
        0.0,
        50.0,
        100.0,
    ]


def test_all_missing_activity_and_extreme_finite_values_stay_unimputed_unwinsorized() -> None:
    result = _normalize(
        _scan(1e-100, 1, 1e100, turnover=(None, None, None), volume=(None, None, None))
    )
    assert [item.percentiles.change_pct_percentile for item in result.items] == [
        0.0,
        50.0,
        100.0,
    ]
    assert all(item.percentiles.turnover_rate_pct_percentile is None for item in result.items)
    assert all(item.percentiles.volume_ratio_percentile is None for item in result.items)
    assert result.diagnostics.normalization_ready is True


def test_all_six_fields_map_independently_and_preserve_rank_and_objects() -> None:
    scan = _scan(
        30,
        20,
        10,
        open_values=(30, 20, 10),
        prev_values=(10, 20, 30),
        range_values=(20, 10, 30),
        turnover=(3, 2, 1),
        volume=(1, 2, 3),
        flags=(
            (RealtimeLightFlag.STRONG_UP_MOVE,),
            (),
            (RealtimeLightFlag.HIGH_VOLUME_RATIO,),
        ),
    )
    result = _normalize(scan)
    assert [item.scan_item for item in result.items] == list(scan.items)
    assert [item.scan_item.snapshot_item.candidate.market_rank for item in result.items] == [
        1,
        2,
        3,
    ]
    first = result.items[0].percentiles
    assert (
        first.change_pct_percentile,
        first.price_vs_open_pct_percentile,
        first.price_vs_prev_close_pct_percentile,
        first.session_range_pct_percentile,
        first.turnover_rate_pct_percentile,
        first.volume_ratio_percentile,
    ) == (100.0, 100.0, 0.0, 50.0, 100.0, 0.0)


def test_readiness_ready_empty_availability_and_determinism() -> None:
    blocked = _normalize(_scan(10, ready=False))
    assert blocked.items == ()
    assert blocked.diagnostics.blockers == (
        RealtimeSignalNormalizationBlocker.LIGHT_SCAN_NOT_READY,
    )
    assert blocked.diagnostics.upstream_blockers == (
        RealtimeLightScanBlocker.CANDIDATE_SNAPSHOT_NOT_READY,
    )
    empty = _normalize(_scan())
    assert empty.diagnostics.normalization_ready is True
    assert empty.items == ()
    assert empty.diagnostics.overall_percentile_coverage is None
    scan = _scan(10, 20, 30, turnover=(1, None, 3), volume=(None, 5, None))
    result = _normalize(scan)
    diagnostics = result.diagnostics
    assert (
        diagnostics.change_pct_ranked_items,
        diagnostics.price_vs_open_ranked_items,
        diagnostics.price_vs_prev_close_ranked_items,
        diagnostics.session_range_ranked_items,
        diagnostics.turnover_rate_ranked_items,
        diagnostics.volume_ratio_ranked_items,
    ) == (3, 3, 3, 3, 2, 1)
    assert (diagnostics.available_percentile_values, diagnostics.total_percentile_slots) == (15, 18)
    assert diagnostics.overall_percentile_coverage == pytest.approx(15 / 18)
    assert result == _normalize(scan)
    assert result.calculation_at == CALCULATION_AT
    assert result.candidate_as_of == AS_OF


def test_preprocessing_errors_are_translated_but_programming_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stock_selector.realtime import signal_normalizer

    def raise_data_error(*_args: object, **_kwargs: object) -> None:
        raise FactorPreprocessingDataError("bad cross-section")

    monkeypatch.setattr(
        signal_normalizer.FactorPreprocessingEngine, "preprocess", raise_data_error
    )
    with pytest.raises(RealtimeDataError) as caught:
        _normalize(_scan(10))
    assert isinstance(caught.value.__cause__, FactorPreprocessingDataError)

    def raise_runtime_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("programming error")

    monkeypatch.setattr(
        signal_normalizer.FactorPreprocessingEngine, "preprocess", raise_runtime_error
    )
    with pytest.raises(RuntimeError, match="programming error"):
        _normalize(_scan(10))


def _normalize(scan: RealtimeLightScanResult):
    return RealtimeSignalNormalizerEngine().normalize(scan)


def _scan(
    *changes: float,
    open_values: tuple[float | None, ...] | None = None,
    prev_values: tuple[float | None, ...] | None = None,
    range_values: tuple[float | None, ...] | None = None,
    turnover: tuple[float | None, ...] | None = None,
    volume: tuple[float | None, ...] | None = None,
    flags: tuple[tuple[RealtimeLightFlag, ...], ...] | None = None,
    ready: bool = True,
) -> RealtimeLightScanResult:
    count = len(changes)
    open_values = open_values or changes
    prev_values = prev_values or changes
    range_values = range_values or changes
    turnover = turnover or tuple(1.0 for _ in changes)
    volume = volume or tuple(1.0 for _ in changes)
    flags = flags or tuple(() for _ in changes)
    items = tuple(
        _scan_item(
            rank,
            change,
            open_values[rank - 1],
            prev_values[rank - 1],
            range_values[rank - 1],
            turnover[rank - 1],
            volume[rank - 1],
            flags[rank - 1],
        )
        for rank, change in enumerate(changes, start=1)
    )
    return RealtimeLightScanResult(
        as_of=AS_OF,
        policy=RealtimeLightScanPolicy(),
        diagnostics=RealtimeLightScanDiagnostics(
            calculation_at=CALCULATION_AT,
            candidate_as_of=AS_OF,
            upstream_snapshot_ready=ready,
            upstream_blockers=(),
            input_items=count,
            output_items=count if ready else 0,
            scan_ready=ready,
            blockers=(
                () if ready else (RealtimeLightScanBlocker.CANDIDATE_SNAPSHOT_NOT_READY,)
            ),
            flagged_items=sum(bool(value) for value in flags) if ready else 0,
            change_pct_available_items=count,
            price_vs_open_available_items=count,
            price_vs_prev_close_available_items=count,
            session_range_available_items=count,
            turnover_rate_available_items=sum(value is not None for value in turnover),
            volume_ratio_available_items=sum(value is not None for value in volume),
            available_signal_values=(
                4 * count
                + sum(value is not None for value in turnover)
                + sum(value is not None for value in volume)
            ),
            total_signal_slots=count * 6,
            overall_signal_coverage=(
                None
                if not count
                else (
                    4 * count
                    + sum(value is not None for value in turnover)
                    + sum(value is not None for value in volume)
                )
                / (count * 6)
            ),
        ),
        items=items if ready else (),
    )


def _scan_item(
    rank: int,
    change: float,
    open_value: float | None,
    prev_value: float | None,
    range_value: float | None,
    turnover: float | None,
    volume: float | None,
    flags: tuple[RealtimeLightFlag, ...],
) -> RealtimeLightScanItem:
    symbol = f"{rank:06d}.SZ"
    quote = RealtimeQuote(symbol=symbol, price=10, ingested_at=AS_OF, source="test")
    snapshot_item = RealtimeCandidateSnapshotItem(
        candidate=RealtimeCandidate(
            symbol=symbol,
            as_of=AS_OF,
            base_score=80,
            market_rank=rank,
            data_completeness=1,
            confidence=1,
        ),
        quote=quote,
    )
    signals = RealtimeLightSignals(
        change_pct=change,
        price_vs_open_pct=open_value,
        price_vs_prev_close_pct=prev_value,
        session_range_pct=range_value,
        turnover_rate_pct=turnover,
        volume_ratio=volume,
    )
    available = sum(value is not None for value in signals.model_dump().values())
    return RealtimeLightScanItem(
        snapshot_item=snapshot_item,
        signals=signals,
        flags=flags,
        available_signals=available,
        signal_completeness=available / 6,
    )
