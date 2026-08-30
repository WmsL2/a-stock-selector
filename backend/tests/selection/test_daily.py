"""Synthetic local-repository integration tests for daily selection safety."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    ValuationRecord,
)
from stock_selector.risk import DatedRiskState
from stock_selector.selection import DailySelectionService, SelectionBlocker
from stock_selector.storage import LocalMarketRepository

_AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_CLASSIFICATION = "证监会行业分类标准（2012）"


def _repository(tmp_path) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(
        tuple(_instrument(symbol) for symbol in ("000001.SZ", "600519.SH", "601398.SH"))
    )
    return repository


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _risk(symbol: str, **changes: bool | None) -> DatedRiskState:
    values: dict[str, object] = {
        "symbol": symbol,
        "as_of": _AS_OF.date(),
        "is_st": False,
        "is_suspended": False,
        "is_delisting_period": False,
        "observed_at": _AS_OF,
        "source": "synthetic",
    }
    values.update(changes)
    return DatedRiskState(**values)


def _financial(symbol: str, period: date, value: float, available_at: datetime | None = None) -> FinancialRecord:
    return FinancialRecord(
        symbol=symbol,
        report_period=period,
        announcement_date=(available_at or _AS_OF - timedelta(days=10)).date(),
        available_at=available_at or _AS_OF - timedelta(days=10),
        roe=value,
        roa=value,
        gross_margin=value,
        net_margin=value,
        revenue=100 + value,
        net_profit=100 + value,
        deducted_net_profit=100 + value,
        source="synthetic",
    )


def _seed_factor_inputs(repository: LocalMarketRepository) -> None:
    for symbol in ("000001.SZ", "600519.SH", "601398.SH"):
        repository.upsert_financial_records(
            (
                _financial(symbol, date(2024, 12, 31), 10),
                _financial(symbol, date(2025, 12, 31), 10),
            )
        )
        repository.upsert_valuation_records(
            (
                ValuationRecord(
                    symbol=symbol,
                    as_of=_AS_OF - timedelta(days=1),
                    pe=10,
                    pb=2,
                    pcf=5,
                    source="synthetic",
                ),
            )
        )
        repository.upsert_industry_records(
            (
                IndustryRecord(
                    symbol=symbol,
                    industry_code="C15",
                    industry_name="酒、饮料和精制茶制造业",
                    classification=_CLASSIFICATION,
                    effective_from=date(2020, 1, 1),
                    source="synthetic",
                ),
            )
        )


def test_complete_safe_risk_builds_qvg_only_ranked_selection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in ("000001.SZ", "600519.SH", "601398.SH")))
    result = DailySelectionService(repository, Settings()).build(_AS_OF)
    assert result.diagnostics.selection_ready is True
    assert result.diagnostics.risk_coverage_ratio == 1
    assert result.diagnostics.factor_input_members == 3
    assert result.diagnostics.scoreable_members == 3
    assert [item.symbol for item in result.selection.items] == ["000001.SZ", "600519.SH", "601398.SH"]
    assert [item.market_rank for item in result.selection.items] == [1, 2, 3]
    assert all(item.data_completeness == pytest.approx(0.75) for item in result.selection.items)
    assert all(item.momentum_score is None and item.low_volatility_score is None for item in result.selection.items)


def test_missing_or_unknown_risk_blocks_official_items(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    missing = DailySelectionService(repository, Settings()).build(_AS_OF)
    assert missing.selection.items == ()
    assert SelectionBlocker.RISK_STATE_COVERAGE_INCOMPLETE in missing.diagnostics.blockers

    repository.upsert_risk_states(
        (
            _risk("000001.SZ"),
            _risk("600519.SH", is_st=None),
            _risk("601398.SH"),
        )
    )
    unknown = DailySelectionService(repository, Settings()).build(_AS_OF)
    assert unknown.selection.items == ()
    assert unknown.diagnostics.risk_complete_members == 2
    assert SelectionBlocker.RISK_STATE_COVERAGE_INCOMPLETE in unknown.diagnostics.blockers


def test_st_and_suspension_are_ineligible_even_with_full_coverage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    repository.upsert_risk_states(
        (
            _risk("000001.SZ"),
            _risk("600519.SH", is_st=True),
            _risk("601398.SH", is_suspended=True),
        )
    )
    result = DailySelectionService(repository, Settings()).build(_AS_OF)
    assert result.diagnostics.selection_ready is True
    assert result.diagnostics.risk_eligible_members == 1
    assert [item.symbol for item in result.selection.items] == ["000001.SZ"]


def test_pit_financial_prior_valuation_and_industry_assembly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    symbol = "600519.SH"
    repository.upsert_financial_records(
        (
            _financial(symbol, date(2024, 9, 30), 10),
            _financial(symbol, date(2024, 12, 31), 99),
            _financial(symbol, date(2025, 9, 30), 20, _AS_OF - timedelta(days=2)),
            _financial(symbol, date(2025, 9, 30), 99, _AS_OF + timedelta(days=1)),
        )
    )
    repository.upsert_valuation_records(
        (
            ValuationRecord(symbol=symbol, as_of=_AS_OF - timedelta(days=2), pe=10, source="synthetic"),
            ValuationRecord(symbol=symbol, as_of=_AS_OF + timedelta(days=1), pe=99, source="synthetic"),
        )
    )
    repository.upsert_industry_records(
        (
            IndustryRecord(symbol=symbol, industry_code="A", industry_name="A", classification=_CLASSIFICATION, effective_from=date(2020, 1, 1), effective_to=date(2024, 6, 30), source="synthetic"),
            IndustryRecord(symbol=symbol, industry_code="B", industry_name="B", classification=_CLASSIFICATION, effective_from=date(2024, 7, 1), source="synthetic"),
        )
    )
    factor_input = DailySelectionService(repository, Settings())._factor_input(symbol, _AS_OF)
    assert factor_input.financial_current is not None
    assert factor_input.financial_current.roe == 20
    assert factor_input.financial_prior_year is not None
    assert factor_input.financial_prior_year.report_period == date(2024, 9, 30)
    assert factor_input.valuation is not None and factor_input.valuation.pe == 10
    assert factor_input.industry_key == f"{_CLASSIFICATION}:B"
    assert factor_input.price_series is None
