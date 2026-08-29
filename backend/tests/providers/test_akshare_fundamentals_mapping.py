"""Offline AKShare DataFrame mapping tests for Task 09 PIT semantics."""

from datetime import date

import pandas as pd
import pytest

from stock_selector.providers.akshare_fundamentals_mapping import (
    _amount_cny,
    map_financial_records,
    map_industry_records,
    map_valuation_records,
)
from stock_selector.providers.errors import ProviderDataError


def test_financial_mapping_uses_notice_date_after_close() -> None:
    records = map_financial_records(
        pd.DataFrame(
            [
                {
                    "SECUCODE": "600519.SH",
                    "REPORT_DATE": "2025-12-31",
                    "NOTICE_DATE": "2026-03-25",
                    "ROEJQ": 15.0,
                    "TOTALOPERATEREVE": 100.0,
                }
            ]
        ),
        "600519.SH",
    )
    assert records[0].available_at.hour == 15
    assert records[0].available_at.minute == 30
    assert records[0].revenue == 100.0


def test_financial_mapping_rejects_missing_notice_date() -> None:
    with pytest.raises(ProviderDataError):
        map_financial_records(
            pd.DataFrame([{"REPORT_DATE": "2025-12-31"}]), "600519.SH"
        )


def test_valuation_mapping_normalizes_hundred_million_cny() -> None:
    records = map_valuation_records(
        {"总市值": pd.DataFrame([{"date": "2026-01-02", "value": 2.5}])}, "600519.SH"
    )
    assert records[0].as_of.date() == date(2026, 1, 2)
    assert records[0].total_market_cap == 250_000_000.0
    assert _amount_cny(2.0, "万元") == 20_000.0


def test_industry_mapping_builds_intervals_per_classification() -> None:
    records = map_industry_records(
        pd.DataFrame(
            [
                {
                    "证券代码": "600519",
                    "变更日期": "2020-01-01",
                    "分类标准": "A",
                    "行业编码": "A1",
                    "行业大类": "Alpha",
                },
                {
                    "证券代码": "600519",
                    "变更日期": "2024-01-01",
                    "分类标准": "A",
                    "行业编码": "A2",
                    "行业大类": "Alpha 2",
                },
                {
                    "证券代码": "600519",
                    "变更日期": "2020-01-01",
                    "分类标准": "B",
                    "行业编码": "B1",
                    "行业大类": "Beta",
                },
            ]
        ),
        "600519.SH",
    )
    first_a = next(
        item
        for item in records
        if item.classification == "A" and item.industry_code == "A1"
    )
    assert first_a.effective_to == date(2023, 12, 31)
    assert (
        next(item for item in records if item.classification == "B").effective_to
        is None
    )
