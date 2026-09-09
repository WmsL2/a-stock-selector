"""Pure contracts for current daily-selection upstream readiness."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.selection import (
    DailySelectionInputReadinessAuditor,
    DailySelectionInputReadinessBlocker,
    DailySelectionInputReadinessRequest,
)

NOW = datetime(2026, 9, 8, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
STRUCTURAL = ("000001.SZ", "000002.SZ", "600519.SH")


def _request(**changes: object) -> DailySelectionInputReadinessRequest:
    values: dict[str, object] = {
        "as_of": NOW,
        "structural_symbols": STRUCTURAL,
        "risk_record_symbols": STRUCTURAL,
        "risk_complete_symbols": STRUCTURAL,
        "risk_eligible_symbols": ("000001.SZ", "000002.SZ"),
        "factor_input_symbols": ("000001.SZ", "000002.SZ"),
    }
    values.update(changes)
    return DailySelectionInputReadinessRequest(**values)


@pytest.mark.parametrize(
    "changes",
    (
        {"as_of": NOW.replace(tzinfo=None)},
        {"structural_symbols": ()},
        {"structural_symbols": ("000001.SZ", "000001.SZ")},
        {"structural_symbols": tuple(reversed(STRUCTURAL))},
        {"risk_record_symbols": ("000003.SZ",)},
        {"risk_complete_symbols": ("000001.SZ",), "risk_record_symbols": ()},
        {"risk_eligible_symbols": ("000001.SZ",), "risk_complete_symbols": ()},
        {"factor_input_symbols": ("000002.SZ", "000001.SZ")},
    ),
)
def test_request_rejects_invalid_contracts(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _request(**changes)


@pytest.mark.parametrize(
    "changes",
    (
        {"structural_symbols": ("invalid",)},
        {"risk_record_symbols": ("000001.SZ", "000001.SZ")},
        {"risk_record_symbols": ("000002.SZ", "000001.SZ")},
        {"risk_record_symbols": ("invalid",)},
        {"risk_record_symbols": ("300001.SZ",)},
        {"risk_complete_symbols": ("000001.SZ", "000001.SZ")},
        {"risk_complete_symbols": ("000002.SZ", "000001.SZ")},
        {"risk_complete_symbols": ("invalid",)},
        {"risk_complete_symbols": ("000001.SZ",), "risk_record_symbols": ()},
        {"risk_eligible_symbols": ("000001.SZ", "000001.SZ")},
        {"risk_eligible_symbols": ("000002.SZ", "000001.SZ")},
        {"risk_eligible_symbols": ("invalid",)},
        {"risk_eligible_symbols": ("000001.SZ",), "risk_complete_symbols": ()},
        {"factor_input_symbols": ("000001.SZ", "000001.SZ")},
        {"factor_input_symbols": ("000002.SZ", "000001.SZ")},
        {"factor_input_symbols": ("invalid",)},
    ),
)
def test_request_validation_matrix_rejects_invalid_symbol_tuples(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _request(**changes)


def test_empty_factor_input_symbols_are_accepted() -> None:
    assert _request(factor_input_symbols=()).factor_input_symbols == ()


def test_ready_allows_risk_ineligible_structural_factor_gap() -> None:
    report = DailySelectionInputReadinessAuditor().audit(_request())
    assert report.upstream_inputs_ready is True
    assert report.blockers == ()
    assert report.eligible_factor_input_missing_symbols == ()
    assert report.structural_members == 3


@pytest.mark.parametrize(
    ("changes", "blocker"),
    (
        (
            {"risk_complete_symbols": ("000001.SZ",), "risk_eligible_symbols": ()},
            DailySelectionInputReadinessBlocker.RISK_STATE_COVERAGE_INCOMPLETE,
        ),
        (
            {"risk_eligible_symbols": ()},
            DailySelectionInputReadinessBlocker.NO_RISK_ELIGIBLE_MEMBERS,
        ),
        (
            {"factor_input_symbols": ("000001.SZ",)},
            DailySelectionInputReadinessBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,
        ),
    ),
)
def test_not_ready_blockers_are_exact(changes: dict[str, object], blocker: DailySelectionInputReadinessBlocker) -> None:
    report = DailySelectionInputReadinessAuditor().audit(_request(**changes))
    assert report.upstream_inputs_ready is False
    assert report.blockers == (blocker,)


def test_nonstructural_factor_symbols_do_not_affect_eligible_coverage() -> None:
    report = DailySelectionInputReadinessAuditor().audit(
        _request(factor_input_symbols=("000001.SZ", "000002.SZ", "300001.SZ"))
    )
    assert report.stored_factor_input_symbols == 3
    assert report.eligible_factor_input_covered == 2
    assert report.upstream_inputs_ready is True


def test_incomplete_risk_partition_and_boundaries_are_exact() -> None:
    report = DailySelectionInputReadinessAuditor().audit(
        _request(
            risk_complete_symbols=("000001.SZ",),
            risk_eligible_symbols=(),
        )
    )
    assert report.risk_incomplete_symbols == ("000002.SZ", "600519.SH")
    assert report.risk_incomplete_members == 2
    assert (report.risk_incomplete_first_symbol, report.risk_incomplete_last_symbol) == (
        "000002.SZ", "600519.SH"
    )
    assert report.blockers == (DailySelectionInputReadinessBlocker.RISK_STATE_COVERAGE_INCOMPLETE,)


def test_eligible_factor_partitions_follow_structural_order() -> None:
    report = DailySelectionInputReadinessAuditor().audit(
        _request(
            risk_eligible_symbols=("000001.SZ", "000002.SZ", "600519.SH"),
            factor_input_symbols=("000002.SZ",),
        )
    )
    assert report.eligible_factor_input_covered_symbols == ("000002.SZ",)
    assert report.eligible_factor_input_missing_symbols == ("000001.SZ", "600519.SH")
    assert (report.eligible_factor_input_covered, report.eligible_factor_input_missing) == (1, 2)
    assert (
        report.eligible_factor_input_missing_first_symbol,
        report.eligible_factor_input_missing_last_symbol,
    ) == ("000001.SZ", "600519.SH")
    assert report.blockers == (
        DailySelectionInputReadinessBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,
    )


@pytest.mark.parametrize(
    "field",
    (
        "risk_incomplete_symbols", "eligible_factor_input_covered_symbols",
        "eligible_factor_input_missing_symbols", "structural_members", "risk_records",
        "risk_complete_members", "risk_incomplete_members", "risk_eligible_members",
        "stored_factor_input_symbols", "eligible_factor_input_covered",
        "eligible_factor_input_missing", "risk_incomplete_first_symbol",
        "risk_incomplete_last_symbol", "eligible_factor_input_missing_first_symbol",
        "eligible_factor_input_missing_last_symbol", "upstream_inputs_ready", "blockers",
    ),
)
def test_report_rejects_tampered_semantics(field: str) -> None:
    report = DailySelectionInputReadinessAuditor().audit(_request())
    value = getattr(report, field)
    replacement = 99 if isinstance(value, int) else ("600519.SH",) if isinstance(value, tuple) else "000001.SZ" if value is None else not value
    with pytest.raises(ValidationError):
        report.model_copy(update={field: replacement}, deep=True).model_validate(
            report.model_copy(update={field: replacement}, deep=True).model_dump()
        )
