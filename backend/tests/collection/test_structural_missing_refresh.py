"""Offline contracts for bounded structural missing-membership planning."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.collection import (
    StructuralMissingRefreshPlan,
    StructuralMissingRefreshPlanner,
    StructuralMissingRefreshPlanRequest,
)

_AS_OF = datetime(2026, 9, 8, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_STRUCTURAL = tuple(f"{index:06d}.SZ" for index in range(1, 6))
_MISSING = ("000001.SZ", "000003.SZ", "000005.SZ")


def _request(**changes: object) -> StructuralMissingRefreshPlanRequest:
    values: dict[str, object] = {
        "as_of": _AS_OF,
        "structural_symbols": _STRUCTURAL,
        "missing_structural_symbols": _MISSING,
        "limit": 2,
        "start_after": None,
    }
    values.update(changes)
    return StructuralMissingRefreshPlanRequest(**values)


def test_accepts_bounds_empty_missing_and_covered_cursor() -> None:
    assert _request(limit=1).limit == 1
    assert _request(limit=100).limit == 100
    assert _request(missing_structural_symbols=()).missing_structural_symbols == ()
    assert _request(start_after="000002.SZ").start_after == "000002.SZ"


@pytest.mark.parametrize(
    "changes",
    (
        {"as_of": _AS_OF.replace(tzinfo=None)}, {"structural_symbols": ()},
        {"structural_symbols": ("000001.SZ", "000001.SZ")},
        {"structural_symbols": ("000002.SZ", "000001.SZ")}, {"structural_symbols": ("000001",)},
        {"missing_structural_symbols": ("000001.SZ", "000001.SZ")},
        {"missing_structural_symbols": ("000003.SZ", "000001.SZ")}, {"missing_structural_symbols": ("000001",)},
        {"missing_structural_symbols": ("600519.SH",)}, {"limit": 0}, {"limit": 101},
        {"start_after": "000001"}, {"start_after": "600519.SH"},
    ),
)
def test_rejects_invalid_request_contract(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _request(**changes)


def test_uses_exact_structural_cursor_and_missing_filter() -> None:
    planner = StructuralMissingRefreshPlanner()
    initial = planner.plan(_request())
    covered_cursor = planner.plan(_request(start_after="000002.SZ"))
    missing_cursor = planner.plan(_request(start_after="000003.SZ"))
    assert initial.selected_symbols == ("000001.SZ", "000003.SZ")
    assert initial.has_more_missing_after_selection is True
    assert initial.next_start_after == "000003.SZ"
    assert covered_cursor.selected_symbols == ("000003.SZ", "000005.SZ")
    assert missing_cursor.selected_symbols == ("000005.SZ",)


def test_handles_over_100_complete_and_missing_only_before_cursor() -> None:
    structural = tuple(f"{index:06d}.SZ" for index in range(1, 102))
    large = StructuralMissingRefreshPlanner().plan(_request(structural_symbols=structural, missing_structural_symbols=structural, limit=100))
    complete = StructuralMissingRefreshPlanner().plan(_request(missing_structural_symbols=()))
    exhausted = StructuralMissingRefreshPlanner().plan(_request(start_after="000005.SZ"))
    assert len(large.selected_symbols) == 100 and large.has_more_missing_after_selection
    assert large.next_start_after == large.selected_symbols[-1]
    assert complete.selected_symbols == () and complete.selected_first_symbol is None
    assert complete.next_start_after is None and not complete.has_more_missing_after_selection
    assert exhausted.missing_structural_members == 3 and exhausted.missing_after_cursor == 0
    assert exhausted.selected_symbols == () and exhausted.next_start_after is None


@pytest.mark.parametrize(
    "update",
    (
        {"selected_symbols": ("000001.SZ",)}, {"missing_structural_members": 4},
        {"missing_after_cursor": 2}, {"selected_count": 1}, {"selected_first_symbol": "000003.SZ"},
        {"has_more_missing_after_selection": False}, {"next_start_after": None},
    ),
)
def test_report_rejects_tampered_planner_values(update: dict[str, object]) -> None:
    report = StructuralMissingRefreshPlanner().plan(_request())
    with pytest.raises(ValidationError):
        StructuralMissingRefreshPlan(**(report.model_dump() | update))
