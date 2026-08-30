from datetime import UTC, datetime

import pytest

from stock_selector.models import RealtimeQuote
from stock_selector.providers.errors import (
    ProviderConnectionError,
    ProviderDataError,
    ProviderError,
    ProviderNotSupportedError,
)
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
    source_timestamp: datetime | None = None,
) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=10,
        ingested_at=at,
        source=source,
        source_timestamp=source_timestamp,
    )


def _quotes(*symbols: str) -> tuple[RealtimeQuote, ...]:
    return tuple(_quote(symbol) for symbol in symbols)


def test_all_market_capture_does_not_persist_without_explicit_persist_symbols() -> None:
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


def test_all_market_capture_persists_only_an_explicit_subset() -> None:
    provider = FakeProvider(_quotes("600519.SH", "000001.SZ", "000002.SZ"))
    repository = FakeRepository()
    result = RealtimeSnapshotCollector(provider, repository).capture(
        RealtimeCaptureRequest(persist_symbols=("000001.SZ",))
    )
    assert len(provider.requests) == 1
    assert result.received_quotes == 3
    assert result.received_symbols == ("000001.SZ", "000002.SZ", "600519.SH")
    assert result.persisted_quotes == 1
    assert result.persisted_symbols == ("000001.SZ",)
    assert repository.saved == [(_quote("000001.SZ"),)]


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


@pytest.mark.parametrize(
    "error",
    [
        ProviderConnectionError("fake", "realtime", "offline"),
        ProviderDataError("fake", "realtime", "invalid payload"),
        ProviderNotSupportedError("fake", "realtime", "not supported"),
    ],
)
def test_collector_translates_each_provider_error_with_original_cause(
    error: ProviderError,
) -> None:
    with pytest.raises(RealtimeCollectionError) as captured:
        RealtimeSnapshotCollector(FakeProvider(error)).capture(RealtimeCaptureRequest())
    assert captured.value.__cause__ is error


def test_collector_propagates_programming_errors() -> None:
    with pytest.raises(RuntimeError, match="bug"):
        RealtimeSnapshotCollector(FakeProvider(RuntimeError("bug"))).capture(
            RealtimeCaptureRequest()
        )


def test_collector_translates_persistence_failures() -> None:
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


def test_collector_uses_one_call_for_a_large_explicit_batch() -> None:
    symbols = tuple(f"{code:06d}.SH" for code in range(600000, 600050))
    provider = FakeProvider(_quotes(*symbols))
    result = RealtimeSnapshotCollector(provider).capture(
        RealtimeCaptureRequest(symbols=symbols)
    )
    assert len(provider.requests) == 1
    assert result.received_quotes == 50
    assert result.received_symbols == symbols


def test_collector_counts_only_present_source_timestamps() -> None:
    ingested_at = datetime(2026, 8, 30, 10, tzinfo=UTC)
    provider = FakeProvider(
        (
            _quote(
                "600519.SH",
                at=ingested_at,
                source_timestamp=datetime(2026, 8, 30, 9, tzinfo=UTC),
            ),
            _quote("000001.SZ", at=ingested_at),
            _quote("000002.SZ", at=ingested_at),
        )
    )
    result = RealtimeSnapshotCollector(provider).capture(RealtimeCaptureRequest())
    assert result.source_timestamp_available_quotes == 1


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
