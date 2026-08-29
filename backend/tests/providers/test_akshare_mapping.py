"""Offline tests for strict AKShare-to-domain mapping helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from stock_selector.models import AdjustmentType, Board, SecurityStatus
from stock_selector.providers.akshare_mapping import (
    canonical_symbol_from_akshare_code,
    canonical_symbol_from_sina_code,
    lots_to_shares,
    map_sh_instruments,
    map_sina_daily_bars,
    map_sina_realtime_quotes,
    sina_symbol_from_canonical,
    to_optional_float,
)
from stock_selector.providers.errors import ProviderDataError


@pytest.mark.parametrize(
    ("code", "symbol"),
    [
        ("600519", "600519.SH"),
        ("000001", "000001.SZ"),
        ("300750", "300750.SZ"),
        ("688981", "688981.SH"),
        ("430047", "430047.BJ"),
        ("920001", "920001.BJ"),
        (1, "000001.SZ"),
    ],
)
def test_canonical_akshare_symbol_mapping(code: object, symbol: str) -> None:
    """Raw six-digit and integer AKShare codes map to canonical symbols."""
    assert canonical_symbol_from_akshare_code(code) == symbol


@pytest.mark.parametrize("value", ["ABC", "12345", 1.5, float("nan")])
def test_invalid_akshare_codes_are_rejected(value: object) -> None:
    """Malformed, fractional, and non-finite raw codes cannot be normalized."""
    with pytest.raises(ProviderDataError):
        canonical_symbol_from_akshare_code(value)


@pytest.mark.parametrize(
    ("code", "symbol"),
    [
        ("sh600519", "600519.SH"),
        ("sz000001", "000001.SZ"),
        ("sz300750", "300750.SZ"),
        ("bj430047", "430047.BJ"),
        ("bj920001", "920001.BJ"),
    ],
)
def test_canonical_sina_symbol_mapping(code: str, symbol: str) -> None:
    """Only strict lowercase Sina exchange-prefixed codes are accepted."""
    assert canonical_symbol_from_sina_code(code) == symbol


@pytest.mark.parametrize(
    "value", ["600519", "SH600519", "xx600519", "shABC519", "sh60051"],
)
def test_invalid_sina_codes_are_rejected(value: str) -> None:
    """Sina codes are never guessed from incomplete or malformed values."""
    with pytest.raises(ProviderDataError):
        canonical_symbol_from_sina_code(value)


@pytest.mark.parametrize(
    ("symbol", "sina_symbol"),
    [("600519.SH", "sh600519"), ("000001.SZ", "sz000001"), ("300750.SZ", "sz300750")],
)
def test_canonical_symbols_map_to_sina_daily_symbols(symbol: str, sina_symbol: str) -> None:
    """Sina historical symbols are explicit rather than guessed from bare codes."""
    assert sina_symbol_from_canonical(symbol) == sina_symbol


def test_sina_daily_symbol_rejects_bse() -> None:
    """Sina daily fallback does not claim unsupported Beijing history capability."""
    with pytest.raises(ProviderDataError):
        sina_symbol_from_canonical("430047.BJ")


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, "", "-", "--"])
def test_optional_float_normalizes_only_true_missing_values(value: object) -> None:
    """Known AKShare missing markers become None."""
    assert to_optional_float(value) is None


@pytest.mark.parametrize(("value", "expected"), [(12, 12.0), ("3.25", 3.25)])
def test_optional_float_preserves_finite_numeric_values(value: object, expected: float) -> None:
    """Finite numeric cells map to float values."""
    assert to_optional_float(value) == expected


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), "abc"])
def test_optional_float_rejects_invalid_nonmissing_values(value: object) -> None:
    """Invalid nonmissing cells are provider data errors, not missing values."""
    with pytest.raises(ProviderDataError):
        to_optional_float(value)


def test_lot_volume_converts_to_shares() -> None:
    """AKShare lots are normalized to the project's shares unit."""
    assert lots_to_shares(100, required=True) == 10_000


def test_instrument_mapping_marks_st_without_filtering() -> None:
    """Visible ST names remain instruments but carry the ST status."""
    frame = pd.DataFrame(
        {"证券代码": ["600519"], "证券简称": ["*ST 测试"], "上市日期": ["2020-01-01"]}
    )
    instrument = map_sh_instruments(frame, Board.SH_MAIN)[0]
    assert instrument.status is SecurityStatus.ST


def _sina_frame() -> pd.DataFrame:
    """Return a compact Sina snapshot including its time-only source timestamp."""
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
            "成交量": [123_400, float("nan")],
            "成交额": [1_234_000, float("nan")],
            "时间戳": ["10:00:00", "10:00:00"],
        }
    )


def test_sina_realtime_mapping_preserves_share_volume_and_missing_optional_values() -> None:
    """Sina volume is already shares and its time-only timestamp is not combined."""
    ingested_at = datetime(2026, 8, 28, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    quotes, skipped = map_sina_realtime_quotes(_sina_frame(), ingested_at)
    assert skipped == 0
    assert [quote.symbol for quote in quotes] == ["000001.SZ", "600519.SH"]
    maotai = next(quote for quote in quotes if quote.symbol == "600519.SH")
    pingan = next(quote for quote in quotes if quote.symbol == "000001.SZ")
    assert maotai.volume == 123_400
    assert maotai.change_pct == 5.0
    assert maotai.turnover_rate is None
    assert maotai.volume_ratio is None
    assert maotai.source_timestamp is None
    assert pingan.volume is None
    assert pingan.amount is None
    assert {quote.ingested_at for quote in quotes} == {ingested_at}


def test_sina_realtime_mapping_rejects_invalid_values_and_skips_invalid_prices() -> None:
    """Bad numeric cells fail while an all-market invalid price is the one skip case."""
    ingested_at = datetime(2026, 8, 28, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    invalid = _sina_frame()
    invalid["最高"] = invalid["最高"].astype(object)
    invalid.loc[0, "最高"] = "not-a-number"
    with pytest.raises(ProviderDataError):
        map_sina_realtime_quotes(invalid, ingested_at)
    missing_schema = _sina_frame().drop(columns=["成交额"])
    with pytest.raises(ProviderDataError):
        map_sina_realtime_quotes(missing_schema, ingested_at)
    invalid_price = _sina_frame()
    invalid_price.loc[0, "最新价"] = float("nan")
    quotes, skipped = map_sina_realtime_quotes(invalid_price, ingested_at)
    assert skipped == 1
    assert [quote.symbol for quote in quotes] == ["000001.SZ"]


def test_sina_daily_mapping_preserves_share_volume_and_raw_adjustment() -> None:
    """Sina daily volume is already shares and still carries an explicit RAW basis."""
    frame = pd.DataFrame(
        {
            "date": ["2026-08-04", "2026-08-03"],
            "open": [10.0, 9.0],
            "high": [12.0, 11.0],
            "low": [9.0, 8.0],
            "close": [11.0, 10.0],
            "volume": [123_400, 456_700],
            "amount": [1_234_000, 4_567_000],
        }
    )
    bars = map_sina_daily_bars(frame, "600519.SH")
    assert [bar.trade_date.day for bar in bars] == [3, 4]
    assert bars[0].volume == 456_700
    assert bars[0].adjustment is AdjustmentType.RAW
    assert bars[0].source == "akshare:stock_zh_a_daily"


def test_mapping_datetime_is_not_used_as_source_timestamp() -> None:
    """This fixture documents the explicit provider ingestion timestamp convention."""
    assert datetime(2026, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai")).tzinfo is not None
