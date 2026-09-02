"""Offline regressions for bounded sequential structural core refreshes."""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    CollectionDataError,
    CollectionError,
    FinancialCollector,
    IndustryCollector,
    StructuralCoreCollectionRequest,
    StructuralCoreDomainStatus,
    StructuralCoreFundamentalsCollector,
    StructuralCoreSymbolResult,
)
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
)
from stock_selector.providers.errors import ProviderDataError
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe import CurrentUniverseService

AS_OF = date(2026, 9, 2)
AT = datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
SYMBOLS = ("000001.SZ", "000002.SZ", "600000.SH", "600519.SH")


class FakeCoreProvider:
    """A symbol-indexed provider fake that records only requested core domains."""

    def __init__(
        self,
        financial: dict[str, tuple[FinancialRecord, ...] | Exception],
        industry: dict[str, tuple[IndustryRecord, ...] | Exception],
    ) -> None:
        self.financial = financial
        self.industry = industry
        self.calls: list[str] = []

    def get_financial_records(self, request: Any) -> tuple[FinancialRecord, ...]:
        symbol = request.symbols[0]
        self.calls.append(f"financial:{symbol}")
        return self._result(self.financial[symbol])

    def get_industry_records(self, request: Any) -> tuple[IndustryRecord, ...]:
        symbol = request.symbols[0]
        self.calls.append(f"industry:{symbol}")
        return self._result(self.industry[symbol])

    @staticmethod
    def _result(result: tuple[Any, ...] | Exception) -> tuple[Any, ...]:
        if isinstance(result, Exception):
            raise result
        return result


def _repository(tmp_path: Any) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _financial(symbol: str) -> FinancialRecord:
    return FinancialRecord(
        symbol=symbol,
        report_period=date(2025, 6, 30),
        announcement_date=date(2025, 8, 28),
        available_at=AT,
        revenue=100.0,
        source="fake:financial",
    )


def _industry(symbol: str) -> IndustryRecord:
    return IndustryRecord(
        symbol=symbol,
        industry_code="C15",
        industry_name="Synthetic",
        classification="CNInfo",
        effective_from=date(2020, 1, 1),
        source="fake:industry",
    )


def _collector(
    repository: LocalMarketRepository, provider: FakeCoreProvider
) -> StructuralCoreFundamentalsCollector:
    return StructuralCoreFundamentalsCollector(
        FinancialCollector(provider, repository), IndustryCollector(provider, repository), repository
    )


def _request(
    symbols: tuple[str, ...] = SYMBOLS, *, has_more: bool = False
) -> StructuralCoreCollectionRequest:
    return StructuralCoreCollectionRequest(
        symbols=symbols, as_of=AS_OF, has_more_structural_members=has_more
    )


def test_structural_core_refresh_is_sequential_and_reports_exact_audit_counts(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path)
    provider = FakeCoreProvider(
        {symbol: (_financial(symbol),) for symbol in symbols},
        {symbol: (_industry(symbol),) for symbol in symbols},
    )
    coverage_calls = 0
    original_coverage = repository.load_factor_input_symbols

    def count_coverage() -> tuple[str, ...]:
        nonlocal coverage_calls
        coverage_calls += 1
        return original_coverage()

    monkeypatch.setattr(repository, "load_factor_input_symbols", count_coverage)
    report = _collector(repository, provider).collect(_request(symbols, has_more=True))

    assert provider.calls == [
        "financial:000001.SZ",
        "industry:000001.SZ",
        "financial:600519.SH",
        "industry:600519.SH",
    ]
    assert report.financial_start_period == date(2024, 1, 1)
    assert report.financial_end_period == AS_OF
    assert (report.financial_success, report.industry_success) == (2, 2)
    assert (report.financial_rows_persisted, report.industry_rows_persisted) == (2, 2)
    assert (report.fully_successful_symbols, report.core_covered_after_run) == (2, 2)
    assert report.batch_first_symbol == "000001.SZ"
    assert report.next_start_after == "600519.SH"
    assert coverage_calls == 1


def test_structural_core_refresh_retains_partial_domain_success_and_failures(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeCoreProvider(
        {
            "000001.SZ": (_financial("000001.SZ"),),
            "000002.SZ": (_financial("000002.SZ"),),
            "600000.SH": (),
            "600519.SH": ProviderDataError("fake", "financial", "unavailable"),
        },
        {
            "000001.SZ": (_industry("000001.SZ"),),
            "000002.SZ": ProviderDataError("fake", "industry", "unavailable"),
            "600000.SH": (_industry("600000.SH"),),
            "600519.SH": (),
        },
    )

    report = _collector(repository, provider).collect(_request())

    assert (report.financial_success, report.financial_empty, report.financial_failed) == (2, 1, 1)
    assert (report.industry_success, report.industry_empty, report.industry_failed) == (2, 1, 1)
    assert (report.financial_rows_persisted, report.industry_rows_persisted) == (2, 2)
    assert report.fully_successful_symbols == 1
    assert [result.symbol for result in report.results] == list(SYMBOLS)
    assert [result.financial_status for result in report.results] == [
        StructuralCoreDomainStatus.SUCCESS,
        StructuralCoreDomainStatus.SUCCESS,
        StructuralCoreDomainStatus.EMPTY,
        StructuralCoreDomainStatus.FAILED,
    ]
    assert [result.industry_status for result in report.results] == [
        StructuralCoreDomainStatus.SUCCESS,
        StructuralCoreDomainStatus.FAILED,
        StructuralCoreDomainStatus.SUCCESS,
        StructuralCoreDomainStatus.EMPTY,
    ]
    assert repository.load_financial_records("000002.SZ") == (_financial("000002.SZ"),)
    assert repository.load_industry_records("600000.SH") == (_industry("600000.SH"),)


def test_structural_core_refresh_aborts_on_storage_infrastructure_failure(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    provider = FakeCoreProvider(
        {"600519.SH": (_financial("600519.SH"),)},
        {"600519.SH": (_industry("600519.SH"),)},
    )
    monkeypatch.setattr(
        repository,
        "upsert_financial_records",
        lambda _records: (_ for _ in ()).throw(StorageError("disk unavailable")),
    )

    with pytest.raises(CollectionError, match="storage infrastructure"):
        _collector(repository, provider).collect(_request(("600519.SH",)))
    assert provider.calls == ["financial:600519.SH"]


def test_structural_core_refresh_is_idempotent_and_unblocks_factor_input_coverage(
    tmp_path: Any,
) -> None:
    repository = _repository(tmp_path)
    provider = FakeCoreProvider(
        {"600519.SH": (_financial("600519.SH"),)},
        {"600519.SH": (_industry("600519.SH"),)},
    )
    assert repository.load_factor_input_symbols() == ()

    first = _collector(repository, provider).collect(_request(("600519.SH",)))
    second = _collector(repository, provider).collect(_request(("600519.SH",)))

    assert (first.core_covered_after_run, second.core_covered_after_run) == (1, 1)
    assert repository.load_factor_input_symbols() == ("600519.SH",)
    assert len(repository.load_financial_records("600519.SH")) == 1
    assert len(repository.load_industry_records("600519.SH")) == 1


def test_structural_core_refresh_inherits_cdr_filtered_structural_scope(tmp_path: Any) -> None:
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
    provider = FakeCoreProvider(
        {"688001.SH": (_financial("688001.SH"),)},
        {"688001.SH": (_industry("688001.SH"),)},
    )

    report = _collector(repository, provider).collect(_request(structural.members))

    assert structural.members == ("688001.SH",)
    assert report.requested_symbols == ("688001.SH",)
    assert provider.calls == ["financial:688001.SH", "industry:688001.SH"]


def test_structural_core_models_reject_invalid_requests_and_domain_rows() -> None:
    for symbols in ((), ("600519",), ("600519.SH", "600519.SH")):
        with pytest.raises(ValidationError):
            StructuralCoreCollectionRequest(
                symbols=symbols, as_of=AS_OF, has_more_structural_members=False
            )
    with pytest.raises(ValidationError):
        StructuralCoreSymbolResult(
            symbol="600519.SH",
            financial_status=StructuralCoreDomainStatus.SUCCESS,
            financial_rows_persisted=0,
            industry_status=StructuralCoreDomainStatus.EMPTY,
            industry_rows_persisted=0,
        )


def test_structural_core_rejects_impossible_one_symbol_collector_report(tmp_path: Any) -> None:
    repository = _repository(tmp_path)

    class ImpossibleFinancialCollector:
        def collect(self, *_args: Any) -> Any:
            from stock_selector.collection.fundamentals import (
                FundamentalsCollectionReport,
            )

            return FundamentalsCollectionReport(
                requested_symbols=("600519.SH",),
                succeeded_symbols=1,
                empty_symbols=1,
                failed_symbols=0,
                rows_persisted=1,
            )

    class EmptyIndustryCollector:
        def collect(self, *_args: Any) -> Any:
            from stock_selector.collection.fundamentals import (
                FundamentalsCollectionReport,
            )

            return FundamentalsCollectionReport(
                requested_symbols=("600519.SH",),
                succeeded_symbols=0,
                empty_symbols=1,
                failed_symbols=0,
                rows_persisted=0,
            )

    with pytest.raises(CollectionDataError, match="impossible"):
        StructuralCoreFundamentalsCollector(
            ImpossibleFinancialCollector(), EmptyIndustryCollector(), repository
        ).collect(_request(("600519.SH",)))
