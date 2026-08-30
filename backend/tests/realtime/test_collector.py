from datetime import UTC, datetime

import pytest

from stock_selector.models import RealtimeQuote
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.providers.requests import RealtimeQuotesRequest
from stock_selector.realtime import (
    RealtimeCaptureRequest,
    RealtimeCaptureScope,
    RealtimeCollectionError,
    RealtimeDataError,
    RealtimeSnapshotCollector,
)
from stock_selector.storage import StorageError


def _quote(
    symbol: str,
    *,
    at: datetime = datetime(2026, 8, 30, 10, tzinfo=UTC),
    source: str = "fake:realtime",
) -> RealtimeQuote:
    return RealtimeQuote(symbol=symbol, price=10, ingested_at=at, source=source)


def _quotes(*symbols: str) -> tuple[RealtimeQuote, ...]:
    return tuple(_quote(symbol) for symbol in symbols)


def test_all_market_capture_calls_provider_once_and_never_persists() -> None:
    provider = FakeProvider(_quotes("600519.SH", "000001.SZ"))
    repository = FakeRepository()
    result = RealtimeSnapshotCollector(provider, repository).capture(
        RealtimeCaptureRequest()
    )
    assert len(provider.requests) == 1
    assert provider.requests[0] == RealtimeQuotesRequest()
    assert result.scope is RealtimeCaptureScope.ALL_MARKET
    assert result.received_symbols == ("000001.SZ", "600519.SH")
    assert result.persisted_quotes == 0
    assert repository.saved == []


def test_explicit_capture_requires_the_exact_returned_symbol_set_and_can_persist() -> (
    None
):
    provider = FakeProvider(_quotes("600519.SH", "000001.SZ"))
    repository = FakeRepository()
    result = RealtimeSnapshotCollector(provider, repository).capture(
        RealtimeCaptureRequest(
            symbols=("600519.SH", "000001.SZ"),
            persist_symbols=("600519.SH",),
        )
    )
    assert result.scope is RealtimeCaptureScope.EXPLICIT_SYMBOLS
    assert result.persisted_symbols == ("600519.SH",)
    assert repository.saved == [(_quote("600519.SH"),)]


@pytest.mark.parametrize(
    "quotes",
    [
        (),
        (_quote("600519.SH"), _quote("600519.SH")),
        (_quote("600519.SH"), _quote("000001.SZ", source="other")),
        (
            _quote("600519.SH"),
            _quote("000001.SZ", at=datetime(2026, 8, 30, 10, 1, tzinfo=UTC)),
        ),
    ],
)
def test_collector_rejects_invalid_snapshot_batches(
    quotes: tuple[RealtimeQuote, ...],
) -> None:
    with pytest.raises(RealtimeDataError):
        RealtimeSnapshotCollector(FakeProvider(quotes)).capture(
            RealtimeCaptureRequest()
        )


def test_collector_translates_provider_and_persistence_failures() -> None:
    with pytest.raises(RealtimeCollectionError):
        RealtimeSnapshotCollector(
            FakeProvider(ProviderConnectionError("fake", "realtime", "offline"))
        ).capture(RealtimeCaptureRequest())
    with pytest.raises(RealtimeCollectionError):
        RealtimeSnapshotCollector(
            FakeProvider(_quotes("600519.SH")), BrokenRepository()
        ).capture(
            RealtimeCaptureRequest(
                symbols=("600519.SH",), persist_symbols=("600519.SH",)
            )
        )


def test_collector_rejects_a_missing_explicit_response_symbol() -> None:
    with pytest.raises(RealtimeDataError):
        RealtimeSnapshotCollector(FakeProvider(_quotes("600519.SH"))).capture(
            RealtimeCaptureRequest(symbols=("000001.SZ",))
        )


class FakeProvider:
    def __init__(self, response: tuple[RealtimeQuote, ...] | Exception) -> None:
        self.response = response
        self.requests: list[RealtimeQuotesRequest] = []

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[RealtimeQuote, ...]] = []

    def save_realtime_snapshot(self, quotes: tuple[RealtimeQuote, ...]) -> None:
        self.saved.append(quotes)


class BrokenRepository:
    def save_realtime_snapshot(self, _quotes: tuple[RealtimeQuote, ...]) -> None:
        raise StorageError("disk unavailable")
