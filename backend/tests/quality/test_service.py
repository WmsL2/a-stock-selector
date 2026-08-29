"""Current quality service tests using explicit local risk records only."""

from datetime import UTC, date, datetime

from stock_selector.config import AppPaths, Settings
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.quality import CurrentQualityService
from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository


def test_quality_service_does_not_fabricate_missing_risk_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments((_instrument("600519.SH"), _instrument("000001.SZ")))
    calculation_at = datetime(2026, 8, 29, 10, tzinfo=UTC)
    service = CurrentQualityService(repository, Settings())
    empty = service.build_current(calculation_at=calculation_at)
    assert (empty.risk_state_records, empty.risk_complete_instruments, empty.risk_filter_ready, empty.risk_eligible_instruments) == (0, 0, False, None)
    repository.upsert_risk_states(
        (
            _state("600519.SH"),
            _state("000001.SZ"),
        )
    )
    complete = service.build_current(calculation_at=calculation_at)
    assert (complete.risk_filter_ready, complete.risk_eligible_instruments) == (True, 2)


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name="test",
        exchange=exchange,
        board=Board.SH_MAIN if exchange is Exchange.SSE else Board.SZ_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _state(symbol: str) -> DatedRiskState:
    return DatedRiskState(
        symbol=symbol,
        as_of=date(2026, 8, 29),
        is_st=False,
        is_suspended=False,
        is_delisting_period=False,
        observed_at=datetime(2026, 8, 29, 9, tzinfo=UTC),
        source="test",
    )
