"""Offline all-or-nothing current-risk collection regressions."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.collection import (
    CollectionDataError,
    CollectionError,
    CurrentRiskCollectionRequest,
    CurrentRiskStateCollector,
)
from stock_selector.config import AppPaths, Settings
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.providers.base import CurrentRiskStateProvider, ProviderInfo
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.providers.requests import CurrentRiskStatesRequest
from stock_selector.risk import DatedRiskState, RiskEligibilityEvaluator
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe import CurrentUniverseService

AS_OF = date(2026, 9, 2)
OBSERVED_AT = datetime(2026, 9, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
SYMBOLS = ("000001.SZ", "600519.SH", "601398.SH")


class FakeRiskProvider(CurrentRiskStateProvider):
    def __init__(self, response: tuple[DatedRiskState, ...] | Exception) -> None:
        self.response = response
        self.requests: list[CurrentRiskStatesRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake")

    def get_current_risk_states(
        self, request: CurrentRiskStatesRequest
    ) -> tuple[DatedRiskState, ...]:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _state(symbol: str, **changes: object) -> DatedRiskState:
    values: dict[str, object] = {
        "symbol": symbol, "as_of": AS_OF, "is_st": False, "is_suspended": False,
        "is_delisting_period": False, "observed_at": OBSERVED_AT, "source": "fake:risk",
    }
    values.update(changes)
    return DatedRiskState(**values)


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _request() -> CurrentRiskCollectionRequest:
    return CurrentRiskCollectionRequest(symbols=tuple(reversed(SYMBOLS)), as_of=AS_OF)


def test_current_risk_collector_persists_one_complete_batch_and_unblocks_evaluator(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    provider = FakeRiskProvider((_state("600519.SH", is_st=True), _state("000001.SZ"), _state("601398.SH", is_suspended=True, is_delisting_period=True)))
    upsert_calls = 0
    original_upsert = repository.upsert_risk_states

    def count_upsert(states: tuple[DatedRiskState, ...]) -> None:
        nonlocal upsert_calls
        upsert_calls += 1
        original_upsert(states)

    monkeypatch.setattr(repository, "upsert_risk_states", count_upsert)
    report = CurrentRiskStateCollector(provider, repository).collect(_request())

    assert provider.requests == [CurrentRiskStatesRequest(symbols=SYMBOLS, as_of=AS_OF)]
    assert upsert_calls == 1
    assert report.requested_symbols == SYMBOLS
    assert (report.states_received, report.states_persisted, report.st_members, report.suspended_members, report.delisting_period_members) == (3, 3, 1, 1, 1)
    persisted = repository.load_risk_states(AS_OF, SYMBOLS)
    assert [state.symbol for state in persisted] == list(SYMBOLS)
    assert [
        (state.is_st, state.is_suspended, state.is_delisting_period)
        for state in persisted
    ] == [(False, False, False), (True, False, False), (False, True, True)]

    repository.save_instruments(tuple(_instrument(symbol) for symbol in SYMBOLS))
    structural = CurrentUniverseService(repository, Settings()).build_current(AS_OF)
    risk = RiskEligibilityEvaluator().evaluate(structural, persisted, Settings().universe)
    assert risk.risk_complete_members == len(structural.members)


@pytest.mark.parametrize(
    "states",
    [
        (_state("000001.SZ"), _state("600519.SH")),
        (_state("000001.SZ"), _state("000001.SZ"), _state("601398.SH")),
        (_state("000001.SZ", as_of=AS_OF - timedelta(days=1)), _state("600519.SH"), _state("601398.SH")),
        (_state("000001.SZ", is_st=None), _state("600519.SH"), _state("601398.SH")),
        (_state("000001.SZ", observed_at=OBSERVED_AT - timedelta(seconds=1)), _state("600519.SH"), _state("601398.SH")),
        (_state("000001.SZ", source="other"), _state("600519.SH"), _state("601398.SH")),
    ],
)
def test_current_risk_collector_rejects_invalid_batches_without_writing(tmp_path, states) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    with pytest.raises(CollectionDataError):
        CurrentRiskStateCollector(FakeRiskProvider(states), repository).collect(_request())
    assert repository.load_risk_states(AS_OF) == ()


def test_current_risk_collector_provider_and_storage_failures_never_claim_success(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    failed = FakeRiskProvider(ProviderConnectionError("fake", "risk", "offline"))
    with pytest.raises(ProviderConnectionError):
        CurrentRiskStateCollector(failed, repository).collect(_request())
    assert repository.load_risk_states(AS_OF) == ()

    provider = FakeRiskProvider(tuple(_state(symbol) for symbol in SYMBOLS))
    monkeypatch.setattr(repository, "upsert_risk_states", lambda _states: (_ for _ in ()).throw(StorageError("disk")))
    with pytest.raises(CollectionError, match="storage infrastructure"):
        CurrentRiskStateCollector(provider, repository).collect(_request())


def test_star_cdr_is_excluded_before_strict_current_risk_collection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
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
    structural = CurrentUniverseService(repository, Settings()).build_current(AS_OF)
    provider = FakeRiskProvider((_state("688001.SH"),))

    report = CurrentRiskStateCollector(provider, repository).collect(
        CurrentRiskCollectionRequest(symbols=structural.members, as_of=AS_OF)
    )

    assert structural.members == ("688001.SH",)
    assert [state.symbol for state in repository.load_risk_states(AS_OF)] == ["688001.SH"]
    assert report.states_persisted == 1


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=symbol,
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )
