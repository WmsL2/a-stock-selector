"""Read-only mappings between local domain records and HTTP DTOs."""

from datetime import date

from stock_selector.api.errors import APIResourceNotFound
from stock_selector.api.schemas import (
    DailyBarResponse,
    DailyBarsResponse,
    InstrumentListResponse,
    InstrumentResponse,
    RealtimeLookupResponse,
    RealtimeQuoteResponse,
    StorageStatusResponse,
)
from stock_selector.models import DailyBar, Instrument, RealtimeQuote
from stock_selector.storage import LocalMarketRepository


class ReadOnlyMarketService:
    """Serve local repository contents without provider or write capabilities."""

    def __init__(self, repository: LocalMarketRepository) -> None:
        self._repository = repository

    def storage_status(self) -> StorageStatusResponse:
        """Return normalized local storage coverage information."""
        stats = self._repository.get_stats()
        return StorageStatusResponse(
            instrument_rows=stats.instrument_rows,
            daily_rows=stats.daily_bar_rows,
            daily_symbols=stats.daily_symbols,
            realtime_rows=stats.realtime_quote_rows,
            realtime_symbols=stats.realtime_symbols,
            realtime_snapshots=stats.realtime_snapshots,
            latest_realtime_at=stats.latest_realtime_at,
            disk_usage_bytes=stats.disk_usage_bytes,
            storage_root=str(self._repository.paths.processed_data_dir),
            duckdb_path=str(self._repository.catalog_path),
        )

    def list_instruments(
        self, query: str | None, limit: int, offset: int
    ) -> InstrumentListResponse:
        """Search and page the canonical local instrument master."""
        instruments = self._repository.load_instruments()
        if query is not None:
            normalized = query.casefold()
            instruments = tuple(
                item
                for item in instruments
                if normalized in item.symbol.casefold() or normalized in item.name
            )
        return InstrumentListResponse(
            total=len(instruments),
            limit=limit,
            offset=offset,
            items=[_instrument_response(item) for item in instruments[offset : offset + limit]],
        )

    def get_instrument(self, symbol: str) -> InstrumentResponse:
        """Return one known instrument or a stable not-found error."""
        return _instrument_response(self._find_instrument(symbol))

    def get_daily_bars(
        self,
        symbol: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> DailyBarsResponse:
        """Return the latest requested local bars while retaining ascending order."""
        self._find_instrument(symbol)
        bars = self._repository.load_daily_bars(symbol, start_date, end_date)
        returned = bars[-limit:]
        return DailyBarsResponse(
            symbol=symbol,
            available_rows=len(bars),
            returned_rows=len(returned),
            items=[_daily_bar_response(item) for item in returned],
        )

    def get_latest_realtime(self, symbol: str) -> RealtimeLookupResponse:
        """Look up one quote in the newest locally persisted snapshot."""
        self._find_instrument(symbol)
        snapshot = self._repository.load_latest_realtime_snapshot()
        latest_snapshot_at = snapshot[0].ingested_at if snapshot else None
        quote = next((item for item in snapshot if item.symbol == symbol), None)
        return RealtimeLookupResponse(
            symbol=symbol,
            available=quote is not None,
            latest_snapshot_at=latest_snapshot_at,
            quote=_realtime_quote_response(quote) if quote is not None else None,
        )

    def _find_instrument(self, symbol: str) -> Instrument:
        for instrument in self._repository.load_instruments():
            if instrument.symbol == symbol:
                return instrument
        raise APIResourceNotFound("instrument not found")


def _instrument_response(instrument: Instrument) -> InstrumentResponse:
    return InstrumentResponse(
        symbol=instrument.symbol,
        name=instrument.name,
        exchange=instrument.exchange.value,
        board=instrument.board.value,
        listing_date=instrument.listing_date,
        delisting_date=instrument.delisting_date,
        status=instrument.status.value,
    )


def _daily_bar_response(bar: DailyBar) -> DailyBarResponse:
    return DailyBarResponse(
        symbol=bar.symbol,
        trade_date=bar.trade_date,
        adjustment=bar.adjustment.value,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        amount=bar.amount,
        source=bar.source,
    )


def _realtime_quote_response(quote: RealtimeQuote) -> RealtimeQuoteResponse:
    return RealtimeQuoteResponse(
        symbol=quote.symbol,
        price=quote.price,
        open=quote.open,
        high=quote.high,
        low=quote.low,
        prev_close=quote.prev_close,
        volume=quote.volume,
        amount=quote.amount,
        change_pct=quote.change_pct,
        turnover_rate=quote.turnover_rate,
        volume_ratio=quote.volume_ratio,
        source_timestamp=quote.source_timestamp,
        ingested_at=quote.ingested_at,
        source=quote.source,
    )
