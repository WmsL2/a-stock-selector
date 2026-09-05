"""Offline contracts for bounded current-structural adjusted-return refresh."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    AdjustedReturnCollectionReport,
    AdjustedReturnCollectionStatus,
    AdjustedReturnSymbolResult,
    CollectionDataError,
    CollectionError,
    StructuralAdjustedReturnCollectionRequest,
    StructuralAdjustedReturnCollector,
)
from stock_selector.config import AppPaths
from stock_selector.models import AdjustedDailyReturn, AdjustmentType
from stock_selector.storage import LocalMarketRepository

_AS_OF = datetime(2026, 9, 3, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_SYMBOLS = ("000001.SZ", "000002.SZ", "600519.SH")


def _repository(tmp_path: Any) -> LocalMarketRepository:
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    return repository


def _request(**changes: Any) -> StructuralAdjustedReturnCollectionRequest:
    values = {
        "symbols": _SYMBOLS,
        "as_of": _AS_OF,
        "start_date": _AS_OF.date() - timedelta(days=179),
        "end_date": _AS_OF.date(),
        "has_more_structural_members": True,
    }
    values.update(changes)
    return StructuralAdjustedReturnCollectionRequest(**values)


def _result(symbol: str, status: AdjustedReturnCollectionStatus) -> AdjustedReturnSymbolResult:
    if status is AdjustedReturnCollectionStatus.SUCCESS:
        return AdjustedReturnSymbolResult(
            symbol=symbol, status=status, rows_received=1, rows_persisted=1,
            source="fake", observed_at=_AS_OF,
        )
    if status is AdjustedReturnCollectionStatus.EMPTY:
        return AdjustedReturnSymbolResult(symbol=symbol, status=status, rows_received=0, rows_persisted=0)
    return AdjustedReturnSymbolResult(
        symbol=symbol, status=status, rows_received=0, rows_persisted=0,
        error_type="ProviderDataError", error_message="synthetic",
    )


class FakeAdjustedCollector:
    def __init__(self, statuses: tuple[AdjustedReturnCollectionStatus, ...]) -> None:
        self.statuses = statuses
        self.requests: list[Any] = []

    def collect(self, request: Any) -> AdjustedReturnCollectionReport:
        self.requests.append(request)
        results = tuple(_result(symbol, status) for symbol, status in zip(request.symbols, self.statuses, strict=True))
        return AdjustedReturnCollectionReport(
            requested_symbols=request.symbols, start_date=request.start_date, end_date=request.end_date,
            success_symbols=sum(item.status is AdjustedReturnCollectionStatus.SUCCESS for item in results),
            empty_symbols=sum(item.status is AdjustedReturnCollectionStatus.EMPTY for item in results),
            failed_symbols=sum(item.status is AdjustedReturnCollectionStatus.FAILED for item in results),
            rows_received=sum(item.rows_received for item in results),
            rows_persisted=sum(item.rows_persisted for item in results), results=results,
        )


def _return(symbol: str, *, observed_at: datetime = _AS_OF) -> AdjustedDailyReturn:
    return AdjustedDailyReturn(
        symbol=symbol, trade_date=date(2026, 9, 2), previous_trade_date=date(2026, 9, 1),
        return_fraction=0.01, adjustment=AdjustmentType.HFQ, observed_at=observed_at, source="fake",
    )


def test_request_rejects_invalid_current_structural_batches() -> None:
    cases = (
        {"symbols": ()}, {"symbols": tuple(f"000{index:03d}.SZ" for index in range(21))},
        {"symbols": ("000001.SZ", "000001.SZ")}, {"symbols": ("600519.SH", "000001.SZ")},
        {"symbols": ("600519",)}, {"as_of": _AS_OF.replace(tzinfo=None)},
        {"start_date": _AS_OF.date(), "end_date": _AS_OF.date() - timedelta(days=1)},
        {"start_date": _AS_OF.date() - timedelta(days=180)},
        {"end_date": _AS_OF.date() - timedelta(days=1)},
    )
    for changes in cases:
        with pytest.raises(ValidationError):
            _request(**changes)


def test_structural_adjusted_return_wraps_once_preserves_outcomes_and_audits_pit(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    repository.upsert_adjusted_daily_returns((_return("000001.SZ"),))
    future = _return("600519.SH", observed_at=_AS_OF + timedelta(minutes=1))
    repository.upsert_adjusted_daily_returns((future,))
    wrapped = FakeAdjustedCollector((
        AdjustedReturnCollectionStatus.SUCCESS,
        AdjustedReturnCollectionStatus.FAILED,
        AdjustedReturnCollectionStatus.EMPTY,
    ))

    report = StructuralAdjustedReturnCollector(wrapped, repository).collect(_request())

    assert len(wrapped.requests) == 1
    assert wrapped.requests[0].symbols == _SYMBOLS
    assert (wrapped.requests[0].end_date - wrapped.requests[0].start_date).days + 1 == 180
    assert (report.success_symbols, report.empty_symbols, report.failed_symbols) == (1, 1, 1)
    assert report.adjusted_return_available_after_run == 1
    assert report.next_start_after == "600519.SH"


def test_structural_adjusted_return_report_and_wrapped_metadata_rejections(tmp_path: Any) -> None:
    repository = _repository(tmp_path)
    wrapped = FakeAdjustedCollector((AdjustedReturnCollectionStatus.EMPTY,) * 3)
    report = StructuralAdjustedReturnCollector(wrapped, repository).collect(_request())
    for update in (
        {"results": tuple(reversed(report.results))}, {"rows_received": 1},
        {"batch_first_symbol": "000002.SZ"}, {"next_start_after": None},
    ):
        with pytest.raises(ValidationError):
            type(report)(**(report.model_dump() | update))

    class BadCollector(FakeAdjustedCollector):
        def collect(self, request: Any) -> AdjustedReturnCollectionReport:
            report = super().collect(request)
            return report.model_copy(update={"end_date": request.end_date - timedelta(days=1)})

    with pytest.raises(CollectionDataError, match="mismatched"):
        StructuralAdjustedReturnCollector(BadCollector((AdjustedReturnCollectionStatus.EMPTY,) * 3), repository).collect(_request())


def test_structural_adjusted_return_propagates_storage_infrastructure_abort(tmp_path: Any) -> None:
    class FailingCollector:
        def collect(self, _request: Any) -> Any:
            raise CollectionError("adjusted-return storage infrastructure failed")

    with pytest.raises(CollectionError, match="storage infrastructure"):
        StructuralAdjustedReturnCollector(FailingCollector(), _repository(tmp_path)).collect(_request())
