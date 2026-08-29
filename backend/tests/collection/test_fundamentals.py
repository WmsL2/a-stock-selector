"""Collector-boundary tests for explicit point-in-time fundamentals batches."""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from stock_selector.collection.errors import CollectionDataError, CollectionError
from stock_selector.collection.fundamentals import (
    FinancialCollector,
    IndustryCollector,
    ValuationCollector,
)
from stock_selector.config.paths import AppPaths
from stock_selector.models import FinancialRecord, IndustryRecord, ValuationRecord
from stock_selector.providers.errors import ProviderDataError
from stock_selector.storage import LocalMarketRepository, StorageError

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_AS_OF = datetime(2026, 3, 31, 16, tzinfo=_SHANGHAI)
_PERIOD = date(2025, 12, 31)


class FakeFundamentalsProvider:
    """A symbol-indexed fake that deliberately crosses no real provider boundary."""

    def __init__(self, results: dict[str, tuple[Any, ...] | Exception]) -> None:
        self._results = results

    def get_financial_records(self, request: Any) -> tuple[FinancialRecord, ...]:
        return self._get(request.symbols[0])

    def get_valuation_records(self, request: Any) -> tuple[ValuationRecord, ...]:
        return self._get(request.symbols[0])

    def get_industry_records(self, request: Any) -> tuple[IndustryRecord, ...]:
        return self._get(request.symbols[0])

    def _get(self, symbol: str) -> tuple[Any, ...]:
        result = self._results[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def _repository(tmp_path: Any) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _financial(symbol: str = "600519.SH", **changes: Any) -> FinancialRecord:
    values = {
        "symbol": symbol,
        "report_period": _PERIOD,
        "announcement_date": date(2026, 3, 25),
        "available_at": datetime(2026, 3, 25, 15, 30, tzinfo=_SHANGHAI),
        "revenue": 100.0,
        "source": "test:financial",
    }
    values.update(changes)
    return FinancialRecord(**values)


def _valuation(symbol: str = "600519.SH", **changes: Any) -> ValuationRecord:
    values = {
        "symbol": symbol,
        "as_of": datetime(2026, 3, 25, 15, 30, tzinfo=_SHANGHAI),
        "pe": -5.0,
        "source": "test:valuation",
    }
    values.update(changes)
    return ValuationRecord(**values)


def _industry(symbol: str = "600519.SH", **changes: Any) -> IndustryRecord:
    values = {
        "symbol": symbol,
        "industry_code": "A1",
        "industry_name": "Alpha",
        "classification": "CNInfo",
        "effective_from": date(2020, 1, 1),
        "source": "test:industry",
    }
    values.update(changes)
    return IndustryRecord(**values)


def test_financial_collector_isolates_provider_failure_and_is_idempotent(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeFundamentalsProvider(
        {
            "000001.SZ": (_financial("000001.SZ"),),
            "600519.SH": ProviderDataError("fake", "financial", "unavailable"),
            "601398.SH": (_financial("601398.SH"),),
        }
    )
    collector = FinancialCollector(provider, repository)
    symbols = ("000001.SZ", "600519.SH", "601398.SH")
    first = collector.collect(symbols, _PERIOD, _PERIOD)
    second = collector.collect(symbols, _PERIOD, _PERIOD)
    assert (first.succeeded_symbols, first.failed_symbols, first.rows_persisted) == (
        2,
        1,
        2,
    )
    assert second.rows_persisted == 2
    assert len(repository.load_financial_records("000001.SZ")) == 1
    assert len(repository.load_financial_records("601398.SH")) == 1
    assert not repository.load_financial_records("600519.SH")


@pytest.mark.parametrize(
    ("collector_factory", "record_factory", "collect"),
    [
        (
            FinancialCollector,
            _financial,
            lambda collector: collector.collect(("600519.SH",), _PERIOD, _PERIOD),
        ),
        (
            ValuationCollector,
            _valuation,
            lambda collector: collector.collect(("600519.SH",), _AS_OF),
        ),
        (
            IndustryCollector,
            _industry,
            lambda collector: collector.collect(("600519.SH",), _AS_OF.date()),
        ),
    ],
)
def test_collectors_reject_wrong_symbol_without_persistence(
    tmp_path: Any,
    collector_factory: Callable[..., Any],
    record_factory: Callable[..., Any],
    collect: Callable[[Any], Any],
) -> None:
    repository = _repository(tmp_path)
    collector = collector_factory(
        FakeFundamentalsProvider({"600519.SH": (record_factory("000001.SZ"),)}),
        repository,
    )
    report = collect(collector)
    assert (report.failed_symbols, report.rows_persisted) == (1, 0)
    assert not repository.load_financial_records("000001.SZ")
    assert not repository.load_valuation_records("000001.SZ")
    assert not repository.load_industry_records("000001.SZ")


def test_empty_provider_result_is_empty_not_failed(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    report = FinancialCollector(
        FakeFundamentalsProvider({"600519.SH": ()}), repository
    ).collect(("600519.SH",), _PERIOD, _PERIOD)
    assert (report.succeeded_symbols, report.empty_symbols, report.failed_symbols) == (
        0,
        1,
        0,
    )


def test_financial_storage_failure_stops_collection(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    collector = FinancialCollector(
        FakeFundamentalsProvider({"600519.SH": (_financial(),)}), repository
    )

    def fail(_: tuple[FinancialRecord, ...]) -> None:
        raise StorageError("disk unavailable")

    monkeypatch.setattr(repository, "upsert_financial_records", fail)
    with pytest.raises(CollectionError):
        collector.collect(("600519.SH",), _PERIOD, _PERIOD)


@pytest.mark.parametrize(
    ("collector_factory", "records", "collect"),
    [
        (
            FinancialCollector,
            (_financial(), _financial()),
            lambda collector: collector.collect(("600519.SH",), _PERIOD, _PERIOD),
        ),
        (
            ValuationCollector,
            (_valuation(), _valuation()),
            lambda collector: collector.collect(("600519.SH",), _AS_OF),
        ),
        (
            IndustryCollector,
            (_industry(), _industry()),
            lambda collector: collector.collect(("600519.SH",), _AS_OF.date()),
        ),
    ],
)
def test_collectors_reject_duplicate_provider_logical_keys(
    tmp_path: Any,
    collector_factory: Callable[..., Any],
    records: tuple[Any, ...],
    collect: Callable[[Any], Any],
) -> None:
    repository = _repository(tmp_path)
    collector = collector_factory(
        FakeFundamentalsProvider({"600519.SH": records}), repository
    )
    report = collect(collector)
    assert (report.failed_symbols, report.rows_persisted) == (1, 0)


@pytest.mark.parametrize(
    ("collector_factory", "record", "collect"),
    [
        (
            FinancialCollector,
            _financial(report_period=date(2024, 12, 31)),
            lambda collector: collector.collect(("600519.SH",), _PERIOD, _PERIOD),
        ),
        (
            ValuationCollector,
            _valuation(as_of=datetime(2026, 4, 1, 15, 30, tzinfo=_SHANGHAI)),
            lambda collector: collector.collect(("600519.SH",), _AS_OF),
        ),
        (
            IndustryCollector,
            _industry(effective_from=date(2026, 4, 1)),
            lambda collector: collector.collect(("600519.SH",), _AS_OF.date()),
        ),
    ],
)
def test_collectors_reject_out_of_range_provider_records(
    tmp_path: Any,
    collector_factory: Callable[..., Any],
    record: Any,
    collect: Callable[[Any], Any],
) -> None:
    repository = _repository(tmp_path)
    collector = collector_factory(
        FakeFundamentalsProvider({"600519.SH": (record,)}), repository
    )
    report = collect(collector)
    assert (report.failed_symbols, report.rows_persisted) == (1, 0)


@pytest.mark.parametrize(
    "symbols",
    [(), ("600519.SH", "600519.SH"), ("600519",)],
)
def test_collectors_reject_empty_duplicate_or_noncanonical_symbols(
    tmp_path: Any, symbols: tuple[str, ...]
) -> None:
    repository = _repository(tmp_path)
    collector = FinancialCollector(FakeFundamentalsProvider({}), repository)
    with pytest.raises(CollectionDataError):
        collector.collect(symbols, _PERIOD, _PERIOD)
