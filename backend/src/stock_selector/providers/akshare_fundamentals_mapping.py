"""Narrow, tested mappings for AKShare point-in-time fundamentals domains."""

from collections.abc import Mapping
from datetime import date, datetime, time
from math import isfinite
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd

from stock_selector.models import FinancialRecord, IndustryRecord, ValuationRecord
from stock_selector.providers.errors import ProviderDataError

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_AVAILABLE_TIME = time(15, 30)
_MISSING_MARKERS = {"", "-", "—", "亏损", "nan", "none", "null"}


def map_financial_records(
    frame: pd.DataFrame, symbol: str
) -> tuple[FinancialRecord, ...]:
    """Map Eastmoney records only when their reported notice date is trustworthy."""
    _require_columns(frame, {"SECUCODE", "REPORT_DATE", "NOTICE_DATE"}, "financial")
    records: list[FinancialRecord] = []
    for raw_row in frame.to_dict(orient="records"):
        row = cast(dict[str, Any], raw_row)
        _require_matching_symbol(row, symbol, "financial")
        report_period = _parse_date(row.get("REPORT_DATE"), "REPORT_DATE")
        announcement_date = _parse_date(row.get("NOTICE_DATE"), "NOTICE_DATE")
        values = {
            "roe": _number(row.get("ROEJQ")),
            "roa": _number(row.get("ZZCJLL")),
            "gross_margin": _number(row.get("XSMLL")),
            "net_margin": _number(row.get("XSJLL")),
            "revenue": _amount_cny(row.get("TOTALOPERATEREVE"), "CNY"),
            "net_profit": _amount_cny(row.get("PARENTNETPROFIT"), "CNY"),
            "deducted_net_profit": _amount_cny(row.get("KCFJCXSYJLR"), "CNY"),
            "operating_cash_flow": _amount_cny(row.get("NCO_OP"), "CNY"),
            "total_assets": _amount_cny(row.get("TOTAL_ASSETS"), "CNY"),
            "total_liabilities": _amount_cny(row.get("TOTAL_LIABILITIES"), "CNY"),
        }
        if not any(value is not None for value in values.values()):
            continue
        records.append(
            FinancialRecord(
                symbol=symbol,
                report_period=report_period,
                announcement_date=announcement_date,
                available_at=datetime.combine(
                    announcement_date, _AVAILABLE_TIME, _SHANGHAI
                ),
                source="akshare:stock_financial_analysis_indicator_em",
                **values,
            )
        )
    return tuple(
        sorted(records, key=lambda item: (item.report_period, item.available_at))
    )


def map_valuation_records(
    frames: Mapping[str, pd.DataFrame], symbol: str
) -> tuple[ValuationRecord, ...]:
    """Map Baidu's dated daily series; market capitalization is supplied in 亿元."""
    by_date: dict[date, dict[str, float | None]] = {}
    fields = {
        "市盈率(TTM)": "pe",
        "市净率": "pb",
        "市现率": "pcf",
        "总市值": "total_market_cap",
    }
    for indicator, field_name in fields.items():
        frame = frames.get(indicator)
        if frame is None:
            continue
        _require_columns(frame, {"date", "value"}, f"valuation {indicator}")
        for raw_row in frame.to_dict(orient="records"):
            row = cast(dict[str, Any], raw_row)
            observation_date = _parse_date(row.get("date"), "valuation date")
            value = _number(row.get("value"))
            if field_name == "total_market_cap":
                value = _amount_cny(value, "亿元")
            by_date.setdefault(observation_date, {})[field_name] = value
    records = []
    for observation_date, values in by_date.items():
        complete = {field: values.get(field) for field in fields.values()}
        if not any(value is not None for value in complete.values()):
            continue
        records.append(
            ValuationRecord(
                symbol=symbol,
                as_of=datetime.combine(observation_date, _AVAILABLE_TIME, _SHANGHAI),
                source="akshare:stock_zh_valuation_baidu",
                **complete,
            )
        )
    return tuple(sorted(records, key=lambda item: item.as_of))


def map_industry_records(
    frame: pd.DataFrame, symbol: str
) -> tuple[IndustryRecord, ...]:
    """Map CNInfo change events to inclusive intervals without inventing a prehistory."""
    _require_columns(
        frame,
        {"证券代码", "变更日期", "分类标准", "行业编码", "行业大类"},
        "industry",
    )
    events = []
    for raw_row in frame.to_dict(orient="records"):
        row = cast(dict[str, Any], raw_row)
        _require_matching_symbol(row, symbol, "industry", column="证券代码")
        events.append(
            (
                _parse_date(row.get("变更日期"), "变更日期"),
                str(row["分类标准"]).strip(),
                str(row["行业编码"]).strip(),
                str(row["行业大类"]).strip(),
            )
        )
    records: list[IndustryRecord] = []
    by_classification: dict[str, list[tuple[date, str, str]]] = {}
    for effective_from, classification, code, name in events:
        if not classification or not code or not name:
            raise ProviderDataError(
                "akshare", "stock_industry_change_cninfo", "incomplete industry row"
            )
        by_classification.setdefault(classification, []).append(
            (effective_from, code, name)
        )

    for classification, classification_events in by_classification.items():
        by_effective_from: dict[date, tuple[str, str]] = {}
        for effective_from, code, name in classification_events:
            existing = by_effective_from.setdefault(effective_from, (code, name))
            if existing != (code, name):
                raise ProviderDataError(
                    "akshare",
                    "stock_industry_change_cninfo",
                    "conflicting industry rows at the same effective date",
                )
        ordered_events = sorted(by_effective_from.items())
        for index, (effective_from, (code, name)) in enumerate(ordered_events):
            next_from = (
                ordered_events[index + 1][0]
                if index + 1 < len(ordered_events)
                else None
            )
            effective_to = (
                None
                if next_from is None
                else date.fromordinal(next_from.toordinal() - 1)
            )
            records.append(
                IndustryRecord(
                    symbol=symbol,
                    industry_code=code,
                    industry_name=name,
                    classification=classification,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    source="akshare:stock_industry_change_cninfo",
                )
            )
    return tuple(
        sorted(records, key=lambda item: (item.classification, item.effective_from))
    )


def _require_columns(frame: pd.DataFrame, required: set[str], operation: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ProviderDataError(
            "akshare", operation, f"missing required columns: {sorted(missing)}"
        )


def _require_matching_symbol(
    row: Mapping[str, Any], symbol: str, operation: str, *, column: str = "SECUCODE"
) -> None:
    returned = row.get(column)
    if returned is None:
        raise ProviderDataError(
            provider="akshare", operation=operation, message=f"missing {column}"
        )
    value = str(returned).strip().upper()
    expected = symbol if column == "SECUCODE" else symbol.split(".", maxsplit=1)[0]
    if not value or value != expected:
        raise ProviderDataError(
            "akshare", operation, "provider returned a different symbol"
        )


def _parse_date(value: Any, field_name: str) -> date:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ProviderDataError("akshare", "mapping", f"invalid {field_name}")
    return cast(date, parsed.date())


def _number(value: Any) -> float | None:
    if value is None or (
        isinstance(value, str) and value.strip().casefold() in _MISSING_MARKERS
    ):
        return None
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    result = float(parsed)
    return result if isfinite(result) else None


def _amount_cny(value: Any, unit: str) -> float | None:
    """Normalize explicit CNY, 万元, and 亿元 values to CNY without guessing units."""
    parsed = _number(value)
    if parsed is None:
        return None
    multipliers = {"CNY": 1.0, "万元": 10_000.0, "亿元": 100_000_000.0}
    try:
        return parsed * multipliers[unit]
    except KeyError as exc:
        raise ProviderDataError(
            "akshare", "mapping", f"unsupported amount unit: {unit}"
        ) from exc
