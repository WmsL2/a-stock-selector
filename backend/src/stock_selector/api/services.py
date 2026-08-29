"""Read-only mappings between local domain records and HTTP DTOs."""

from datetime import date, datetime

from stock_selector.api.errors import APIResourceNotFound
from stock_selector.api.schemas import (
    DailyBarResponse,
    DailyBarsResponse,
    DailyStatusResponse,
    FinancialRecordResponse,
    FinancialRecordsResponse,
    FundamentalsStatusResponse,
    IndustryRecordResponse,
    IndustryRecordsResponse,
    InstrumentListResponse,
    InstrumentResponse,
    QualityStatusResponse,
    RealtimeLookupResponse,
    RealtimeQuoteResponse,
    StorageStatusResponse,
    UniverseBoardCountsResponse,
    UniverseExclusionCountsResponse,
    UniverseStatusResponse,
    ValuationLookupResponse,
    ValuationRecordResponse,
)
from stock_selector.config.models import Settings
from stock_selector.models import (
    Board,
    DailyBar,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.quality import CurrentQualityService
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe import CurrentUniverseService, UniverseExclusionReason


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
            earliest_daily_trade_date=stats.earliest_daily_trade_date,
            latest_daily_trade_date=stats.latest_daily_trade_date,
            realtime_rows=stats.realtime_quote_rows,
            realtime_symbols=stats.realtime_symbols,
            realtime_snapshots=stats.realtime_snapshots,
            latest_realtime_at=stats.latest_realtime_at,
            risk_state_rows=stats.risk_state_rows,
            risk_state_dates=stats.risk_state_dates,
            latest_risk_state_date=stats.latest_risk_state_date,
            disk_usage_bytes=stats.disk_usage_bytes,
            storage_root=str(self._repository.paths.processed_data_dir),
            duckdb_path=str(self._repository.catalog_path),
        )

    def daily_status(self) -> DailyStatusResponse:
        """Report actual RAW daily storage coverage without completeness claims."""
        stats = self._repository.get_stats()
        return DailyStatusResponse(
            stored_symbols=stats.daily_symbols,
            stored_rows=stats.daily_bar_rows,
            earliest_trade_date=stats.earliest_daily_trade_date,
            latest_trade_date=stats.latest_daily_trade_date,
            adjustment_basis="raw",
            corporate_action_adjusted=False,
            full_market_completeness_verified=False,
            trading_calendar_gap_check_applied=False,
        )

    def fundamentals_status(self) -> FundamentalsStatusResponse:
        stats = self._repository.get_stats()
        return FundamentalsStatusResponse(
            financial_symbols=stats.financial_symbols,
            financial_rows=stats.financial_rows,
            latest_financial_available_at=stats.latest_financial_available_at,
            valuation_symbols=stats.valuation_symbols,
            valuation_rows=stats.valuation_rows,
            latest_valuation_at=stats.latest_valuation_at,
            industry_symbols=stats.industry_symbols,
            industry_rows=stats.industry_rows,
            financial_point_in_time_safe=True,
            valuation_history_supported=True,
            industry_history_supported=True,
        )

    def quality_status(self, settings: Settings) -> QualityStatusResponse:
        """Return conservative current quality status using only local data."""
        status = CurrentQualityService(self._repository, settings).build_current()
        return QualityStatusResponse(
            as_of=status.as_of,
            structural_instruments=status.structural_instruments,
            risk_state_records=status.risk_state_records,
            risk_complete_instruments=status.risk_complete_instruments,
            risk_coverage_ratio=status.risk_coverage_ratio,
            risk_filter_ready=status.risk_filter_ready,
            risk_eligible_instruments=status.risk_eligible_instruments,
            latest_realtime_at=status.latest_realtime_at,
            realtime_age_seconds=status.realtime_age_seconds,
            realtime_freshness=status.realtime_freshness.value,
        )

    def universe_status(self, settings: Settings) -> UniverseStatusResponse:
        """Return current structural coverage without claiming historical completeness."""
        snapshot = CurrentUniverseService(self._repository, settings).build_current()
        instruments = self._repository.load_instruments()
        included_symbols = set(snapshot.members)
        board_counts = {
            "sh_main": 0,
            "sz_main": 0,
            "chinext": 0,
            "star": 0,
            "bse": 0,
        }
        board_keys = {
            Board.SH_MAIN: "sh_main",
            Board.SZ_MAIN: "sz_main",
            Board.CHINEXT: "chinext",
            Board.STAR: "star",
            Board.BSE: "bse",
        }
        for instrument in instruments:
            if instrument.symbol in included_symbols:
                board_counts[board_keys[instrument.board]] += 1
        exclusion_counts = {reason.value: 0 for reason in UniverseExclusionReason}
        for decision in snapshot.decisions:
            for reason in decision.reasons:
                exclusion_counts[reason.value] += 1
        return UniverseStatusResponse(
            as_of=snapshot.as_of,
            data_scope="current_instrument_master",
            input_instruments=snapshot.input_count,
            included_instruments=len(snapshot.members),
            excluded_instruments=snapshot.input_count - len(snapshot.members),
            boards=UniverseBoardCountsResponse(**board_counts),
            exclusions=UniverseExclusionCountsResponse(**exclusion_counts),
            risk_filters_applied=False,
            historical_survivorship_safe=False,
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

    def get_financials(
        self, symbol: str, as_of: datetime | None
    ) -> FinancialRecordsResponse:
        self._find_instrument(symbol)
        items = (
            self._repository.load_latest_financials_as_of(symbol, as_of)
            if as_of is not None
            else self._repository.load_financial_records(symbol)
        )
        return FinancialRecordsResponse(
            symbol=symbol,
            available=bool(items),
            as_of=as_of,
            items=[_financial_record_response(item) for item in items],
        )

    def get_valuation(
        self, symbol: str, as_of: datetime | None
    ) -> ValuationLookupResponse:
        self._find_instrument(symbol)
        if as_of is not None:
            record = self._repository.load_latest_valuation_as_of(symbol, as_of)
        else:
            records = self._repository.load_valuation_records(symbol)
            record = records[-1] if records else None
        return ValuationLookupResponse(
            symbol=symbol,
            available=record is not None,
            requested_as_of=as_of,
            record=_valuation_record_response(record) if record is not None else None,
        )

    def get_industry(self, symbol: str, as_of: date | None) -> IndustryRecordsResponse:
        self._find_instrument(symbol)
        items = self._repository.load_industry_records(symbol, as_of=as_of)
        return IndustryRecordsResponse(
            symbol=symbol,
            available=bool(items),
            as_of=as_of,
            items=[_industry_record_response(item) for item in items],
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


def _financial_record_response(record: FinancialRecord) -> FinancialRecordResponse:
    return FinancialRecordResponse(**record.model_dump())


def _valuation_record_response(record: ValuationRecord) -> ValuationRecordResponse:
    return ValuationRecordResponse(**record.model_dump())


def _industry_record_response(record: IndustryRecord) -> IndustryRecordResponse:
    return IndustryRecordResponse(**record.model_dump())
