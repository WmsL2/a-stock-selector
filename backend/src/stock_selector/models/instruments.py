"""Canonical security identifiers and instrument metadata records."""

from datetime import date
from enum import Enum

from pydantic import field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_nonempty_string,
    validate_symbol,
)


class Exchange(str, Enum):
    """Canonical exchange suffixes used in internal symbols."""

    SSE = "SH"
    SZSE = "SZ"
    BSE = "BJ"


class Board(str, Enum):
    """Supported Chinese equity boards."""

    SH_MAIN = "sh_main"
    SZ_MAIN = "sz_main"
    CHINEXT = "chinext"
    STAR = "star"
    BSE = "bse"


class SecurityStatus(str, Enum):
    """Instrument status known at the time of a metadata record."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ST = "st"
    DELISTING = "delisting"
    DELISTED = "delisted"


_BOARD_EXCHANGES = {
    Board.SH_MAIN: Exchange.SSE,
    Board.STAR: Exchange.SSE,
    Board.SZ_MAIN: Exchange.SZSE,
    Board.CHINEXT: Exchange.SZSE,
    Board.BSE: Exchange.BSE,
}


class Instrument(DomainModel):
    """Static security metadata with canonical symbol and board identity."""

    symbol: str
    name: str
    exchange: Exchange
    board: Board
    listing_date: date
    delisting_date: date | None = None
    status: SecurityStatus = SecurityStatus.ACTIVE

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol representation."""
        return validate_symbol(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a nonempty instrument name."""
        return ensure_nonempty_string(value, "name")

    @model_validator(mode="after")
    def validate_consistency(self) -> "Instrument":
        """Ensure exchange, board, and listing history agree."""
        symbol_exchange = self.symbol.rsplit(".", maxsplit=1)[1]
        if symbol_exchange != self.exchange.value:
            raise ValueError("symbol exchange suffix must match exchange")
        if _BOARD_EXCHANGES[self.board] != self.exchange:
            raise ValueError("board must match exchange")
        if self.delisting_date is not None and self.delisting_date < self.listing_date:
            raise ValueError("delisting_date must not precede listing_date")
        return self
