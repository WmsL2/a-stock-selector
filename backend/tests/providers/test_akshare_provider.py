"""Offline contract tests for the concrete AKShare provider."""

import logging
from datetime import date

import pandas as pd
import pytest

from stock_selector.models import AdjustmentType, Board, Exchange
from stock_selector.providers import (
    AKShareProvider,
    DailyBarsRequest,
    ProviderConnectionError,
    ProviderDataError,
    ProviderNotSupportedError,
    RealtimeQuotesRequest,
)
from stock_selector.providers import akshare_provider as provider_module


def _instrument_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build one offline listing frame for every supported exchange board."""
    sh_main = pd.DataFrame(
        {"证券代码": ["600519"], "证券简称": ["贵州茅台"], "上市日期": ["2001-08-27"]}
    )
    star = pd.DataFrame(
        {"证券代码": ["688981"], "证券简称": ["中芯国际"], "上市日期": ["2020-07-16"]}
    )
    sz = pd.DataFrame(
        {
            "A股代码": ["000001", "300750"],
            "A股简称": ["平安银行", "宁德时代"],
            "A股上市日期": ["1991-04-03", "2018-06-11"],
            "板块": ["主板", "创业板"],
        }
    )
    bj = pd.DataFrame(
        {"证券代码": ["430047"], "证券简称": ["诺思兰德"], "上市日期": ["2014-01-24"]}
    )
    return sh_main, star, sz, bj


def _patch_instrument_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every listing endpoint with deterministic offline frames."""
    sh_main, star, sz, bj = _instrument_frames()
    monkeypatch.setattr(
        provider_module.ak,
        "stock_info_sh_name_code",
        lambda symbol: sh_main if symbol == "主板A股" else star,
    )
    monkeypatch.setattr(provider_module.ak, "stock_info_sz_name_code", lambda symbol: sz)
    monkeypatch.setattr(provider_module.ak, "stock_info_bj_name_code", lambda: bj)


def _daily_frame() -> pd.DataFrame:
    """Return deliberately unsorted daily data in AKShare's raw units."""
    return pd.DataFrame(
        {
            "日期": ["2026-08-04", "2026-08-03"],
            "开盘": [10.0, 9.0],
            "最高": [12.0, 11.0],
            "最低": [9.0, 8.0],
            "收盘": [11.0, 10.0],
            "成交量": [100, 200],
            "成交额": [110_000.0, 200_000.0],
        }
    )


def _sina_daily_frame() -> pd.DataFrame:
    """Return deliberately unsorted Sina daily data in its share-volume unit."""
    return pd.DataFrame(
        {
            "date": ["2026-08-04", "2026-08-03"],
            "open": [10.0, 9.0],
            "high": [12.0, 11.0],
            "low": [9.0, 8.0],
            "close": [11.0, 10.0],
            "volume": [123_400, 456_700],
            "amount": [1_234_000.0, 4_567_000.0],
        }
    )


def _realtime_frame() -> pd.DataFrame:
    """Return a minimal strict-schema real-time snapshot in AKShare raw units."""
    return pd.DataFrame(
        {
            "代码": ["600519", "000001"],
            "最新价": [10.0, 20.0],
            "今开": [9.0, 19.0],
            "最高": [11.0, 21.0],
            "最低": [8.0, 18.0],
            "昨收": [9.5, 19.5],
            "成交量": [100, 200],
            "成交额": [100_000.0, 400_000.0],
            "涨跌幅": [3.25, 2.56],
            "换手率": [1.2, 0.8],
            "量比": [1.1, 0.9],
        }
    )


def _sina_realtime_frame() -> pd.DataFrame:
    """Return a Sina-style snapshot, whose volume is already in shares."""
    return pd.DataFrame(
        {
            "代码": ["sh600519", "sz000001"],
            "名称": ["贵州茅台", "平安银行"],
            "最新价": [10.0, 20.0],
            "涨跌额": [0.5, 0.2],
            "涨跌幅": [5.0, 1.01],
            "买入": [9.9, 19.9],
            "卖出": [10.1, 20.1],
            "昨收": [9.5, 19.8],
            "今开": [9.7, 19.7],
            "最高": [10.2, 20.3],
            "最低": [9.6, 19.5],
            "成交量": [123_400, 456_700],
            "成交额": [1_234_000, 9_134_000],
            "时间戳": ["10:00:00", "10:00:00"],
        }
    )


def test_get_instruments_maps_all_supported_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Four AKShare listing calls map to sorted canonical instrument records."""
    _patch_instrument_calls(monkeypatch)
    instruments = AKShareProvider().get_instruments()
    assert [instrument.symbol for instrument in instruments] == sorted(
        instrument.symbol for instrument in instruments
    )
    assert {(instrument.exchange, instrument.board) for instrument in instruments} == {
        (Exchange.SSE, Board.SH_MAIN),
        (Exchange.SSE, Board.STAR),
        (Exchange.SZSE, Board.SZ_MAIN),
        (Exchange.SZSE, Board.CHINEXT),
        (Exchange.BSE, Board.BSE),
    }
    assert instruments[0].listing_date == date(1991, 4, 3)


@pytest.mark.parametrize("scenario", ["missing", "empty", "unknown_board", "duplicate"])
def test_get_instruments_rejects_bad_listing_data(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """Schema, empty-frame, board, and duplicate problems are provider data errors."""
    sh_main, star, sz, bj = _instrument_frames()
    if scenario == "missing":
        sh_main = sh_main.drop(columns=["上市日期"])
    elif scenario == "empty":
        star = star.iloc[0:0]
    elif scenario == "unknown_board":
        sz.loc[0, "板块"] = "未知板块"
    else:
        star.loc[0, "证券代码"] = "600519"
    monkeypatch.setattr(
        provider_module.ak,
        "stock_info_sh_name_code",
        lambda symbol: sh_main if symbol == "主板A股" else star,
    )
    monkeypatch.setattr(provider_module.ak, "stock_info_sz_name_code", lambda symbol: sz)
    monkeypatch.setattr(provider_module.ak, "stock_info_bj_name_code", lambda: bj)
    with pytest.raises(ProviderDataError):
        AKShareProvider().get_instruments()


def test_get_daily_bars_maps_and_normalizes_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Daily mapping keeps original prices, normalizes lots, and orders dates."""
    captured: dict[str, str] = {}

    def fake_history(**kwargs: str) -> pd.DataFrame:
        captured.update(kwargs)
        return _daily_frame()

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", fake_history)
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_daily",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("fallback must not be called")),
    )
    bars = AKShareProvider().get_daily_bars(
        DailyBarsRequest(
            symbol="600519.SH", start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
    )
    assert captured == {
        "symbol": "600519",
        "period": "daily",
        "start_date": "20260803",
        "end_date": "20260807",
        "adjust": "",
    }
    assert [bar.trade_date for bar in bars] == [date(2026, 8, 3), date(2026, 8, 4)]
    assert bars[0].volume == 20_000
    assert bars[0].amount == 200_000
    assert bars[0].source == "akshare:stock_zh_a_hist"
    assert bars[0].adjustment is AdjustmentType.RAW


def test_get_daily_bars_handles_empty_and_invalid_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty date ranges are valid but malformed bars are not silently skipped."""
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: pd.DataFrame())
    request = DailyBarsRequest(
        symbol="600519.SH", start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
    )
    assert AKShareProvider().get_daily_bars(request) == ()
    invalid = _daily_frame()
    invalid.loc[0, "收盘"] = float("nan")
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: invalid)
    with pytest.raises(ProviderDataError):
        AKShareProvider().get_daily_bars(request)


def test_get_daily_bars_translates_third_party_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection failure in both daily sources becomes one provider connection error."""
    def raise_connection(**kwargs: str) -> pd.DataFrame:
        raise RuntimeError("offline")

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", raise_connection)
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", raise_connection)
    with pytest.raises(ProviderConnectionError, match="primary and fallback unavailable"):
        AKShareProvider().get_daily_bars(
            DailyBarsRequest(
                symbol="600519.SH",
                start_date=date(2026, 8, 3),
                end_date=date(2026, 8, 7),
            )
        )


def test_get_daily_bars_falls_back_to_sina_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sina is used only when the Eastmoney daily request boundary is unavailable."""
    def raise_connection(**kwargs: str) -> pd.DataFrame:
        raise RuntimeError("Eastmoney offline")

    captured: dict[str, str] = {}

    def fake_sina_history(**kwargs: str) -> pd.DataFrame:
        captured.update(kwargs)
        return _sina_daily_frame()

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", raise_connection)
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", fake_sina_history)
    bars = AKShareProvider().get_daily_bars(
        DailyBarsRequest(
            symbol="600519.SH", start_date=date(2026, 8, 3), end_date=date(2026, 8, 7)
        )
    )
    assert captured == {
        "symbol": "sh600519",
        "start_date": "20260803",
        "end_date": "20260807",
        "adjust": "",
    }
    assert [bar.trade_date for bar in bars] == [date(2026, 8, 3), date(2026, 8, 4)]
    assert bars[0].volume == 456_700
    assert bars[0].amount == 4_567_000
    assert bars[0].source == "akshare:stock_zh_a_daily"
    assert bars[0].adjustment is AdjustmentType.RAW


def test_get_daily_bars_does_not_fallback_for_primary_data_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A primary schema problem must remain visible instead of activating fallback."""
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_hist",
        lambda **kwargs: _daily_frame().drop(columns=["成交额"]),
    )
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_daily",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("fallback must not be called")),
    )
    with pytest.raises(ProviderDataError):
        AKShareProvider().get_daily_bars(
            DailyBarsRequest(
                symbol="600519.SH",
                start_date=date(2026, 8, 3),
                end_date=date(2026, 8, 7),
            )
        )


def test_get_daily_bars_rejects_nonraw_adjustment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Current provider capability is explicit: RAW only, never silently substituted."""
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_hist",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider must not fetch")),
    )
    with pytest.raises(ProviderNotSupportedError):
        AKShareProvider().get_daily_bars(
            DailyBarsRequest(
                symbol="600519.SH",
                start_date=date(2026, 8, 3),
                end_date=date(2026, 8, 7),
                adjustment=AdjustmentType.QFQ,
            )
        )


def test_get_realtime_quotes_maps_snapshot_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """One full-market fetch maps shares, percentages, and consistent ingestion time."""
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", _realtime_frame)
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_spot",
        lambda: (_ for _ in ()).throw(AssertionError("fallback must not be called")),
    )
    provider = AKShareProvider()
    quotes = provider.get_realtime_quotes(RealtimeQuotesRequest())
    assert len(quotes) == 2
    assert quotes[0].volume == 20_000
    assert quotes[0].change_pct == 2.56
    assert {quote.ingested_at for quote in quotes}.__len__() == 1
    assert all(quote.source_timestamp is None for quote in quotes)
    assert all(quote.source == "akshare:stock_zh_a_spot_em" for quote in quotes)
    requested = provider.get_realtime_quotes(RealtimeQuotesRequest(symbols=("600519.SH",)))
    assert requested[0].symbol == "600519.SH"


def test_get_realtime_quotes_handles_skips_and_data_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only all-market invalid prices are skipped; schema and explicit misses fail."""
    missing_price = _realtime_frame()
    missing_price.loc[0, "最新价"] = float("nan")
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", lambda: missing_price)
    provider = AKShareProvider()
    assert len(provider.get_realtime_quotes(RealtimeQuotesRequest())) == 1
    with pytest.raises(ProviderDataError):
        provider.get_realtime_quotes(RealtimeQuotesRequest(symbols=("600519.SH",)))
    with pytest.raises(ProviderDataError):
        provider.get_realtime_quotes(RealtimeQuotesRequest(symbols=("300750.SZ",)))
    missing_column = _realtime_frame().drop(columns=["量比"])
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", lambda: missing_column)
    with pytest.raises(ProviderDataError):
        provider.get_realtime_quotes(RealtimeQuotesRequest())
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", lambda: pd.DataFrame())
    with pytest.raises(ProviderDataError):
        provider.get_realtime_quotes(RealtimeQuotesRequest())


def test_get_realtime_quotes_translates_third_party_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure in both realtime sources becomes one provider connection error."""
    def raise_connection() -> pd.DataFrame:
        raise RuntimeError("offline")

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", raise_connection)
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot", raise_connection)
    with pytest.raises(ProviderConnectionError, match="primary and fallback unavailable"):
        AKShareProvider().get_realtime_quotes(RealtimeQuotesRequest())


def test_get_realtime_quotes_falls_back_to_sina_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sina is used only after the Eastmoney request boundary fails."""
    def raise_connection() -> pd.DataFrame:
        raise RuntimeError("Eastmoney offline")

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", raise_connection)
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot", _sina_realtime_frame)
    caplog.set_level(logging.WARNING, logger="stock_selector.providers.akshare")
    quotes = AKShareProvider().get_realtime_quotes(RealtimeQuotesRequest())
    assert [quote.symbol for quote in quotes] == ["000001.SZ", "600519.SH"]
    maotai = next(quote for quote in quotes if quote.symbol == "600519.SH")
    assert maotai.source == "akshare:stock_zh_a_spot"
    assert maotai.volume == 123_400
    assert maotai.change_pct == 5.0
    assert maotai.turnover_rate is None
    assert maotai.volume_ratio is None
    assert maotai.source_timestamp is None
    assert {quote.ingested_at for quote in quotes}.__len__() == 1
    assert [record.message for record in caplog.records] == [
        "Eastmoney realtime snapshot unavailable; falling back to Sina"
    ]


def test_get_realtime_quotes_does_not_fallback_for_primary_data_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful primary response with a bad schema must not be masked by fallback."""
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_spot_em",
        lambda: _realtime_frame().drop(columns=["量比"]),
    )
    monkeypatch.setattr(
        provider_module.ak,
        "stock_zh_a_spot",
        lambda: (_ for _ in ()).throw(AssertionError("fallback must not be called")),
    )
    with pytest.raises(ProviderDataError):
        AKShareProvider().get_realtime_quotes(RealtimeQuotesRequest())
