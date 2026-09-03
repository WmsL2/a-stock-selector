"""Sequential bounded collection of separate HFQ daily-return evidence."""

from stock_selector.collection.errors import CollectionDataError, CollectionError
from stock_selector.collection.models import (
    AdjustedReturnCollectionReport,
    AdjustedReturnCollectionRequest,
    AdjustedReturnCollectionStatus,
    AdjustedReturnSymbolResult,
)
from stock_selector.models import AdjustedDailyReturn, AdjustmentType
from stock_selector.providers.base import AdjustedDailyReturnProvider
from stock_selector.providers.errors import ProviderError
from stock_selector.providers.requests import AdjustedDailyReturnsRequest
from stock_selector.storage import LocalMarketRepository, StorageError


class AdjustedDailyReturnCollector:
    """Persist HFQ return evidence one explicit symbol at a time."""

    def __init__(self, provider: AdjustedDailyReturnProvider, repository: LocalMarketRepository) -> None:
        self._provider = provider
        self._repository = repository

    def collect(self, request: AdjustedReturnCollectionRequest) -> AdjustedReturnCollectionReport:
        """Return deterministic per-symbol outcomes; infrastructure errors abort the run."""
        results: list[AdjustedReturnSymbolResult] = []
        for symbol in request.symbols:
            try:
                records = self._provider.get_adjusted_daily_returns(
                    AdjustedDailyReturnsRequest(
                        symbol=symbol, start_date=request.start_date, end_date=request.end_date
                    )
                )
                self._validate(symbol, records, request)
            except (CollectionDataError, ProviderError) as exc:
                results.append(
                    AdjustedReturnSymbolResult(
                        symbol=symbol, status=AdjustedReturnCollectionStatus.FAILED,
                        rows_received=0, rows_persisted=0, error_type=type(exc).__name__,
                        error_message=str(exc)[:240] or "provider collection failed",
                    )
                )
                continue
            if not records:
                results.append(
                    AdjustedReturnSymbolResult(
                        symbol=symbol, status=AdjustedReturnCollectionStatus.EMPTY,
                        rows_received=0, rows_persisted=0,
                    )
                )
                continue
            try:
                self._repository.upsert_adjusted_daily_returns(records)
            except StorageError as exc:
                raise CollectionError("adjusted-return storage infrastructure failed") from exc
            results.append(
                AdjustedReturnSymbolResult(
                    symbol=symbol, status=AdjustedReturnCollectionStatus.SUCCESS,
                    rows_received=len(records), rows_persisted=len(records),
                    source=records[0].source, observed_at=records[0].observed_at,
                )
            )
        outcome = tuple(results)
        return AdjustedReturnCollectionReport(
            requested_symbols=request.symbols, start_date=request.start_date, end_date=request.end_date,
            success_symbols=sum(item.status is AdjustedReturnCollectionStatus.SUCCESS for item in outcome),
            empty_symbols=sum(item.status is AdjustedReturnCollectionStatus.EMPTY for item in outcome),
            failed_symbols=sum(item.status is AdjustedReturnCollectionStatus.FAILED for item in outcome),
            rows_received=sum(item.rows_received for item in outcome),
            rows_persisted=sum(item.rows_persisted for item in outcome), results=outcome,
        )

    @staticmethod
    def _validate(
        symbol: str,
        records: tuple[AdjustedDailyReturn, ...],
        request: AdjustedReturnCollectionRequest,
    ) -> None:
        if not records:
            return
        if any(item.symbol != symbol for item in records):
            raise CollectionDataError("provider returned a return for a different symbol")
        if any(item.adjustment is not AdjustmentType.HFQ for item in records):
            raise CollectionDataError("provider returned a non-HFQ return")
        if any(item.trade_date < request.start_date or item.trade_date > request.end_date for item in records):
            raise CollectionDataError("provider returned a return outside the requested range")
        if len({item.trade_date for item in records}) != len(records):
            raise CollectionDataError("provider returned duplicate trade dates")
        if len({item.observed_at for item in records}) != 1:
            raise CollectionDataError("provider returned mixed observed_at values")
        if len({item.source for item in records}) != 1:
            raise CollectionDataError("provider returned mixed sources")
