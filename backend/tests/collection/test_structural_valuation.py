"""Offline regressions for bounded current structural valuation refresh."""

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    CollectionDataError,
    CollectionError,
    StructuralValuationCollectionRequest,
    StructuralValuationCollector,
    StructuralValuationStatus,
)
from stock_selector.collection.fundamentals import (
    FundamentalsCollectionReport,
    ValuationCollector,
)
from stock_selector.config import AppPaths, Settings
from stock_selector.models import Board, Exchange, Instrument, ValuationRecord
from stock_selector.providers import AKShareProvider
from stock_selector.providers import akshare_provider as provider_module
from stock_selector.providers.errors import ProviderDataError
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe import CurrentUniverseService

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_AS_OF = datetime(2026, 9, 2, 16, tzinfo=_SHANGHAI)
_SYMBOLS = ("000001.SZ", "000002.SZ", "600519.SH")


class FakeValuationProvider:
    """A symbol-indexed valuation fake with no other collection surface."""

    def __init__(self, results: dict[str, tuple[ValuationRecord, ...] | Exception]) -> None:
        self._results = results
        self.calls: list[tuple[str, datetime]] = []

    def get_valuation_records(self, request: Any) -> tuple[ValuationRecord, ...]:
        symbol = request.symbols[0]
        self.calls.append((symbol, request.as_of))
        result = self._results[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def _repository(tmp_path: Any) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _valuation(symbol: str, **changes: Any) -> ValuationRecord:
    values = {
        "symbol": symbol,
        "as_of": datetime(2026, 9, 1, 15, 30, tzinfo=_SHANGHAI),
        "pe": 10.0,
        "pb": 1.5,
        "pcf": 8.0,
        "source": "fake:valuation",
    }
    values.update(changes)
    return ValuationRecord(**values)


def _request(
    symbols: tuple[str, ...] = _SYMBOLS,
    *,
    as_of: datetime = _AS_OF,
    has_more: bool = False,
) -> StructuralValuationCollectionRequest:
    return StructuralValuationCollectionRequest(
        symbols=symbols,
        as_of=as_of,
        has_more_structural_members=has_more,
    )


def _collector(
    repository: LocalMarketRepository, provider: FakeValuationProvider
) -> StructuralValuationCollector:
    return StructuralValuationCollector(ValuationCollector(provider, repository), repository)


def test_structural_valuation_refresh_is_sequential_and_audits_pit_availability(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeValuationProvider(
        {symbol: (_valuation(symbol),) for symbol in _SYMBOLS}
    )

    report = _collector(repository, provider).collect(_request(has_more=True))

    assert provider.calls == [(symbol, _AS_OF) for symbol in _SYMBOLS]
    assert (report.success_symbols, report.empty_symbols, report.failed_symbols) == (3, 0, 0)
    assert (report.rows_persisted, report.valuation_available_after_run) == (3, 3)
    assert report.batch_first_symbol == "000001.SZ"
    assert report.batch_last_symbol == "600519.SH"
    assert report.next_start_after == "600519.SH"


def test_structural_valuation_keeps_mixed_outcomes_and_negative_pe(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeValuationProvider(
        {
            "000001.SZ": (_valuation("000001.SZ", pe=-5.0),),
            "000002.SZ": ProviderDataError("fake", "valuation", "unavailable"),
            "600519.SH": (),
        }
    )

    report = _collector(repository, provider).collect(_request())

    assert (report.success_symbols, report.empty_symbols, report.failed_symbols) == (1, 1, 1)
    assert (report.rows_persisted, report.valuation_available_after_run) == (1, 1)
    assert [result.status for result in report.results] == [
        StructuralValuationStatus.SUCCESS,
        StructuralValuationStatus.FAILED,
        StructuralValuationStatus.EMPTY,
    ]
    assert provider.calls == [(symbol, _AS_OF) for symbol in _SYMBOLS]
    assert repository.load_latest_valuation_as_of("000001.SZ", _AS_OF).pe == -5.0


def test_structural_valuation_aborts_on_storage_infrastructure_failure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    provider = FakeValuationProvider(
        {
            "000001.SZ": (_valuation("000001.SZ"),),
            "000002.SZ": (_valuation("000002.SZ"),),
        }
    )
    monkeypatch.setattr(
        repository,
        "upsert_valuation_records",
        lambda _records: (_ for _ in ()).throw(StorageError("disk unavailable")),
    )

    with pytest.raises(CollectionError, match="storage infrastructure"):
        _collector(repository, provider).collect(_request(("000001.SZ", "000002.SZ")))
    assert provider.calls == [("000001.SZ", _AS_OF)]


def test_structural_valuation_is_idempotent_and_audits_existing_evidence(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeValuationProvider({"600519.SH": (_valuation("600519.SH"),)})
    collector = _collector(repository, provider)

    first = collector.collect(_request(("600519.SH",)))
    second = collector.collect(_request(("600519.SH",)))

    assert (first.rows_persisted, second.rows_persisted) == (1, 1)
    assert (first.valuation_available_after_run, second.valuation_available_after_run) == (1, 1)
    assert len(repository.load_valuation_records("600519.SH")) == 1


def test_structural_valuation_availability_respects_pit_visibility(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    repository.upsert_valuation_records(
        (
            _valuation("600519.SH", as_of=datetime(2026, 9, 1, 15, 30, tzinfo=_SHANGHAI)),
            _valuation("600519.SH", as_of=datetime(2026, 9, 2, 15, 30, tzinfo=_SHANGHAI)),
        )
    )
    provider = FakeValuationProvider({"600519.SH": ()})
    collector = _collector(repository, provider)

    before_close = collector.collect(
        _request(("600519.SH",), as_of=datetime(2026, 9, 2, 10, tzinfo=_SHANGHAI))
    )
    after_close = collector.collect(
        _request(("600519.SH",), as_of=datetime(2026, 9, 2, 16, tzinfo=_SHANGHAI))
    )

    assert before_close.valuation_available_after_run == 1
    assert after_close.valuation_available_after_run == 1
    assert (
        repository.load_latest_valuation_as_of(
            "600519.SH", datetime(2026, 9, 2, 10, tzinfo=_SHANGHAI)
        ).as_of
        == datetime(2026, 9, 1, 15, 30, tzinfo=_SHANGHAI)
    )
    assert (
        repository.load_latest_valuation_as_of(
            "600519.SH", datetime(2026, 9, 2, 16, tzinfo=_SHANGHAI)
        ).as_of
        == datetime(2026, 9, 2, 15, 30, tzinfo=_SHANGHAI)
    )


def test_structural_valuation_inherits_cdr_filtered_structural_scope(tmp_path: Any) -> None:
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
            Instrument(
                symbol="600519.SH",
                name="Main board",
                exchange=Exchange.SSE,
                board=Board.SH_MAIN,
                listing_date=date(2020, 1, 1),
            ),
        )
    )
    structural = CurrentUniverseService(repository, Settings()).build_current(_AS_OF.date())
    provider = FakeValuationProvider(
        {symbol: (_valuation(symbol),) for symbol in structural.members}
    )

    report = _collector(repository, provider).collect(_request(structural.members))

    assert structural.members == ("600519.SH", "688001.SH")
    assert report.requested_symbols == structural.members
    assert all(symbol != "689009.SH" for symbol, _ in provider.calls)


def test_structural_valuation_models_and_translation_reject_invalid_contracts(
    tmp_path: Any,
) -> None:
    for symbols, as_of in (
        ((), _AS_OF),
        (("600519",), _AS_OF),
        (("600519.SH", "000001.SZ"), _AS_OF),
        (("600519.SH",), datetime(2026, 9, 2, 16, tzinfo=UTC).replace(tzinfo=None)),
    ):
        with pytest.raises(ValidationError):
            StructuralValuationCollectionRequest(
                symbols=symbols,
                as_of=as_of,
                has_more_structural_members=False,
            )

    class ImpossibleValuationCollector:
        def collect(self, *_args: Any) -> FundamentalsCollectionReport:
            return FundamentalsCollectionReport(
                requested_symbols=("600519.SH",),
                succeeded_symbols=1,
                empty_symbols=1,
                failed_symbols=0,
                rows_persisted=1,
            )

    repository = _repository(tmp_path)
    with pytest.raises(CollectionDataError, match="impossible"):
        StructuralValuationCollector(ImpossibleValuationCollector(), repository).collect(
            _request(("600519.SH",))
        )


def test_valuation_indicator_final_failure_persists_no_partial_records(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    frames = {
        "市盈率(TTM)": pd.DataFrame({"date": ["2026-09-02"], "value": [10.0]}),
        "市净率": pd.DataFrame({"date": ["2026-09-02"], "value": [0.5]}),
    }
    calls: list[str] = []

    def fake_valuation(*, symbol: str, indicator: str, period: str) -> pd.DataFrame:
        assert (symbol, period) == ("600519", "全部")
        calls.append(indicator)
        if indicator == "市现率":
            raise ConnectionError("synthetic connection reset")
        return frames[indicator]

    monkeypatch.setattr(provider_module.ak, "stock_zh_valuation_baidu", fake_valuation)

    report = ValuationCollector(AKShareProvider(), repository).collect(
        ("600519.SH",), _AS_OF
    )

    assert (report.succeeded_symbols, report.empty_symbols, report.failed_symbols) == (0, 0, 1)
    assert report.rows_persisted == 0
    assert calls == ["市盈率(TTM)", "市净率", "市现率", "市现率"]
    assert repository.load_valuation_records("600519.SH") == ()
