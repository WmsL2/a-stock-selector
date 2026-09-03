"""Offline contracts for bounded, sequential HFQ return collection."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.collection import (
    AdjustedDailyReturnCollector,
    AdjustedReturnCollectionRequest,
    AdjustedReturnCollectionStatus,
    CollectionError,
)
from stock_selector.config.paths import AppPaths
from stock_selector.models import AdjustedDailyReturn, AdjustmentType
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.storage import LocalMarketRepository, StorageError


def _record(symbol: str, *, trade_date: date = date(2026, 9, 2), **changes: object) -> AdjustedDailyReturn:
    values = {
        "symbol": symbol,
        "trade_date": trade_date,
        "previous_trade_date": trade_date - timedelta(days=1),
        "return_fraction": 0.01,
        "adjustment": AdjustmentType.HFQ,
        "observed_at": datetime(2026, 9, 3, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        "source": "fake:hfq",
    }
    values.update(changes)
    return AdjustedDailyReturn(**values)


class FakeProvider:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_adjusted_daily_returns(self, request):  # type: ignore[no-untyped-def]
        self.calls.append(request.symbol)
        result = self.responses[request.symbol]
        if isinstance(result, Exception):
            raise result
        return result


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _request() -> AdjustedReturnCollectionRequest:
    return AdjustedReturnCollectionRequest(
        symbols=("000001.SZ", "000002.SZ", "600519.SH"),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
    )


def test_collects_sequentially_and_isolates_provider_failures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    provider = FakeProvider(
        {
            "000001.SZ": (_record("000001.SZ"),),
            "000002.SZ": ProviderConnectionError("fake", "test", "offline"),
            "600519.SH": (),
        }
    )
    report = AdjustedDailyReturnCollector(provider, repository).collect(_request())
    assert provider.calls == ["000001.SZ", "000002.SZ", "600519.SH"]
    assert [item.status for item in report.results] == [
        AdjustedReturnCollectionStatus.SUCCESS,
        AdjustedReturnCollectionStatus.FAILED,
        AdjustedReturnCollectionStatus.EMPTY,
    ]
    assert (report.success_symbols, report.empty_symbols, report.failed_symbols) == (1, 1, 1)
    assert (report.rows_received, report.rows_persisted) == (1, 1)
    assert len(repository.load_adjusted_daily_returns("000001.SZ")) == 1
    assert repository.load_adjusted_daily_returns("600519.SH") == ()


def test_storage_failure_is_fatal_before_later_provider_requests(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    provider = FakeProvider({symbol: (_record(symbol),) for symbol in _request().symbols})
    monkeypatch.setattr(repository, "upsert_adjusted_daily_returns", lambda records: (_ for _ in ()).throw(StorageError("disk")))
    with pytest.raises(CollectionError):
        AdjustedDailyReturnCollector(provider, repository).collect(_request())
    assert provider.calls == ["000001.SZ"]


@pytest.mark.parametrize(
    "records",
    [
        (_record("600519.SH"), _record("600519.SH")),
        (_record("600519.SH"), _record("600519.SH", observed_at=datetime(2026, 9, 3, 17, tzinfo=ZoneInfo("Asia/Shanghai")))),
        (_record("600519.SH"), _record("600519.SH", source="other:hfq")),
        (_record("000001.SZ"),),
    ],
)
def test_rejects_invalid_provider_batches_and_does_not_persist(tmp_path, records) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    provider = FakeProvider({"600519.SH": records})
    request = AdjustedReturnCollectionRequest(symbols=("600519.SH",), start_date=date(2026, 9, 1), end_date=date(2026, 9, 3))
    assert AdjustedDailyReturnCollector(provider, repository).collect(request).results[0].error_type == "CollectionDataError"
    assert repository.load_adjusted_daily_returns("600519.SH") == ()


def test_rejects_non_hfq_provider_batch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    invalid = _record("600519.SH").model_copy(update={"adjustment": AdjustmentType.RAW})
    provider = FakeProvider({"600519.SH": (invalid,)})
    request = AdjustedReturnCollectionRequest(symbols=("600519.SH",), start_date=date(2026, 9, 1), end_date=date(2026, 9, 3))
    assert AdjustedDailyReturnCollector(provider, repository).collect(request).results[0].error_type == "CollectionDataError"
