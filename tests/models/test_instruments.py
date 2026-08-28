"""Tests for canonical instrument metadata."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from stock_selector.models import Board, Exchange, Instrument


@pytest.mark.parametrize(
    ("symbol", "exchange", "board"),
    [
        ("600519.SH", Exchange.SSE, Board.SH_MAIN),
        ("688981.SH", Exchange.SSE, Board.STAR),
        ("300750.SZ", Exchange.SZSE, Board.CHINEXT),
        ("430047.BJ", Exchange.BSE, Board.BSE),
    ],
)
def test_valid_instruments(symbol: str, exchange: Exchange, board: Board) -> None:
    """Every supported board maps to its canonical exchange."""
    instrument = Instrument(
        symbol=symbol,
        name="测试证券",
        exchange=exchange,
        board=board,
        listing_date=datetime.now(tz=UTC).date(),
    )
    assert instrument.symbol == symbol


def test_instrument_rejects_exchange_and_board_mismatches() -> None:
    """Symbol, exchange, and board must agree."""
    with pytest.raises(ValidationError):
        Instrument(
            symbol="600519.SH",
            name="测试证券",
            exchange=Exchange.SZSE,
            board=Board.SZ_MAIN,
            listing_date=datetime.now(tz=UTC).date(),
        )
    with pytest.raises(ValidationError):
        Instrument(
            symbol="600519.SH",
            name="测试证券",
            exchange=Exchange.SZSE,
            board=Board.STAR,
            listing_date=datetime.now(tz=UTC).date(),
        )


def test_instrument_rejects_invalid_name_and_date_range() -> None:
    """Instrument metadata must contain a name and ordered lifecycle dates."""
    with pytest.raises(ValidationError):
        Instrument(
            symbol="600519.SH",
            name="  ",
            exchange=Exchange.SSE,
            board=Board.SH_MAIN,
            listing_date=datetime.now(tz=UTC).date(),
        )
    with pytest.raises(ValidationError):
        Instrument(
            symbol="600519.SH",
            name="测试证券",
            exchange=Exchange.SSE,
            board=Board.SH_MAIN,
            listing_date=date(2020, 1, 2),
            delisting_date=date(2020, 1, 1),
        )
