"""Concrete AKShare adapter for instruments, daily bars, and real-time quotes."""

import logging
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import cast
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

from stock_selector.models import (
    AdjustmentType,
    Board,
    DailyBar,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.providers.akshare_fundamentals_mapping import (
    map_financial_records,
    map_industry_records,
    map_valuation_records,
)
from stock_selector.providers.akshare_mapping import (
    map_bj_instruments,
    map_current_risk_states,
    map_daily_bars,
    map_realtime_quotes,
    map_sh_instruments,
    map_sina_current_risk_states,
    map_sina_daily_bars,
    map_sina_realtime_quotes,
    map_sz_instruments,
    sina_symbol_from_canonical,
)
from stock_selector.providers.base import (
    CurrentRiskStateProvider,
    DailyMarketDataProvider,
    FundamentalDataProvider,
    IndustryDataProvider,
    InstrumentProvider,
    ProviderInfo,
    RealtimeMarketDataProvider,
)
from stock_selector.providers.errors import (
    ProviderConnectionError,
    ProviderDataError,
    ProviderNotSupportedError,
)
from stock_selector.providers.requests import (
    CurrentRiskStatesRequest,
    DailyBarsRequest,
    FinancialRecordsRequest,
    IndustryRecordsRequest,
    RealtimeQuotesRequest,
    ValuationRecordsRequest,
)
from stock_selector.risk import DatedRiskState

_LOGGER = logging.getLogger("stock_selector.providers.akshare")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _system_shanghai_now() -> datetime:
    """Read the concrete provider-boundary current instant once per risk request."""
    return datetime.now(tz=_SHANGHAI)


class AKShareProvider(
    InstrumentProvider,
    DailyMarketDataProvider,
    RealtimeMarketDataProvider,
    FundamentalDataProvider,
    IndustryDataProvider,
    CurrentRiskStateProvider,
):
    """AKShare adapter that exposes only normalized domain-model batches."""

    @property
    def info(self) -> ProviderInfo:
        """Return AKShare identity with installed package version when available."""
        try:
            installed_version = version("akshare")
        except PackageNotFoundError:
            installed_version = None
        return ProviderInfo(name="akshare", version=installed_version)

    def get_instruments(self) -> tuple[Instrument, ...]:
        """Fetch and normalize all supported Shanghai, Shenzhen, and Beijing listings."""
        sh_main = self._fetch_sh_list("主板A股")
        star = self._fetch_sh_list("科创板")
        sz = self._fetch_sz_list()
        bj = self._fetch_bj_list()
        instruments = (
            *map_sh_instruments(sh_main, Board.SH_MAIN),
            *map_sh_instruments(star, Board.STAR),
            *map_sz_instruments(sz),
            *map_bj_instruments(bj),
        )
        symbols = [instrument.symbol for instrument in instruments]
        if len(set(symbols)) != len(symbols):
            raise ProviderDataError(
                "akshare", "get_instruments", "duplicate canonical symbols returned"
            )
        return tuple(sorted(instruments, key=lambda instrument: instrument.symbol))

    def get_daily_bars(self, request: DailyBarsRequest) -> tuple[DailyBar, ...]:
        """Fetch RAW daily bars, falling back to Sina only after primary connectivity loss."""
        if request.adjustment is not AdjustmentType.RAW:
            raise ProviderNotSupportedError(
                "akshare", "get_daily_bars", "only raw daily adjustment is supported"
            )
        try:
            frame = self._fetch_daily_em(request)
        except ProviderConnectionError:
            _LOGGER.warning("Eastmoney daily history unavailable; falling back to Sina")
            try:
                sina_symbol = sina_symbol_from_canonical(request.symbol)
            except ProviderDataError as exc:
                raise ProviderNotSupportedError(
                    "akshare", "stock_zh_a_daily", "Sina daily fallback supports SH and SZ only"
                ) from exc
            try:
                frame = self._fetch_daily_sina(request, sina_symbol)
            except ProviderConnectionError as fallback_error:
                raise ProviderConnectionError(
                    "akshare", "get_daily_bars", "primary and fallback unavailable"
                ) from fallback_error
            return map_sina_daily_bars(frame, request.symbol)
        return map_daily_bars(frame, request.symbol)

    def _fetch_daily_em(self, request: DailyBarsRequest) -> pd.DataFrame:
        """Call the primary Eastmoney daily endpoint at the third-party boundary."""
        raw_code = request.symbol.split(".", maxsplit=1)[0]
        try:
            return cast(
                pd.DataFrame,
                ak.stock_zh_a_hist(
                    symbol=raw_code,
                    period="daily",
                    start_date=request.start_date.strftime("%Y%m%d"),
                    end_date=request.end_date.strftime("%Y%m%d"),
                    adjust="",
                ),
            )
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_zh_a_hist", "daily history request failed"
            ) from exc

    def _fetch_daily_sina(self, request: DailyBarsRequest, symbol: str) -> pd.DataFrame:
        """Call the Sina RAW daily endpoint only after primary connection failure."""
        try:
            return cast(
                pd.DataFrame,
                ak.stock_zh_a_daily(
                    symbol=symbol,
                    start_date=request.start_date.strftime("%Y%m%d"),
                    end_date=request.end_date.strftime("%Y%m%d"),
                    adjust="",
                ),
            )
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_zh_a_daily", "Sina daily history request failed"
            ) from exc

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        """Fetch one full-market snapshot and optionally filter to requested symbols."""
        try:
            frame = self._fetch_realtime_em()
        except ProviderConnectionError:
            _LOGGER.warning(
                "Eastmoney realtime snapshot unavailable; falling back to Sina"
            )
            try:
                frame = self._fetch_realtime_sina()
            except ProviderConnectionError as fallback_error:
                raise ProviderConnectionError(
                    "akshare",
                    "get_realtime_quotes",
                    "primary and fallback unavailable",
                ) from fallback_error
            ingested_at = datetime.now(tz=_SHANGHAI)
            quotes, skipped_without_price = map_sina_realtime_quotes(frame, ingested_at)
            _LOGGER.info("Using Sina realtime snapshot fallback")
        else:
            ingested_at = datetime.now(tz=_SHANGHAI)
            quotes, skipped_without_price = map_realtime_quotes(frame, ingested_at)
        if request.symbols is None:
            if skipped_without_price:
                _LOGGER.warning(
                    "Skipped %s realtime rows without valid positive price",
                    skipped_without_price,
                )
            return quotes
        quotes_by_symbol = {quote.symbol: quote for quote in quotes}
        missing = [symbol for symbol in request.symbols if symbol not in quotes_by_symbol]
        if missing:
            raise ProviderDataError(
                "akshare",
                "get_realtime_quotes",
                f"requested symbols unavailable or invalid: {', '.join(missing)}",
            )
        return tuple(quotes_by_symbol[symbol] for symbol in request.symbols)

    def get_current_risk_states(
        self, request: CurrentRiskStatesRequest
    ) -> tuple[DatedRiskState, ...]:
        """Fetch one raw current-market snapshot for complete structural risk evidence."""
        observed_at = _system_shanghai_now()
        if request.as_of != observed_at.date():
            raise ProviderNotSupportedError(
                "akshare",
                "get_current_risk_states",
                "current-risk collection does not support historical as_of dates",
            )
        try:
            frame = self._fetch_realtime_em()
        except ProviderConnectionError:
            _LOGGER.warning(
                "Eastmoney current-risk snapshot unavailable; falling back to Sina"
            )
            try:
                frame = self._fetch_realtime_sina()
            except ProviderConnectionError as fallback_error:
                raise ProviderConnectionError(
                    "akshare",
                    "get_current_risk_states",
                    "primary and fallback unavailable",
                ) from fallback_error
            return map_sina_current_risk_states(
                frame, request.symbols, request.as_of, observed_at
            )
        return map_current_risk_states(frame, request.symbols, request.as_of, observed_at)

    def _fetch_realtime_em(self) -> pd.DataFrame:
        """Call the primary Eastmoney realtime endpoint at the provider boundary."""
        try:
            return cast(pd.DataFrame, ak.stock_zh_a_spot_em())
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_zh_a_spot_em", "realtime snapshot request failed"
            ) from exc

    def _fetch_realtime_sina(self) -> pd.DataFrame:
        """Call the Sina realtime endpoint only after primary connectivity failure."""
        try:
            return cast(pd.DataFrame, ak.stock_zh_a_spot())
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_zh_a_spot", "Sina realtime snapshot request failed"
            ) from exc

    def _fetch_sh_list(self, board: str) -> pd.DataFrame:
        """Call one concrete Shanghai listing endpoint at the third-party boundary."""
        try:
            return cast(pd.DataFrame, ak.stock_info_sh_name_code(symbol=board))
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_info_sh_name_code", "Shanghai listing request failed"
            ) from exc

    def _fetch_sz_list(self) -> pd.DataFrame:
        """Call the concrete Shenzhen listing endpoint at the third-party boundary."""
        try:
            return cast(pd.DataFrame, ak.stock_info_sz_name_code(symbol="A股列表"))
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_info_sz_name_code", "Shenzhen listing request failed"
            ) from exc

    def _fetch_bj_list(self) -> pd.DataFrame:
        """Call the concrete Beijing listing endpoint at the third-party boundary."""
        try:
            return cast(pd.DataFrame, ak.stock_info_bj_name_code())
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_info_bj_name_code", "Beijing listing request failed"
            ) from exc

    def get_financial_records(
        self, request: FinancialRecordsRequest
    ) -> tuple[FinancialRecord, ...]:
        """Fetch only financial rows with provider-supplied notice dates."""
        records: list[FinancialRecord] = []
        for symbol in request.symbols:
            try:
                frame = cast(
                    pd.DataFrame,
                    ak.stock_financial_analysis_indicator_em(
                        symbol=symbol, indicator="按报告期"
                    ),
                )
            except Exception as exc:
                raise ProviderConnectionError(
                    "akshare", "stock_financial_analysis_indicator_em", "financial request failed"
                ) from exc
            mapped = map_financial_records(frame, symbol)
            records.extend(
                item
                for item in mapped
                if (request.start_period is None or item.report_period >= request.start_period)
                and (request.end_period is None or item.report_period <= request.end_period)
            )
        return tuple(sorted(records, key=lambda item: (item.symbol, item.report_period, item.available_at)))

    def get_valuation_records(
        self, request: ValuationRecordsRequest
    ) -> tuple[ValuationRecord, ...]:
        """Fetch dated Baidu valuation history; unsupported fields remain null."""
        records: list[ValuationRecord] = []
        for symbol in request.symbols:
            raw_symbol = symbol.split(".", maxsplit=1)[0]
            frames: dict[str, pd.DataFrame] = {}
            for indicator in ("市盈率(TTM)", "市净率", "市现率", "总市值"):
                frames[indicator] = self._fetch_valuation_indicator(raw_symbol, indicator)
            records.extend(
                item
                for item in map_valuation_records(frames, symbol)
                if request.as_of is None or item.as_of <= request.as_of
            )
        return tuple(sorted(records, key=lambda item: (item.symbol, item.as_of)))

    def _fetch_valuation_indicator(
        self, raw_symbol: str, indicator: str
    ) -> pd.DataFrame:
        """Fetch one required valuation indicator with one bounded immediate retry."""
        try:
            return cast(
                pd.DataFrame,
                ak.stock_zh_valuation_baidu(
                    symbol=raw_symbol, indicator=indicator, period="全部"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - third-party request boundary
            _LOGGER.warning(
                "valuation indicator request failed; retrying once; symbol=%s indicator=%s error=%s",
                raw_symbol,
                indicator,
                type(exc).__name__,
            )
        try:
            return cast(
                pd.DataFrame,
                ak.stock_zh_valuation_baidu(
                    symbol=raw_symbol, indicator=indicator, period="全部"
                ),
            )
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare",
                "stock_zh_valuation_baidu",
                f"valuation indicator {indicator} request failed after 2 attempts",
            ) from exc

    def get_industry_records(
        self, request: IndustryRecordsRequest
    ) -> tuple[IndustryRecord, ...]:
        """Fetch CNInfo industry change events with provider-declared change dates."""
        records: list[IndustryRecord] = []
        end_date = request.as_of.strftime("%Y%m%d") if request.as_of is not None else datetime.now(_SHANGHAI).strftime("%Y%m%d")
        for symbol in request.symbols:
            try:
                frame = cast(
                    pd.DataFrame,
                    ak.stock_industry_change_cninfo(
                        symbol=symbol.split(".", maxsplit=1)[0],
                        start_date="19900101",
                        end_date=end_date,
                    ),
                )
            except Exception as exc:
                raise ProviderConnectionError(
                    "akshare", "stock_industry_change_cninfo", "industry request failed"
                ) from exc
            mapped = map_industry_records(frame, symbol)
            records.extend(
                item
                for item in mapped
                if request.as_of is None
                or item.effective_from <= request.as_of
            )
        return tuple(sorted(records, key=lambda item: (item.symbol, item.classification, item.effective_from)))
