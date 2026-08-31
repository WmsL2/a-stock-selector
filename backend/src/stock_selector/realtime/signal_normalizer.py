"""Task 18 adapter from Task 17 observations to generic percentile preprocessing."""

from stock_selector.preprocessing import (
    FactorDirection,
    FactorPreprocessingDataError,
    FactorPreprocessingEngine,
    FactorPreprocessingRequest,
    MissingValuePolicy,
    NeutralizationMode,
    RawFactorObservation,
)

from .errors import RealtimeDataError
from .models import (
    RealtimeLightScanItem,
    RealtimeLightScanResult,
    RealtimeSignalNormalizationBlocker,
    RealtimeSignalNormalizationDiagnostics,
    RealtimeSignalNormalizationItem,
    RealtimeSignalNormalizationResult,
    RealtimeSignalPercentiles,
)

_SIGNALS = (
    "change_pct",
    "price_vs_open_pct",
    "price_vs_prev_close_pct",
    "session_range_pct",
    "turnover_rate_pct",
    "volume_ratio",
)


class RealtimeSignalNormalizerEngine:
    """Normalize supplied Task 17 signals without data access or signal recomputation."""

    def normalize(
        self, scan: RealtimeLightScanResult
    ) -> RealtimeSignalNormalizationResult:
        """Return six independent raw-magnitude percentile cross-sections."""
        if not scan.diagnostics.scan_ready:
            return _result(scan, ())
        if not scan.items:
            return _result(scan, ())
        by_signal = {signal: _normalize_signal(scan, signal) for signal in _SIGNALS}
        items = tuple(_item(scan_item, by_signal) for scan_item in scan.items)
        return _result(scan, items)


def _normalize_signal(
    scan: RealtimeLightScanResult, signal: str
) -> dict[str, float | None]:
    request = FactorPreprocessingRequest(
        observations=tuple(
            RawFactorObservation(
                symbol=item.snapshot_item.candidate.symbol,
                as_of=scan.diagnostics.calculation_at,
                factor_name=signal,
                factor_group="realtime_signal",
                raw_value=getattr(item.signals, signal),
                industry_key=None,
                source=item.snapshot_item.quote.source,
            )
            for item in scan.items
        ),
        missing_policy=MissingValuePolicy.KEEP_MISSING,
        direction=FactorDirection.HIGHER_IS_BETTER,
        neutralization=NeutralizationMode.NONE,
        winsorize=False,
    )
    try:
        result = FactorPreprocessingEngine().preprocess(request)
    except FactorPreprocessingDataError as exc:
        raise RealtimeDataError("invalid realtime signal preprocessing input") from exc
    return {value.symbol: value.score for value in result.values}


def _item(
    scan_item: RealtimeLightScanItem, by_signal: dict[str, dict[str, float | None]]
) -> RealtimeSignalNormalizationItem:
    symbol = scan_item.snapshot_item.candidate.symbol
    percentiles = RealtimeSignalPercentiles(
        **{f"{signal}_percentile": by_signal[signal][symbol] for signal in _SIGNALS}
    )
    available = sum(value is not None for value in percentiles.model_dump().values())
    return RealtimeSignalNormalizationItem(
        scan_item=scan_item,
        percentiles=percentiles,
        available_percentiles=available,
        percentile_completeness=available / 6,
    )


def _result(
    scan: RealtimeLightScanResult,
    items: tuple[RealtimeSignalNormalizationItem, ...],
) -> RealtimeSignalNormalizationResult:
    ranked_counts = {
        signal: sum(
            getattr(item.percentiles, f"{signal}_percentile") is not None
            for item in items
        )
        for signal in _SIGNALS
    }
    available = sum(item.available_percentiles for item in items)
    diagnostics = RealtimeSignalNormalizationDiagnostics(
        calculation_at=scan.diagnostics.calculation_at,
        candidate_as_of=scan.diagnostics.candidate_as_of,
        upstream_scan_ready=scan.diagnostics.scan_ready,
        upstream_blockers=scan.diagnostics.blockers,
        input_items=len(scan.items),
        output_items=len(items),
        normalization_ready=scan.diagnostics.scan_ready,
        blockers=(
            ()
            if scan.diagnostics.scan_ready
            else (RealtimeSignalNormalizationBlocker.LIGHT_SCAN_NOT_READY,)
        ),
        change_pct_ranked_items=ranked_counts["change_pct"],
        price_vs_open_ranked_items=ranked_counts["price_vs_open_pct"],
        price_vs_prev_close_ranked_items=ranked_counts["price_vs_prev_close_pct"],
        session_range_ranked_items=ranked_counts["session_range_pct"],
        turnover_rate_ranked_items=ranked_counts["turnover_rate_pct"],
        volume_ratio_ranked_items=ranked_counts["volume_ratio"],
        available_percentile_values=available,
        total_percentile_slots=len(scan.items) * 6,
        overall_percentile_coverage=(
            None if not scan.items else available / (len(scan.items) * 6)
        ),
    )
    return RealtimeSignalNormalizationResult(
        calculation_at=scan.diagnostics.calculation_at,
        candidate_as_of=scan.diagnostics.candidate_as_of,
        diagnostics=diagnostics,
        items=items,
    )
