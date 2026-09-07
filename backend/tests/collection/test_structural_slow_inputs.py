"""Offline contracts for one bounded unified structural slow-input refresh."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    AdjustedReturnCollectionStatus,
    AdjustedReturnSymbolResult,
    CollectionDataError,
    CollectionError,
    StructuralAdjustedReturnCollectionReport,
    StructuralCoreCollectionReport,
    StructuralCoreDomainStatus,
    StructuralCoreSymbolResult,
    StructuralSlowInputCollectionReport,
    StructuralSlowInputCollectionRequest,
    StructuralSlowInputCollector,
    StructuralValuationCollectionReport,
    StructuralValuationStatus,
    StructuralValuationSymbolResult,
)

_AS_OF = datetime(2026, 9, 5, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_SYMBOLS = ("000001.SZ", "000002.SZ")


def _request(**updates: Any) -> StructuralSlowInputCollectionRequest:
    values = {"symbols": _SYMBOLS, "as_of": _AS_OF, "has_more_structural_members": True}
    values.update(updates)
    return StructuralSlowInputCollectionRequest(**values)


def _core(symbols: tuple[str, ...] = _SYMBOLS, *, failed: bool = False) -> StructuralCoreCollectionReport:
    results = tuple(StructuralCoreSymbolResult(
        symbol=symbol, financial_status=StructuralCoreDomainStatus.FAILED if failed and index == 0 else StructuralCoreDomainStatus.SUCCESS,
        financial_rows_persisted=0 if failed and index == 0 else 1,
        industry_status=StructuralCoreDomainStatus.SUCCESS, industry_rows_persisted=1,
    ) for index, symbol in enumerate(symbols))
    return StructuralCoreCollectionReport(
        as_of=_AS_OF.date(), requested_symbols=symbols, financial_start_period=date(2024, 1, 1), financial_end_period=_AS_OF.date(),
        financial_success=sum(item.financial_status is StructuralCoreDomainStatus.SUCCESS for item in results), financial_empty=0,
        financial_failed=sum(item.financial_status is StructuralCoreDomainStatus.FAILED for item in results), financial_rows_persisted=sum(item.financial_rows_persisted for item in results),
        industry_success=len(results), industry_empty=0, industry_failed=0, industry_rows_persisted=len(results),
        fully_successful_symbols=sum(item.financial_status is StructuralCoreDomainStatus.SUCCESS for item in results), core_covered_after_run=0,
        results=results, batch_first_symbol=symbols[0], batch_last_symbol=symbols[-1], has_more_structural_members=True, next_start_after=symbols[-1])


def _valuation(symbols: tuple[str, ...] = _SYMBOLS, *, as_of: datetime = _AS_OF, failed: bool = False) -> StructuralValuationCollectionReport:
    results = tuple(StructuralValuationSymbolResult(symbol=symbol, status=StructuralValuationStatus.FAILED if failed and index == 0 else StructuralValuationStatus.SUCCESS, rows_persisted=0 if failed and index == 0 else 1) for index, symbol in enumerate(symbols))
    return StructuralValuationCollectionReport(as_of=as_of, requested_symbols=symbols, success_symbols=sum(item.status is StructuralValuationStatus.SUCCESS for item in results), empty_symbols=0, failed_symbols=sum(item.status is StructuralValuationStatus.FAILED for item in results),
        rows_persisted=sum(item.rows_persisted for item in results), valuation_available_after_run=len(results), results=results, batch_first_symbol=symbols[0], batch_last_symbol=symbols[-1], has_more_structural_members=True, next_start_after=symbols[-1])


def _adjusted(symbols: tuple[str, ...] = _SYMBOLS, *, start_date: date | None = None) -> StructuralAdjustedReturnCollectionReport:
    results = tuple(AdjustedReturnSymbolResult(symbol=symbol, status=AdjustedReturnCollectionStatus.SUCCESS, rows_received=1, rows_persisted=1, source="fake", observed_at=_AS_OF) for symbol in symbols)
    end = _AS_OF.date()
    return StructuralAdjustedReturnCollectionReport(as_of=_AS_OF, availability_as_of=_AS_OF, start_date=start_date or end - timedelta(days=179), end_date=end,
        requested_symbols=symbols, success_symbols=len(results), empty_symbols=0, failed_symbols=0, rows_received=len(results), rows_persisted=len(results), adjusted_return_available_after_run=len(results), results=results,
        batch_first_symbol=symbols[0], batch_last_symbol=symbols[-1], has_more_structural_members=True, next_start_after=symbols[-1])


class _Stage:
    def __init__(self, report: Any, calls: list[str], name: str, error: Exception | None = None) -> None:
        self.report, self.calls, self.name, self.error = report, calls, name, error
        self.requests: list[Any] = []
    def collect(self, request: Any) -> Any:
        self.calls.append(self.name)
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.report


class _Repository:
    def __init__(self, members: set[str]) -> None:
        self.members, self.calls = members, 0
    def load_factor_input_symbols(self) -> tuple[str, ...]:
        self.calls += 1
        return tuple(sorted(self.members))


def test_request_rejects_invalid_batches_and_accepts_boundaries() -> None:
    cases = ({"symbols": ()}, {"symbols": tuple(f"000{index:03d}.SZ" for index in range(21))}, {"symbols": ("000001.SZ", "000001.SZ")}, {"symbols": ("000002.SZ", "000001.SZ")}, {"symbols": ("000001",)}, {"as_of": _AS_OF.replace(tzinfo=None)})
    for changes in cases:
        with pytest.raises(ValidationError):
            _request(**changes)
    assert len(_request(symbols=("000001.SZ",)).symbols) == 1
    assert len(_request(symbols=tuple(f"{index:06d}.SZ" for index in range(1, 21))).symbols) == 20


def test_runs_existing_collectors_once_in_order_and_audits_final_membership() -> None:
    calls: list[str] = []
    repository = _Repository(set())
    core, valuation, adjusted = _Stage(_core(), calls, "core"), _Stage(_valuation(), calls, "valuation"), _Stage(_adjusted(), calls, "adjusted")
    original_collect = valuation.collect
    def valuation_collect(request: Any) -> Any:
        repository.members.add("000002.SZ")
        return original_collect(request)
    valuation.collect = valuation_collect
    request = _request()
    report = StructuralSlowInputCollector(core, valuation, adjusted, repository).collect(request)
    assert calls == ["core", "valuation", "adjusted"]
    assert repository.calls == 1
    assert report.factor_input_covered_after_run == 1
    assert report.adjusted_return_report.start_date == _AS_OF.date() - timedelta(days=179)
    assert report.adjusted_return_report.end_date == _AS_OF.date()
    assert core.requests[0].symbols == request.symbols and core.requests[0].as_of == request.as_of.date()
    assert valuation.requests[0].symbols == request.symbols and valuation.requests[0].as_of == request.as_of
    assert adjusted.requests[0].symbols == request.symbols and adjusted.requests[0].as_of == request.as_of
    assert (adjusted.requests[0].end_date - adjusted.requests[0].start_date).days + 1 == 180


def test_per_symbol_failure_continues_but_contract_or_infrastructure_stops_later_stages() -> None:
    calls: list[str] = []
    collector = StructuralSlowInputCollector(_Stage(_core(failed=True), calls, "core"), _Stage(_valuation(), calls, "valuation"), _Stage(_adjusted(), calls, "adjusted"), _Repository(set()))
    assert collector.collect(_request()).core_report.financial_failed == 1
    assert calls == ["core", "valuation", "adjusted"]
    calls.clear()
    abort = StructuralSlowInputCollector(_Stage(_core(), calls, "core", CollectionError("stop")), _Stage(_valuation(), calls, "valuation"), _Stage(_adjusted(), calls, "adjusted"), _Repository(set()))
    with pytest.raises(CollectionError): abort.collect(_request())
    assert calls == ["core"]


def test_valuation_failure_continues_and_later_infrastructure_aborts_skip_audit() -> None:
    calls: list[str] = []
    repository = _Repository(set())
    report = StructuralSlowInputCollector(_Stage(_core(), calls, "core"), _Stage(_valuation(failed=True), calls, "valuation"), _Stage(_adjusted(), calls, "adjusted"), repository).collect(_request())
    assert calls == ["core", "valuation", "adjusted"] and report.valuation_report.failed_symbols == 1
    for failing_stage, expected in (("valuation", ["core", "valuation"]), ("adjusted", ["core", "valuation", "adjusted"])):
        calls.clear()
        stages = (_Stage(_core(), calls, "core"), _Stage(_valuation(), calls, "valuation", CollectionError("stop") if failing_stage == "valuation" else None), _Stage(_adjusted(), calls, "adjusted", CollectionError("stop") if failing_stage == "adjusted" else None))
        repository = _Repository(set())
        with pytest.raises(CollectionError): StructuralSlowInputCollector(*stages, repository).collect(_request())
        assert calls == expected and repository.calls == 0


@pytest.mark.parametrize("stage,report", (("valuation", _valuation(as_of=_AS_OF + timedelta(seconds=1))), ("adjusted", _adjusted(start_date=_AS_OF.date() - timedelta(days=178))), ("core", _core().model_copy(update={"next_start_after": "000001.SZ"}))))
def test_rejects_nested_metadata_before_later_stage(stage: str, report: Any) -> None:
    calls: list[str] = []
    stages = {"core": _Stage(report if stage == "core" else _core(), calls, "core"), "valuation": _Stage(report if stage == "valuation" else _valuation(), calls, "valuation"), "adjusted": _Stage(report if stage == "adjusted" else _adjusted(), calls, "adjusted")}
    with pytest.raises(CollectionDataError): StructuralSlowInputCollector(stages["core"], stages["valuation"], stages["adjusted"], _Repository(set())).collect(_request())
    assert calls == (["core"] if stage == "core" else ["core", "valuation"] if stage == "valuation" else ["core", "valuation", "adjusted"])
    calls.clear()
    mismatch = StructuralSlowInputCollector(_Stage(_core(("000001.SZ",)), calls, "core"), _Stage(_valuation(), calls, "valuation"), _Stage(_adjusted(), calls, "adjusted"), _Repository(set()))
    with pytest.raises(CollectionDataError): mismatch.collect(_request())
    assert calls == ["core"]


def test_outer_report_rejects_impossible_coverage_and_cursor() -> None:
    valid = StructuralSlowInputCollectionReport(
        as_of=_AS_OF, requested_symbols=_SYMBOLS, core_report=_core(),
        valuation_report=_valuation(), adjusted_return_report=_adjusted(),
        factor_input_covered_after_run=0, batch_first_symbol=_SYMBOLS[0],
        batch_last_symbol=_SYMBOLS[-1], has_more_structural_members=True,
        next_start_after=_SYMBOLS[-1],
    )
    for update in (
        {"factor_input_covered_after_run": len(_SYMBOLS) + 1},
        {"next_start_after": _SYMBOLS[0]},
    ):
        with pytest.raises(ValidationError):
            StructuralSlowInputCollectionReport(**(valid.model_dump() | update))
