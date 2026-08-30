from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stock_selector.realtime import RealtimeCaptureRequest


def test_capture_request_keeps_all_market_distinct_and_orders_explicit_symbols() -> (
    None
):
    assert RealtimeCaptureRequest().symbols is None
    request = RealtimeCaptureRequest(
        symbols=("600519.SH", "000001.SZ"),
        persist_symbols=("600519.SH",),
    )
    assert request.symbols == ("000001.SZ", "600519.SH")
    assert request.persist_symbols == ("600519.SH",)


@pytest.mark.parametrize(
    "values",
    [
        {"symbols": ()},
        {"symbols": ("600519.SH", "600519.SH")},
        {"symbols": ("invalid",)},
        {"persist_symbols": ("600519.SH", "600519.SH")},
        {"symbols": ("600519.SH",), "persist_symbols": ("invalid",)},
        {"symbols": ("600519.SH",), "persist_symbols": ("000001.SZ",)},
    ],
)
def test_capture_request_rejects_invalid_explicit_batches(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RealtimeCaptureRequest(**values)


def test_capture_request_does_not_create_a_timestamp() -> None:
    request = RealtimeCaptureRequest(symbols=("600519.SH",))
    assert not hasattr(request, "ingested_at")
    assert datetime(2026, 8, 30, tzinfo=UTC).tzinfo is UTC
