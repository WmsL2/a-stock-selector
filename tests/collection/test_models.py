"""Collection request and report model tests."""

from datetime import date

import pytest
from pydantic import ValidationError

from stock_selector.collection import DailyCollectionRequest
from stock_selector.models import AdjustmentType


def test_request_canonicalizes_symbol_order_and_rejects_non_raw_ranges() -> None:
    request = DailyCollectionRequest(
        symbols=("600519.SH", "000001.SZ"),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 7),
    )
    assert request.symbols == ("000001.SZ", "600519.SH")
    with pytest.raises(ValidationError):
        DailyCollectionRequest(
            symbols=("600519.SH",),
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 3),
        )
    with pytest.raises(ValidationError):
        DailyCollectionRequest(
            symbols=("600519.SH",),
            start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 7),
            adjustment=AdjustmentType.QFQ,
        )
