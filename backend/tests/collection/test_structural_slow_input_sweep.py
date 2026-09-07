"""Offline contracts for bounded Task35 multi-batch sweeps."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    StructuralAdjustedReturnCollectionReport,
    StructuralCoreCollectionReport,
    StructuralCoreDomainStatus,
    StructuralCoreSymbolResult,
    StructuralSlowInputCollectionReport,
    StructuralSlowInputSweepCollector,
    StructuralSlowInputSweepReport,
    StructuralSlowInputSweepRequest,
    StructuralValuationCollectionReport,
)

_AS_OF = datetime(2026, 9, 7, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


def _symbols(count: int) -> tuple[str, ...]:
    return tuple(f"{index:06d}.SZ" for index in range(1, count + 1))


def _outer_payload(
    report: StructuralSlowInputSweepReport,
    *,
    batch_reports: tuple[StructuralSlowInputCollectionReport, ...] | None = None,
    coverage: int | None = None,
) -> dict[str, object]:
    return {
        "as_of": report.as_of,
        "requested_symbols": report.requested_symbols,
        "batch_reports": report.batch_reports if batch_reports is None else batch_reports,
        "factor_input_covered_after_run": (
            report.factor_input_covered_after_run if coverage is None else coverage
        ),
        "batch_first_symbol": report.batch_first_symbol,
        "batch_last_symbol": report.batch_last_symbol,
        "has_more_structural_members": report.has_more_structural_members,
        "next_start_after": report.next_start_after,
    }


class _Task35:
    def __init__(
        self,
        calls: list[object],
        fail_at: int | None = None,
        financial_failure_at: int | None = None,
    ) -> None:
        self.calls = calls
        self.fail_at = fail_at
        self.financial_failure_at = financial_failure_at

    def collect(self, request: object) -> object:
        self.calls.append(request)
        if self.fail_at == len(self.calls):
            raise RuntimeError("stop")
        common = {
            "requested_symbols": request.symbols,
            "batch_first_symbol": request.symbols[0],
            "batch_last_symbol": request.symbols[-1],
            "has_more_structural_members": request.has_more_structural_members,
            "next_start_after": (
                request.symbols[-1] if request.has_more_structural_members else None
            ),
        }
        financial_failed = self.financial_failure_at == len(self.calls)
        core = StructuralCoreCollectionReport.model_construct(
            as_of=request.as_of.date(),
            financial_failed=int(financial_failed),
            results=tuple(
                StructuralCoreSymbolResult(
                    symbol=symbol,
                    financial_status=(
                        StructuralCoreDomainStatus.FAILED
                        if financial_failed and index == 0
                        else StructuralCoreDomainStatus.EMPTY
                    ),
                    financial_rows_persisted=0,
                    industry_status=StructuralCoreDomainStatus.EMPTY,
                    industry_rows_persisted=0,
                )
                for index, symbol in enumerate(request.symbols)
            ),
            **common,
        )
        valuation = StructuralValuationCollectionReport.model_construct(
            as_of=request.as_of, **common
        )
        adjusted = StructuralAdjustedReturnCollectionReport.model_construct(
            as_of=request.as_of,
            start_date=request.as_of.date() - timedelta(days=179),
            end_date=request.as_of.date(),
            **common,
        )
        return StructuralSlowInputCollectionReport.model_construct(
            as_of=request.as_of, requested_symbols=request.symbols,
            core_report=core, valuation_report=valuation, adjusted_return_report=adjusted,
            factor_input_covered_after_run=len(request.symbols),
            batch_first_symbol=request.symbols[0], batch_last_symbol=request.symbols[-1],
            has_more_structural_members=request.has_more_structural_members,
            next_start_after=request.symbols[-1] if request.has_more_structural_members else None,
        )


@pytest.mark.parametrize("count,chunks", ((1, (1,)), (20, (20,)), (21, (20, 1)), (40, (20, 20)), (41, (20, 20, 1)), (100, (20, 20, 20, 20, 20))))
def test_validates_and_partitions_selected_symbols(count: int, chunks: tuple[int, ...]) -> None:
    symbols, calls = _symbols(count), []
    report = StructuralSlowInputSweepCollector(_Task35(calls)).collect(
        StructuralSlowInputSweepRequest(symbols=symbols, as_of=_AS_OF, has_more_structural_members=False)
    )
    assert tuple(len(request.symbols) for request in calls) == chunks
    assert tuple(symbol for request in calls for symbol in request.symbols) == symbols
    assert all(request.as_of == _AS_OF for request in calls)
    assert [request.has_more_structural_members for request in calls] == [True] * (len(calls) - 1) + [False]
    assert report.factor_input_covered_after_run == count


def test_request_rejects_invalid_outer_slices() -> None:
    for symbols, as_of in (((), _AS_OF), (_symbols(101), _AS_OF), (("000001.SZ", "000001.SZ"), _AS_OF), (("000002.SZ", "000001.SZ"), _AS_OF), (("000001",), _AS_OF), ((_symbols(1)), _AS_OF.replace(tzinfo=None))):
        with pytest.raises(ValidationError):
            StructuralSlowInputSweepRequest(symbols=symbols, as_of=as_of, has_more_structural_members=False)
    assert len(StructuralSlowInputSweepRequest(symbols=_symbols(100), as_of=_AS_OF, has_more_structural_members=True).symbols) == 100


def test_per_symbol_failure_continues_and_batch_exception_aborts() -> None:
    calls: list[object] = []
    collector = _Task35(calls, financial_failure_at=2)
    report = StructuralSlowInputSweepCollector(collector).collect(
        StructuralSlowInputSweepRequest(symbols=_symbols(41), as_of=_AS_OF, has_more_structural_members=False)
    )
    assert len(report.batch_reports) == 3
    assert len(calls) == 3
    failed_core = report.batch_reports[1].core_report
    assert failed_core.financial_failed == 1
    assert failed_core.results[0].financial_status is StructuralCoreDomainStatus.FAILED

    aborted_calls: list[object] = []
    with pytest.raises(RuntimeError, match="stop"):
        StructuralSlowInputSweepCollector(_Task35(aborted_calls, fail_at=2)).collect(
            StructuralSlowInputSweepRequest(symbols=_symbols(41), as_of=_AS_OF, has_more_structural_members=False)
        )
    assert len(aborted_calls) == 2


@pytest.mark.parametrize(
    "update",
    (
        {"batch_first_symbol": "000020.SZ"},
        {"batch_last_symbol": "000001.SZ"},
    ),
)
def test_report_rejects_nested_boundary_mismatch(update: dict[str, str]) -> None:
    report = StructuralSlowInputSweepCollector(_Task35([])).collect(
        StructuralSlowInputSweepRequest(symbols=_symbols(21), as_of=_AS_OF, has_more_structural_members=False)
    )
    malformed = report.batch_reports[0].model_copy(update=update)
    with pytest.raises(ValidationError):
        StructuralSlowInputSweepReport(
            **_outer_payload(report, batch_reports=(malformed, report.batch_reports[1]))
        )


def test_report_rejects_inconsistent_outer_coverage() -> None:
    report = StructuralSlowInputSweepCollector(_Task35([])).collect(
        StructuralSlowInputSweepRequest(symbols=_symbols(21), as_of=_AS_OF, has_more_structural_members=False)
    )
    with pytest.raises(ValidationError, match="sweep coverage"):
        StructuralSlowInputSweepReport(**_outer_payload(report, coverage=20))


def test_report_accepts_distinct_adjusted_availability_cutoffs() -> None:
    report = StructuralSlowInputSweepCollector(_Task35([])).collect(
        StructuralSlowInputSweepRequest(symbols=_symbols(21), as_of=_AS_OF, has_more_structural_members=False)
    )
    later_adjusted = report.batch_reports[1].adjusted_return_report.model_copy(
        update={"availability_as_of": _AS_OF + timedelta(minutes=1)}
    )
    later_batch = report.batch_reports[1].model_copy(
        update={"adjusted_return_report": later_adjusted}
    )
    validated = StructuralSlowInputSweepReport(
        **_outer_payload(report, batch_reports=(report.batch_reports[0], later_batch))
    )
    assert validated.batch_reports[1].adjusted_return_report.availability_as_of > _AS_OF
