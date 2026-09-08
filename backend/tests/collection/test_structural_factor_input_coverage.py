"""Offline contracts for current structural factor-input membership coverage."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    StructuralFactorInputCoverageAuditor,
    StructuralFactorInputCoverageReport,
    StructuralFactorInputCoverageRequest,
)

_AS_OF = datetime(2026, 9, 7, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_STRUCTURAL = ("000001.SZ", "000002.SZ", "000003.SZ")


def _request(
    structural: tuple[str, ...] = _STRUCTURAL,
    factor: tuple[str, ...] = (),
    as_of: datetime = _AS_OF,
) -> StructuralFactorInputCoverageRequest:
    return StructuralFactorInputCoverageRequest(
        as_of=as_of,
        structural_symbols=structural,
        factor_input_symbols=factor,
    )


def test_request_accepts_one_structural_symbol_and_empty_factor_inputs() -> None:
    request = _request(structural=("000001.SZ",))
    assert request.factor_input_symbols == ()


def test_request_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError):
        _request(as_of=_AS_OF.replace(tzinfo=None))


@pytest.mark.parametrize(
    "structural",
    ((), ("000001.SZ", "000001.SZ"), ("000002.SZ", "000001.SZ"), ("000001",)),
)
def test_request_rejects_invalid_structural_symbols(structural: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _request(structural=structural)


@pytest.mark.parametrize(
    "factor",
    (("000001.SZ", "000001.SZ"), ("000002.SZ", "000001.SZ"), ("000001",)),
)
def test_request_rejects_invalid_factor_input_symbols(factor: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _request(factor=factor)


def test_auditor_returns_exact_partition_and_deterministic_ordering() -> None:
    report = StructuralFactorInputCoverageAuditor().audit(
        _request(factor=("000002.SZ", "000003.SZ", "600519.SH"))
    )
    assert report.covered_structural_symbols == ("000002.SZ", "000003.SZ")
    assert report.missing_structural_symbols == ("000001.SZ",)
    assert report.nonstructural_factor_input_symbols == ("600519.SH",)
    assert (
        report.structural_members,
        report.stored_factor_input_symbols,
        report.structural_factor_input_covered,
        report.structural_factor_input_missing,
        report.nonstructural_stored_factor_input_symbols,
    ) == (3, 3, 2, 1, 1)
    assert (report.first_missing_symbol, report.last_missing_symbol) == (
        "000001.SZ",
        "000001.SZ",
    )


def test_complete_and_zero_coverage_are_valid() -> None:
    auditor = StructuralFactorInputCoverageAuditor()
    complete = auditor.audit(_request(factor=_STRUCTURAL))
    zero = auditor.audit(_request())
    assert complete.missing_structural_symbols == ()
    assert (complete.first_missing_symbol, complete.last_missing_symbol) == (None, None)
    assert zero.covered_structural_symbols == ()
    assert zero.missing_structural_symbols == _STRUCTURAL
    assert (zero.first_missing_symbol, zero.last_missing_symbol) == (
        "000001.SZ",
        "000003.SZ",
    )


@pytest.mark.parametrize(
    "update",
    (
        {"structural_members": 4},
        {"covered_structural_symbols": ("000001.SZ",)},
        {"first_missing_symbol": "000002.SZ"},
        {"nonstructural_factor_input_symbols": ("000001.SZ",)},
    ),
)
def test_report_rejects_inconsistent_partition_metadata_or_counts(
    update: dict[str, object],
) -> None:
    report = StructuralFactorInputCoverageAuditor().audit(
        _request(factor=("000002.SZ", "600519.SH"))
    )
    with pytest.raises(ValidationError):
        StructuralFactorInputCoverageReport(**(report.model_dump() | update))
