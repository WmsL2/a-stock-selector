"""Point-in-time, structural-only universe builder tests."""

from datetime import date

import pytest

from stock_selector.config.models import UniverseConfig
from stock_selector.models import Board, Exchange, Instrument, SecurityStatus
from stock_selector.universe import (
    AshareUniverseBuilder,
    UniverseDataError,
    UniverseExclusionReason,
)


def _instrument(
    symbol: str,
    listing_date: date = date(2020, 1, 1),
    delisting_date: date | None = None,
    status: SecurityStatus = SecurityStatus.ACTIVE,
) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    board = {
        Exchange.SSE: Board.SH_MAIN,
        Exchange.SZSE: Board.SZ_MAIN,
        Exchange.BSE: Board.BSE,
    }[exchange]
    return Instrument(
        symbol=symbol,
        name=symbol,
        exchange=exchange,
        board=board,
        listing_date=listing_date,
        delisting_date=delisting_date,
        status=status,
    )


def _decision(snapshot, symbol: str):  # type: ignore[no-untyped-def]
    return next(decision for decision in snapshot.decisions if decision.symbol == symbol)


def test_default_policy_includes_listing_day_without_new_stock_filter() -> None:
    config = UniverseConfig()
    instrument = _instrument("600519.SH", listing_date=date(2024, 1, 1))
    snapshot = AshareUniverseBuilder().build((instrument,), config, date(2024, 1, 1))
    assert config.min_listing_days == 0
    assert snapshot.members == ("600519.SH",)


def test_lifecycle_boundaries_are_inclusive_and_historical_input_is_respected() -> None:
    active = _instrument("600519.SH", listing_date=date(2010, 1, 1))
    delisted = _instrument(
        "000001.SZ", listing_date=date(2010, 1, 1), delisting_date=date(2020, 6, 30)
    )
    newer = _instrument("430047.BJ", listing_date=date(2022, 1, 1))
    builder = AshareUniverseBuilder()
    config = UniverseConfig()
    assert builder.build((active, delisted, newer), config, date(2018, 1, 1)).members == (
        "000001.SZ",
        "600519.SH",
    )
    assert builder.build((active, delisted, newer), config, date(2021, 1, 1)).members == (
        "600519.SH",
    )
    assert builder.build((active, delisted, newer), config, date(2023, 1, 1)).members == (
        "430047.BJ",
        "600519.SH",
    )
    boundary = builder.build((delisted,), config, date(2020, 6, 30))
    assert boundary.members == ("000001.SZ",)
    after = builder.build((delisted,), config, date(2020, 7, 1))
    assert _decision(after, "000001.SZ").reasons == (UniverseExclusionReason.DELISTED,)


def test_board_lifecycle_and_minimum_days_reasons_are_deterministic() -> None:
    config = UniverseConfig(include_sh_main=False, min_listing_days=30)
    instrument = _instrument("600519.SH", listing_date=date(2024, 1, 1))
    snapshot = AshareUniverseBuilder().build((instrument,), config, date(2024, 1, 15))
    assert _decision(snapshot, "600519.SH").reasons == (
        UniverseExclusionReason.BOARD_DISABLED,
        UniverseExclusionReason.MIN_LISTING_DAYS,
    )


def test_duplicate_symbols_are_rejected_without_silent_deduplication() -> None:
    instrument = _instrument("600519.SH")
    with pytest.raises(UniverseDataError, match="duplicate"):
        AshareUniverseBuilder().build(
            (instrument, instrument), UniverseConfig(), date(2024, 1, 1)
        )


def test_current_status_never_changes_structural_membership() -> None:
    builder = AshareUniverseBuilder()
    as_of = date(2024, 1, 1)
    active = _instrument("600519.SH", status=SecurityStatus.ACTIVE)
    st = _instrument("600519.SH", status=SecurityStatus.ST)
    suspended = _instrument("600519.SH", status=SecurityStatus.SUSPENDED)
    delisting = _instrument("600519.SH", status=SecurityStatus.DELISTING)
    expected = builder.build((active,), UniverseConfig(), as_of)
    for candidate in (st, suspended, delisting):
        assert builder.build((candidate,), UniverseConfig(), as_of) == expected
