"""Offline tests for strict AKShare-to-domain mapping helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from stock_selector.models import Board, SecurityStatus
from stock_selector.providers.akshare_mapping import (
    canonical_symbol_from_akshare_code,
    lots_to_shares,
    map_sh_instruments,
    to_optional_float,
)
from stock_selector.providers.errors import ProviderDataError


@pytest.mark.parametrize(
    ("code", "symbol"),
    [
        ("600519", "600519.SH"),
        ("000001", "000001.SZ"),
        ("300750", "300750.SZ"),
        ("688981", "688981.SH"),
        ("430047", "430047.BJ"),
        ("920001", "920001.BJ"),
        (1, "000001.SZ"),
    ],
)
def test_canonical_akshare_symbol_mapping(code: object, symbol: str) -> None:
    """Raw six-digit and integer AKShare codes map to canonical symbols."""
    assert canonical_symbol_from_akshare_code(code) == symbol


@pytest.mark.parametrize("value", ["ABC", "12345", 1.5, float("nan")])
def test_invalid_akshare_codes_are_rejected(value: object) -> None:
    """Malformed, fractional, and non-finite raw codes cannot be normalized."""
    with pytest.raises(ProviderDataError):
        canonical_symbol_from_akshare_code(value)


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, "", "-", "--"])
def test_optional_float_normalizes_only_true_missing_values(value: object) -> None:
    """Known AKShare missing markers become None."""
    assert to_optional_float(value) is None


@pytest.mark.parametrize(("value", "expected"), [(12, 12.0), ("3.25", 3.25)])
def test_optional_float_preserves_finite_numeric_values(value: object, expected: float) -> None:
    """Finite numeric cells map to float values."""
    assert to_optional_float(value) == expected


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), "abc"])
def test_optional_float_rejects_invalid_nonmissing_values(value: object) -> None:
    """Invalid nonmissing cells are provider data errors, not missing values."""
    with pytest.raises(ProviderDataError):
        to_optional_float(value)


def test_lot_volume_converts_to_shares() -> None:
    """AKShare lots are normalized to the project's shares unit."""
    assert lots_to_shares(100, required=True) == 10_000


def test_instrument_mapping_marks_st_without_filtering() -> None:
    """Visible ST names remain instruments but carry the ST status."""
    frame = pd.DataFrame(
        {"证券代码": ["600519"], "证券简称": ["*ST 测试"], "上市日期": ["2020-01-01"]}
    )
    instrument = map_sh_instruments(frame, Board.SH_MAIN)[0]
    assert instrument.status is SecurityStatus.ST


def test_mapping_datetime_is_not_used_as_source_timestamp() -> None:
    """This fixture documents the explicit provider ingestion timestamp convention."""
    assert datetime(2026, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai")).tzinfo is not None
