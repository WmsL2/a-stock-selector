"""Strict conversion from AKShare DataFrames to internal domain models."""

import math
from datetime import date, datetime
from numbers import Integral, Real
from typing import Final

import pandas as pd
from pydantic import ValidationError

from stock_selector.models import (
    AdjustmentType,
    Board,
    DailyBar,
    Exchange,
    Instrument,
    RealtimeQuote,
    SecurityStatus,
)
from stock_selector.models.common import validate_symbol
from stock_selector.providers.errors import ProviderDataError

_MISSING_TEXT: Final[frozenset[str]] = frozenset({"", "-", "--"})
_DAILY_COLUMNS: Final[tuple[str, ...]] = (
    "日期",
    "开盘",
    "最高",
    "最低",
    "收盘",
    "成交量",
    "成交额",
)
_SINA_DAILY_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
_REALTIME_COLUMNS: Final[tuple[str, ...]] = (
    "代码",
    "最新价",
    "今开",
    "最高",
    "最低",
    "昨收",
    "成交量",
    "成交额",
    "涨跌幅",
    "换手率",
    "量比",
)
_SINA_REALTIME_COLUMNS: Final[tuple[str, ...]] = (
    "代码",
    "最新价",
    "今开",
    "最高",
    "最低",
    "昨收",
    "成交量",
    "成交额",
    "涨跌幅",
)


def normalize_akshare_code(value: object) -> str:
    """Normalize a strict AKShare code while preserving leading zero semantics."""
    if isinstance(value, bool):
        raise _data_error("normalize_code", "boolean is not a stock code")
    if isinstance(value, Integral):
        code = int(value)
        if not 0 <= code <= 999999:
            raise _data_error("normalize_code", "integer code must fit six digits")
        return f"{code:06d}"
    if isinstance(value, str) and len(value) == 6 and value.isascii() and value.isdigit():
        return value
    raise _data_error("normalize_code", "code must be a six-digit string or integer")


def canonical_symbol_from_akshare_code(value: object) -> str:
    """Convert a raw AKShare code to the project's canonical exchange symbol."""
    code = normalize_akshare_code(value)
    if code.startswith("6"):
        suffix = "SH"
    elif code.startswith(("0", "3")):
        suffix = "SZ"
    elif code.startswith(("4", "8", "9")):
        suffix = "BJ"
    else:
        raise _data_error("canonical_symbol", f"unsupported code prefix: {code}")
    return f"{code}.{suffix}"


def canonical_symbol_from_sina_code(value: object) -> str:
    """Convert one strict lowercase Sina exchange-prefixed code to a symbol."""
    if not isinstance(value, str) or len(value) != 8:
        raise _data_error("canonical_sina_symbol", "code must be an eight-character string")
    market, code = value[:2], value[2:]
    if market not in {"sh", "sz", "bj"}:
        raise _data_error("canonical_sina_symbol", "code must use a lowercase exchange prefix")
    if not code.isascii() or not code.isdigit():
        raise _data_error("canonical_sina_symbol", "code must end in six ASCII digits")
    valid_prefixes = {"sh": ("6",), "sz": ("0", "3"), "bj": ("4", "8", "9")}
    if not code.startswith(valid_prefixes[market]):
        raise _data_error("canonical_sina_symbol", "exchange prefix does not match stock code")
    return f"{code}.{market.upper()}"


def sina_symbol_from_canonical(symbol: str) -> str:
    """Translate an SH or SZ canonical symbol into Sina's historical symbol form."""
    try:
        validate_symbol(symbol)
    except ValueError as exc:
        raise _data_error("sina_daily_symbol", "invalid canonical symbol") from exc
    code, exchange = symbol.rsplit(".", maxsplit=1)
    prefixes = {"SH": "sh", "SZ": "sz"}
    try:
        return f"{prefixes[exchange]}{code}"
    except KeyError as exc:
        raise _data_error("sina_daily_symbol", "Sina daily history supports SH and SZ only") from exc


def to_optional_float(value: object) -> float | None:
    """Convert an AKShare optional numeric cell, preserving missing-vs-invalid input."""
    if value is None:
        return None
    if value is pd.NA:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in _MISSING_TEXT:
            return None
        value = stripped
    if not isinstance(value, (str, Real)) or isinstance(value, bool):
        raise _data_error("numeric_mapping", "value is not numeric")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _data_error("numeric_mapping", "value cannot be converted to float") from exc
    if not math.isfinite(numeric):
        if pd.isna(numeric):
            return None
        raise _data_error("numeric_mapping", "value must be finite")
    return numeric


def lots_to_shares(value: object, *, required: bool) -> float | None:
    """Convert AKShare lot volume to internal shares using one lot equals 100 shares."""
    lots = to_optional_float(value)
    if lots is None:
        if required:
            raise _data_error("volume_mapping", "required volume is missing")
        return None
    return lots * 100


def map_sh_instruments(frame: pd.DataFrame, board: Board) -> tuple[Instrument, ...]:
    """Map one Shanghai board listing frame to canonical instruments."""
    _require_nonempty_columns(frame, ("证券代码", "证券简称", "上市日期"), "sh_instruments")
    exchange = Exchange.SSE
    return _map_instrument_rows(
        frame,
        code_column="证券代码",
        name_column="证券简称",
        listing_date_column="上市日期",
        exchange=exchange,
        board=board,
    )


def map_sz_instruments(frame: pd.DataFrame) -> tuple[Instrument, ...]:
    """Map Shenzhen listings and their explicit board field to canonical instruments."""
    _require_nonempty_columns(
        frame,
        ("A股代码", "A股简称", "A股上市日期", "板块"),
        "sz_instruments",
    )
    instruments: list[Instrument] = []
    for _, row in frame.iterrows():
        board_text = _require_text(row["板块"], "board")
        board = {"主板": Board.SZ_MAIN, "创业板": Board.CHINEXT}.get(board_text)
        if board is None:
            raise _data_error("sz_instruments", f"unsupported Shenzhen board: {board_text}")
        instruments.append(
            _build_instrument(
                code=row["A股代码"],
                name=row["A股简称"],
                listing_date=row["A股上市日期"],
                exchange=Exchange.SZSE,
                board=board,
            )
        )
    return tuple(instruments)


def map_bj_instruments(frame: pd.DataFrame) -> tuple[Instrument, ...]:
    """Map Beijing Exchange listings to canonical instruments."""
    _require_nonempty_columns(frame, ("证券代码", "证券简称", "上市日期"), "bj_instruments")
    return _map_instrument_rows(
        frame,
        code_column="证券代码",
        name_column="证券简称",
        listing_date_column="上市日期",
        exchange=Exchange.BSE,
        board=Board.BSE,
    )


def map_daily_bars(frame: pd.DataFrame, symbol: str) -> tuple[DailyBar, ...]:
    """Map AKShare daily bars, normalizing lot volume into shares."""
    if frame.empty:
        return ()
    _require_columns(frame, _DAILY_COLUMNS, "daily_bars")
    bars: list[DailyBar] = []
    for _, row in frame.iterrows():
        try:
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=_to_date(row["日期"], "trade_date"),
                    adjustment=AdjustmentType.RAW,
                    open=_required_float(row["开盘"], "open"),
                    high=_required_float(row["最高"], "high"),
                    low=_required_float(row["最低"], "low"),
                    close=_required_float(row["收盘"], "close"),
                    volume=_required_lots_to_shares(row["成交量"]),
                    amount=_required_float(row["成交额"], "amount"),
                    source="akshare:stock_zh_a_hist",
                )
            )
        except (ValidationError, ProviderDataError) as exc:
            raise _data_error("daily_bars", "invalid daily-bar row") from exc
    return tuple(sorted(bars, key=lambda bar: bar.trade_date))


def map_sina_daily_bars(frame: pd.DataFrame, symbol: str) -> tuple[DailyBar, ...]:
    """Map Sina historical daily bars, whose volume column is already shares."""
    if frame.empty:
        return ()
    _require_columns(frame, _SINA_DAILY_COLUMNS, "sina_daily_bars")
    bars: list[DailyBar] = []
    for _, row in frame.iterrows():
        try:
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=_to_date(row["date"], "trade_date"),
                    adjustment=AdjustmentType.RAW,
                    open=_required_float(row["open"], "open"),
                    high=_required_float(row["high"], "high"),
                    low=_required_float(row["low"], "low"),
                    close=_required_float(row["close"], "close"),
                    volume=_required_float(row["volume"], "volume"),
                    amount=_required_float(row["amount"], "amount"),
                    source="akshare:stock_zh_a_daily",
                )
            )
        except (ValidationError, ProviderDataError) as exc:
            raise _data_error("sina_daily_bars", "invalid Sina daily-bar row") from exc
    return tuple(sorted(bars, key=lambda bar: bar.trade_date))


def map_realtime_quotes(
    frame: pd.DataFrame, ingested_at: datetime
) -> tuple[tuple[RealtimeQuote, ...], int]:
    """Map one AKShare snapshot and skip only rows lacking valid positive prices."""
    _require_nonempty_columns(frame, _REALTIME_COLUMNS, "realtime_quotes")
    quotes: list[RealtimeQuote] = []
    skipped_without_price = 0
    for _, row in frame.iterrows():
        symbol = canonical_symbol_from_akshare_code(row["代码"])
        price = to_optional_float(row["最新价"])
        if price is None or price <= 0:
            skipped_without_price += 1
            continue
        try:
            quotes.append(
                RealtimeQuote(
                    symbol=symbol,
                    price=price,
                    open=to_optional_float(row["今开"]),
                    high=to_optional_float(row["最高"]),
                    low=to_optional_float(row["最低"]),
                    prev_close=to_optional_float(row["昨收"]),
                    volume=lots_to_shares(row["成交量"], required=False),
                    amount=to_optional_float(row["成交额"]),
                    change_pct=to_optional_float(row["涨跌幅"]),
                    turnover_rate=to_optional_float(row["换手率"]),
                    volume_ratio=to_optional_float(row["量比"]),
                    source_timestamp=None,
                    ingested_at=ingested_at,
                    source="akshare:stock_zh_a_spot_em",
                )
            )
        except (ValidationError, ProviderDataError) as exc:
            raise _data_error("realtime_quotes", "invalid realtime quote row") from exc
    return tuple(sorted(quotes, key=lambda quote: quote.symbol)), skipped_without_price


def map_sina_realtime_quotes(
    frame: pd.DataFrame, ingested_at: datetime
) -> tuple[tuple[RealtimeQuote, ...], int]:
    """Map a Sina snapshot, whose volume column is already expressed in shares."""
    _require_nonempty_columns(frame, _SINA_REALTIME_COLUMNS, "sina_realtime_quotes")
    quotes: list[RealtimeQuote] = []
    skipped_without_price = 0
    for _, row in frame.iterrows():
        symbol = canonical_symbol_from_sina_code(row["代码"])
        price = to_optional_float(row["最新价"])
        if price is None or price <= 0:
            skipped_without_price += 1
            continue
        try:
            quotes.append(
                RealtimeQuote(
                    symbol=symbol,
                    price=price,
                    open=to_optional_float(row["今开"]),
                    high=to_optional_float(row["最高"]),
                    low=to_optional_float(row["最低"]),
                    prev_close=to_optional_float(row["昨收"]),
                    volume=to_optional_float(row["成交量"]),
                    amount=to_optional_float(row["成交额"]),
                    change_pct=to_optional_float(row["涨跌幅"]),
                    turnover_rate=None,
                    volume_ratio=None,
                    source_timestamp=None,
                    ingested_at=ingested_at,
                    source="akshare:stock_zh_a_spot",
                )
            )
        except (ValidationError, ProviderDataError) as exc:
            raise _data_error("sina_realtime_quotes", "invalid realtime quote row") from exc
    return tuple(sorted(quotes, key=lambda quote: quote.symbol)), skipped_without_price


def _map_instrument_rows(
    frame: pd.DataFrame,
    *,
    code_column: str,
    name_column: str,
    listing_date_column: str,
    exchange: Exchange,
    board: Board,
) -> tuple[Instrument, ...]:
    """Map a listing frame with one fixed exchange and board."""
    instruments: list[Instrument] = []
    for _, row in frame.iterrows():
        instruments.append(
            _build_instrument(
                code=row[code_column],
                name=row[name_column],
                listing_date=row[listing_date_column],
                exchange=exchange,
                board=board,
            )
        )
    return tuple(instruments)


def _build_instrument(
    *, code: object, name: object, listing_date: object, exchange: Exchange, board: Board
) -> Instrument:
    """Build one validated instrument from a provider listing row."""
    try:
        instrument = Instrument(
            symbol=canonical_symbol_from_akshare_code(code),
            name=_require_text(name, "name"),
            exchange=exchange,
            board=board,
            listing_date=_to_date(listing_date, "listing_date"),
            status=_status_from_name(_require_text(name, "name")),
        )
    except (ValidationError, ProviderDataError) as exc:
        raise _data_error("instrument_mapping", "invalid instrument row") from exc
    return instrument


def _status_from_name(name: str) -> SecurityStatus:
    """Classify explicit ST-style name prefixes without filtering instruments."""
    normalized = name.upper().replace(" ", "")
    prefixes = ("ST", "*ST", "S*ST", "SST")
    return SecurityStatus.ST if normalized.startswith(prefixes) else SecurityStatus.ACTIVE


def _to_date(value: object, field_name: str) -> date:
    """Convert a provider date cell into a date-only domain value."""
    if not isinstance(value, (str, int, float, date, datetime, pd.Timestamp)):
        raise _data_error("date_mapping", f"{field_name} cannot be parsed")
    try:
        converted = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _data_error("date_mapping", f"{field_name} cannot be parsed") from exc
    if pd.isna(converted):
        raise _data_error("date_mapping", f"{field_name} is missing")
    return date(converted.year, converted.month, converted.day)


def _required_float(value: object, field_name: str) -> float:
    """Convert a required finite numeric provider cell."""
    converted = to_optional_float(value)
    if converted is None:
        raise _data_error("numeric_mapping", f"required {field_name} is missing")
    return converted


def _required_lots_to_shares(value: object) -> float:
    """Convert a required lot-volume cell into a non-optional share count."""
    converted = lots_to_shares(value, required=True)
    assert converted is not None
    return converted


def _require_text(value: object, field_name: str) -> str:
    """Convert a required text provider cell without accepting missing placeholders."""
    if not isinstance(value, str):
        raise _data_error("text_mapping", f"{field_name} must be text")
    text = value.strip()
    if text in _MISSING_TEXT:
        raise _data_error("text_mapping", f"{field_name} is missing")
    return text


def _require_nonempty_columns(
    frame: pd.DataFrame, columns: tuple[str, ...], operation: str
) -> None:
    """Require a nonempty frame with a complete expected AKShare schema."""
    if frame.empty:
        raise _data_error(operation, "AKShare returned an empty DataFrame")
    _require_columns(frame, columns, operation)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], operation: str) -> None:
    """Raise a data error when an AKShare schema column is missing."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise _data_error(operation, f"missing required columns: {', '.join(missing)}")


def _data_error(operation: str, message: str) -> ProviderDataError:
    """Build a concise AKShare data-boundary error."""
    return ProviderDataError("akshare", operation, message)
