"""Tests for factor data-record consistency."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.models import FactorSnapshot, FactorValue


def _as_of() -> datetime:
    """Return one shared timestamp for factor tests."""
    return datetime(2026, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai"))


def _factor_value(**changes: object) -> FactorValue:
    """Build a valid factor observation with optional overrides."""
    values: dict[str, object] = {
        "symbol": "600519.SH",
        "as_of": _as_of(),
        "factor_name": "roe",
        "factor_group": "quality",
        "raw_value": 0.2,
        "score": 80.0,
        "available": True,
    }
    values.update(changes)
    return FactorValue(**values)


def test_factor_value_validates_scores_and_availability() -> None:
    """Score ranges and available-state semantics are enforced."""
    assert _factor_value().score == 80.0
    assert _factor_value(available=False, score=None).available is False
    for changes in (
        {"score": -1.0},
        {"score": 101.0},
        {"available": False, "score": 80.0},
        {"available": True, "score": None},
        {"raw_value": float("nan")},
    ):
        with pytest.raises(ValidationError):
            _factor_value(**changes)


def test_factor_snapshot_requires_matching_unique_values() -> None:
    """Snapshots cannot mix symbols, timestamps, or duplicate factor names."""
    value = _factor_value()
    snapshot = FactorSnapshot(symbol="600519.SH", as_of=_as_of(), values=(value,))
    assert snapshot.values == (value,)
    for values in (
        (_factor_value(symbol="000001.SZ"),),
        (_factor_value(as_of=_as_of() + timedelta(days=1)),),
        (value, _factor_value()),
    ):
        with pytest.raises(ValidationError):
            FactorSnapshot(symbol="600519.SH", as_of=_as_of(), values=values)
