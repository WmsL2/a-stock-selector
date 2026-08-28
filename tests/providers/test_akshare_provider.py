"""Offline contract tests for the concrete AKShare provider."""

from datetime import date

import pandas as pd
import pytest

from stock_selector.models import Board, Exchange
from stock_selector.providers import (
    AKShareProvider,
    DailyBarsRequest,
    ProviderConnectionError,
    ProviderDataError,
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
    """Only the AKShare call boundary translates connection failures."""
    def raise_connection(**kwargs: str) -> pd.DataFrame:
        raise RuntimeError("offline")

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", raise_connection)
    with pytest.raises(ProviderConnectionError):
        AKShareProvider().get_daily_bars(
            DailyBarsRequest(
                symbol="600519.SH",
                start_date=date(2026, 8, 3),
                end_date=date(2026, 8, 7),
            )
        )


def test_get_realtime_quotes_maps_snapshot_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """One full-market fetch maps shares, percentages, and consistent ingestion time."""
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", _realtime_frame)
    provider = AKShareProvider()
    quotes = provider.get_realtime_quotes(RealtimeQuotesRequest())
    assert len(quotes) == 2
    assert quotes[0].volume == 20_000
    assert quotes[0].change_pct == 2.56
    assert {quote.ingested_at for quote in quotes}.__len__() == 1
    assert all(quote.source_timestamp is None for quote in quotes)
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
    """Realtime third-party call failures become provider connection errors."""
    def raise_connection() -> pd.DataFrame:
        raise RuntimeError("offline")

    monkeypatch.setattr(provider_module.ak, "stock_zh_a_spot_em", raise_connection)
    with pytest.raises(ProviderConnectionError):
        AKShareProvider().get_realtime_quotes(RealtimeQuotesRequest())
