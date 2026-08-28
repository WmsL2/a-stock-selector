"""Concrete AKShare adapter for instruments, daily bars, and real-time quotes."""

import logging
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import cast
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

from stock_selector.models import Board, DailyBar, Instrument, RealtimeQuote
from stock_selector.providers.akshare_mapping import (
    map_bj_instruments,
    map_daily_bars,
    map_realtime_quotes,
    map_sh_instruments,
    map_sina_realtime_quotes,
    map_sz_instruments,
)
from stock_selector.providers.base import (
    DailyMarketDataProvider,
    InstrumentProvider,
    ProviderInfo,
    RealtimeMarketDataProvider,
)
from stock_selector.providers.errors import ProviderConnectionError, ProviderDataError
from stock_selector.providers.requests import (
    DailyBarsRequest,
    RealtimeQuotesRequest,
)

_LOGGER = logging.getLogger("stock_selector.providers.akshare")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class AKShareProvider(
    InstrumentProvider,
    DailyMarketDataProvider,
    RealtimeMarketDataProvider,
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
        """Fetch original, unadjusted daily bars and normalize lot volume to shares."""
        raw_code = request.symbol.split(".", maxsplit=1)[0]
        try:
            frame = ak.stock_zh_a_hist(
                symbol=raw_code,
                period="daily",
                start_date=request.start_date.strftime("%Y%m%d"),
                end_date=request.end_date.strftime("%Y%m%d"),
                adjust="",
            )
        except Exception as exc:
            raise ProviderConnectionError(
                "akshare", "stock_zh_a_hist", "daily history request failed"
            ) from exc
        return map_daily_bars(frame, request.symbol)

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
