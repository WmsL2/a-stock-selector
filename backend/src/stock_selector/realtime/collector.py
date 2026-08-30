from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.providers.errors import ProviderError
from stock_selector.providers.requests import RealtimeQuotesRequest
from stock_selector.storage import LocalMarketRepository, StorageError

from .errors import RealtimeCollectionError, RealtimeDataError
from .models import RealtimeCaptureRequest, RealtimeCaptureResult, RealtimeCaptureScope


class RealtimeSnapshotCollector:
    """Collect one validated snapshot and persist only named symbols."""

    def __init__(
        self,
        provider: RealtimeMarketDataProvider,
        repository: LocalMarketRepository | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def capture(self, request: RealtimeCaptureRequest) -> RealtimeCaptureResult:
        """Capture exactly once and validate snapshot-level provenance."""
        try:
            quotes = self._provider.get_realtime_quotes(
                RealtimeQuotesRequest(symbols=request.symbols)
            )
        except ProviderError as exc:
            raise RealtimeCollectionError("provider realtime capture failed") from exc
        if not quotes:
            raise RealtimeDataError("realtime snapshot must not be empty")
        symbols = tuple(item.symbol for item in quotes)
        if len(set(symbols)) != len(symbols):
            raise RealtimeDataError("realtime snapshot symbols must be unique")
        if request.symbols is not None and set(symbols) != set(request.symbols):
            raise RealtimeDataError(
                "explicit realtime response symbols must exactly match request"
            )
        if len({item.source for item in quotes}) != 1:
            raise RealtimeDataError("realtime snapshot must use one source")
        if len({item.ingested_at for item in quotes}) != 1:
            raise RealtimeDataError("realtime snapshot must use one ingested_at")

        ordered = tuple(sorted(quotes, key=lambda item: item.symbol))
        if set(request.persist_symbols) - set(symbols):
            raise RealtimeDataError("persist symbols must be returned by provider")
        persisted = tuple(
            item for item in ordered if item.symbol in request.persist_symbols
        )
        if persisted:
            if self._repository is None:
                raise RealtimeCollectionError("persistence repository is required")
            try:
                self._repository.save_realtime_snapshot(persisted)
            except StorageError as exc:
                raise RealtimeCollectionError("realtime persistence failed") from exc

        return RealtimeCaptureResult(
            scope=(
                RealtimeCaptureScope.ALL_MARKET
                if request.symbols is None
                else RealtimeCaptureScope.EXPLICIT_SYMBOLS
            ),
            requested_symbols=request.symbols,
            received_quotes=len(ordered),
            received_symbols=tuple(item.symbol for item in ordered),
            source=ordered[0].source,
            ingested_at=ordered[0].ingested_at,
            source_timestamp_available_quotes=sum(
                item.source_timestamp is not None for item in ordered
            ),
            persist_requested_symbols=request.persist_symbols,
            persisted_quotes=len(persisted),
            persisted_symbols=tuple(item.symbol for item in persisted),
            persistence_performed=bool(persisted),
            quotes=ordered,
        )
