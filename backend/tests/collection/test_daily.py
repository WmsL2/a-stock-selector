"""Bounded collector tests using a provider abstraction fake."""

from datetime import date

import pytest

from stock_selector.collection import (
    DailyCollectionRequest,
    DailyCollectionStatus,
    DailyPriceCollector,
)
from stock_selector.config import AppPaths
from stock_selector.models import AdjustmentType, DailyBar
from stock_selector.providers.base import DailyMarketDataProvider, ProviderInfo
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.providers.requests import DailyBarsRequest
from stock_selector.storage import LocalMarketRepository, StorageError


def test_collector_isolates_provider_failures_and_persists_only_requested_symbols(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    provider = FakeDailyProvider({
        "000001.SZ": ProviderConnectionError("fake", "daily", "offline"),
        "600519.SH": _bars("600519.SH"),
        "601398.SH": _bars("601398.SH"),
    })
    report = DailyPriceCollector(provider, repository).collect(_request("601398.SH", "000001.SZ", "600519.SH"))
    assert (report.succeeded_symbols, report.failed_symbols, report.empty_symbols) == (2, 1, 0)
    assert [result.status for result in report.results] == [
        DailyCollectionStatus.FAILED,
        DailyCollectionStatus.SUCCESS,
        DailyCollectionStatus.SUCCESS,
    ]
    assert repository.load_daily_bars("000001.SZ") == ()
    assert len(repository.load_daily_bars("600519.SH")) == 5
    assert len(repository.load_daily_bars("601398.SH")) == 5
    assert not repository.load_instruments()


def test_invalid_provider_batches_are_failed_without_persistence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    invalid_batches = (
        _bars("000001.SZ"),
        _bars("600519.SH", dates=(2, 3, 8)),
        _bars("600519.SH", dates=(3, 3)),
        _bars("600519.SH", sources=("a", "b", "a", "a", "a")),
        _bars("600519.SH", adjustment=AdjustmentType.QFQ),
    )
    for bars in invalid_batches:
        repository = _repository(tmp_path / bars[0].source.replace(":", "_"))
        report = DailyPriceCollector(
            FakeDailyProvider({"600519.SH": bars}), repository
        ).collect(_request("600519.SH"))
        assert report.results[0].status is DailyCollectionStatus.FAILED
        assert repository.load_daily_bars("600519.SH") == ()


def test_empty_idempotent_and_storage_failure_behaviors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    empty = DailyPriceCollector(FakeDailyProvider({"600519.SH": ()}), repository).collect(_request("600519.SH"))
    assert empty.results[0].status is DailyCollectionStatus.EMPTY
    provider = FakeDailyProvider({"600519.SH": _bars("600519.SH")})
    collector = DailyPriceCollector(provider, repository)
    collector.collect(_request("600519.SH"))
    collector.collect(_request("600519.SH"))
    assert len(repository.load_daily_bars("600519.SH")) == 5
    broken = BrokenRepository(repository)
    with pytest.raises(Exception, match="storage infrastructure"):
        DailyPriceCollector(provider, broken).collect(_request("600519.SH"))


class FakeDailyProvider(DailyMarketDataProvider):
    def __init__(self, responses: dict[str, tuple[DailyBar, ...] | Exception]) -> None:
        self.responses = responses

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake")

    def get_daily_bars(self, request: DailyBarsRequest) -> tuple[DailyBar, ...]:
        response = self.responses[request.symbol]
        if isinstance(response, Exception):
            raise response
        return response


class BrokenRepository:
    def __init__(self, repository: LocalMarketRepository) -> None:
        self._repository = repository

    def upsert_daily_bars(self, _bars: tuple[DailyBar, ...]) -> None:
        raise StorageError("disk failed")


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _request(*symbols: str) -> DailyCollectionRequest:
    return DailyCollectionRequest(symbols=symbols, start_date=date(2026, 8, 3), end_date=date(2026, 8, 7))


def _bars(
    symbol: str,
    *,
    dates: tuple[int, ...] = (3, 4, 5, 6, 7),
    sources: tuple[str, ...] | None = None,
    adjustment: AdjustmentType = AdjustmentType.RAW,
) -> tuple[DailyBar, ...]:
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=date(2026, 8, day),
            adjustment=adjustment,
            open=9.0,
            high=11.0,
            low=8.0,
            close=10.0,
            volume=100.0,
            amount=1000.0,
            source=sources[index] if sources else "fake",
        )
        for index, day in enumerate(dates)
    )
