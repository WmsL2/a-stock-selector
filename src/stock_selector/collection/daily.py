"""Sequential, bounded RAW daily-price collection through provider abstractions."""

from stock_selector.collection.errors import (
    CollectionDataError,
    CollectionError,
    CollectionNotSupportedError,
)
from stock_selector.collection.models import (
    DailyCollectionReport,
    DailyCollectionRequest,
    DailyCollectionStatus,
    DailySymbolCollectionResult,
)
from stock_selector.models import AdjustmentType, DailyBar
from stock_selector.providers.base import DailyMarketDataProvider
from stock_selector.providers.errors import ProviderError
from stock_selector.providers.requests import DailyBarsRequest
from stock_selector.storage import LocalMarketRepository, StorageError


class DailyPriceCollector:
    """Collect only caller-supplied symbols and date ranges, one request at a time."""

    def __init__(self, provider: DailyMarketDataProvider, repository: LocalMarketRepository) -> None:
        self._provider = provider
        self._repository = repository

    def collect(self, request: DailyCollectionRequest) -> DailyCollectionReport:
        """Persist valid batches while isolating only provider/data failures by symbol."""
        if request.adjustment is not AdjustmentType.RAW:
            raise CollectionNotSupportedError("daily collection currently supports RAW only")
        results = tuple(self._collect_symbol(symbol, request) for symbol in request.symbols)
        return DailyCollectionReport(
            start_date=request.start_date,
            end_date=request.end_date,
            adjustment=request.adjustment,
            requested_symbols=request.symbols,
            succeeded_symbols=sum(result.status is DailyCollectionStatus.SUCCESS for result in results),
            empty_symbols=sum(result.status is DailyCollectionStatus.EMPTY for result in results),
            failed_symbols=sum(result.status is DailyCollectionStatus.FAILED for result in results),
            total_rows_received=sum(result.rows_received for result in results),
            results=results,
        )

    def _collect_symbol(
        self, symbol: str, request: DailyCollectionRequest
    ) -> DailySymbolCollectionResult:
        try:
            bars = self._provider.get_daily_bars(
                DailyBarsRequest(
                    symbol=symbol,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    adjustment=request.adjustment,
                )
            )
            validated = self._validate_batch(symbol, bars, request)
        except (CollectionDataError, ProviderError) as exc:
            return _failed_result(symbol, request, exc)
        if not validated:
            return DailySymbolCollectionResult(
                symbol=symbol,
                status=DailyCollectionStatus.EMPTY,
                requested_start_date=request.start_date,
                requested_end_date=request.end_date,
                rows_received=0,
                rows_persisted=0,
            )
        try:
            self._repository.upsert_daily_bars(validated)
        except StorageError as exc:
            raise CollectionError("daily storage infrastructure failed") from exc
        return DailySymbolCollectionResult(
            symbol=symbol,
            status=DailyCollectionStatus.SUCCESS,
            requested_start_date=request.start_date,
            requested_end_date=request.end_date,
            rows_received=len(validated),
            rows_persisted=len(validated),
            source=validated[0].source,
        )

    @staticmethod
    def _validate_batch(
        symbol: str, bars: tuple[DailyBar, ...], request: DailyCollectionRequest
    ) -> tuple[DailyBar, ...]:
        if not bars:
            return ()
        if any(bar.symbol != symbol for bar in bars):
            raise CollectionDataError("provider returned a bar for a different symbol")
        if any(bar.adjustment is not request.adjustment for bar in bars):
            raise CollectionDataError("provider returned an unexpected adjustment basis")
        if any(
            bar.trade_date < request.start_date or bar.trade_date > request.end_date
            for bar in bars
        ):
            raise CollectionDataError("provider returned a bar outside the requested date range")
        if len({bar.trade_date for bar in bars}) != len(bars):
            raise CollectionDataError("provider returned duplicate trade dates")
        if len({bar.source for bar in bars}) != 1:
            raise CollectionDataError("provider returned mixed sources for one symbol request")
        return tuple(sorted(bars, key=lambda bar: bar.trade_date))


def _failed_result(
    symbol: str, request: DailyCollectionRequest, exc: Exception
) -> DailySymbolCollectionResult:
    """Expose a compact, provider-safe failure instead of traceback details."""
    message = str(exc).replace("\n", " ")[:240] or "provider collection failed"
    return DailySymbolCollectionResult(
        symbol=symbol,
        status=DailyCollectionStatus.FAILED,
        requested_start_date=request.start_date,
        requested_end_date=request.end_date,
        rows_received=0,
        rows_persisted=0,
        error_type=type(exc).__name__,
        error_message=message,
    )
