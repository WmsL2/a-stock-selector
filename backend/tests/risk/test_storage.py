"""Dated risk-state Parquet persistence tests."""

from datetime import UTC, date, datetime

import duckdb
import pytest

from stock_selector.config import AppPaths
from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository, StorageDataError


def test_risk_states_are_exact_date_tri_state_atomic_and_queryable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    first_day = date(2026, 8, 28)
    second_day = date(2026, 8, 29)
    assert repository.load_risk_states(first_day) == ()
    state = _state("600519.SH", first_day, is_st=None, is_suspended=False)
    repository.upsert_risk_states((state,))
    assert repository.load_risk_states(first_day) == (state,)
    assert repository.load_risk_states(second_day) == ()
    replacement = state.model_copy(update={"is_st": True})
    repository.upsert_risk_states((replacement, _state("000001.SZ", first_day)))
    assert repository.load_risk_states(first_day, ("600519.SH",)) == (replacement,)
    assert [state.symbol for state in repository.load_risk_states(first_day)] == ["000001.SZ", "600519.SH"]
    stats = repository.get_stats()
    assert (stats.risk_state_rows, stats.risk_state_dates, stats.latest_risk_state_date) == (2, 1, first_day)
    connection = duckdb.connect(str(repository.catalog_path))
    try:
        assert connection.execute("SELECT COUNT(*) FROM risk_states").fetchone() == (2,)
    finally:
        connection.close()
    assert not list(tmp_path.rglob("*.tmp"))


def test_risk_storage_rejects_duplicate_and_mixed_day_inputs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    today = date(2026, 8, 29)
    state = _state("600519.SH", today)
    repository.upsert_risk_states(())
    with pytest.raises(StorageDataError):
        repository.upsert_risk_states((state, state))
    with pytest.raises(StorageDataError):
        repository.upsert_risk_states((state, _state("000001.SZ", date(2026, 8, 30))))
    with pytest.raises(StorageDataError):
        repository.load_risk_states(today, ("600519.SH", "600519.SH"))


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _state(
    symbol: str,
    as_of: date,
    *,
    is_st: bool | None = False,
    is_suspended: bool | None = None,
) -> DatedRiskState:
    return DatedRiskState(
        symbol=symbol,
        as_of=as_of,
        is_st=is_st,
        is_suspended=is_suspended,
        observed_at=datetime(2026, 8, 29, 1, tzinfo=UTC),
        source="test",
    )
