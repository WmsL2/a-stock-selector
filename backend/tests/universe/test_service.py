"""Current-universe service tests for explicit timezone and as-of boundaries."""

from datetime import date

from stock_selector.config.models import Settings
from stock_selector.config.paths import AppPaths
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe import CurrentUniverseService


def test_current_service_accepts_explicit_as_of_override(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(
        (
            Instrument(
                symbol="600519.SH",
                name="测试股票",
                exchange=Exchange.SSE,
                board=Board.SH_MAIN,
                listing_date=date(2024, 1, 1),
            ),
        )
    )
    snapshot = CurrentUniverseService(repository, Settings()).build_current(
        as_of=date(2023, 12, 31)
    )
    assert snapshot.as_of == date(2023, 12, 31)
    assert snapshot.members == ()


def test_current_service_inherits_star_cdr_structural_exclusion(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(
        (
            Instrument(
                symbol="688001.SH",
                name="STAR A 股",
                exchange=Exchange.SSE,
                board=Board.STAR,
                listing_date=date(2020, 1, 1),
            ),
            Instrument(
                symbol="689009.SH",
                name="STAR CDR",
                exchange=Exchange.SSE,
                board=Board.STAR,
                listing_date=date(2020, 1, 1),
            ),
        )
    )
    snapshot = CurrentUniverseService(repository, Settings()).build_current(
        as_of=date(2026, 9, 2)
    )
    assert snapshot.members == ("688001.SH",)
    assert [decision.symbol for decision in snapshot.decisions] == [
        "688001.SH",
        "689009.SH",
    ]
