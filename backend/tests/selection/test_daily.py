"""Synthetic local-repository integration tests for daily selection safety."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config import AppPaths, Settings
from stock_selector.factors import FiveFactorRequest
from stock_selector.factors.models import FactorFamily
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    ValuationRecord,
)
from stock_selector.risk import DatedRiskState
from stock_selector.scoring import (
    BaseScoreCrossSectionResult,
    BaseScoreRequest,
    BaseScoreStockResult,
    FactorWeightContribution,
)
from stock_selector.selection import DailySelectionService, SelectionBlocker
from stock_selector.storage import LocalMarketRepository

_AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_CLASSIFICATION = "证监会行业分类标准（2012）"


def _repository(
    tmp_path, symbols: tuple[str, ...] = ("000001.SZ", "600519.SH", "601398.SH")
) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(tuple(_instrument(symbol) for symbol in symbols))
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


def _seed_factor_inputs(repository: LocalMarketRepository, symbols: tuple[str, ...] = ("000001.SZ", "600519.SH", "601398.SH")) -> None:
    for symbol in symbols:
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
        repository.upsert_industry_records((_industry(symbol),))


def _industry(symbol: str) -> IndustryRecord:
    return IndustryRecord(
        symbol=symbol,
        industry_code="C15",
        industry_name="酒、饮料和精制茶制造业",
        classification=_CLASSIFICATION,
        effective_from=date(2020, 1, 1),
        source="synthetic",
    )


def _stub_score(
    as_of: datetime, symbols_and_scores: tuple[tuple[str, float | None, float], ...]
) -> BaseScoreCrossSectionResult:
    """Create a narrow scoring-boundary fixture; factor assembly remains real."""
    stocks = tuple(
        sorted(
            (_score_result(as_of, symbol, base_score, coverage) for symbol, base_score, coverage in symbols_and_scores),
            key=lambda item: item.symbol,
        )
    )
    return BaseScoreCrossSectionResult(as_of=as_of, input_count=len(stocks), stocks=stocks)


def _score_result(
    as_of: datetime, symbol: str, base_score: float | None, coverage: float
) -> BaseScoreStockResult:
    available = base_score is not None
    weights = {
        FactorFamily.QUALITY: 0.25,
        FactorFamily.VALUE: 0.25,
        FactorFamily.GROWTH: 0.25,
        FactorFamily.MOMENTUM: 0.125,
        FactorFamily.LOW_VOLATILITY: 0.125,
    }
    contributions = tuple(
        FactorWeightContribution(
            family=family,
            enabled=True,
            configured_weight=weight,
            family_score=base_score if available else None,
            family_component_coverage=coverage if available else 0.0,
            available=available,
            renormalized_weight=weight if available else 0.0,
            weighted_contribution=base_score * weight if available else None,
        )
        for family, weight in weights.items()
    )
    return BaseScoreStockResult(
        symbol=symbol,
        as_of=as_of,
        base_score=base_score,
        data_completeness=1.0 if available else 0.0,
        confidence=coverage if available else 0.0,
        confidence_adjusted_score=base_score * coverage if available else None,
        available_family_weight=1.0 if available else 0.0,
        enabled_family_weight=1.0,
        available_families=5 if available else 0,
        enabled_families=5,
        contributions=contributions,
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


def test_ranking_uses_base_score_then_symbol_and_preserves_market_rank(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "600519.SH", "601398.SH")
    repository = _repository(tmp_path, symbols)
    _seed_factor_inputs(repository, symbols)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in symbols))
    service = DailySelectionService(repository, Settings())
    stubbed_scores = _stub_score(
        _AS_OF,
        (
            ("000001.SZ", 80.0, 0.1),
            ("600519.SH", 80.0, 0.1),
            ("601398.SH", 70.0, 1.0),
        ),
    )
    monkeypatch.setattr(service._score_engine, "compute", lambda _request: stubbed_scores)

    result = service.build(_AS_OF)

    assert [(item.symbol, item.base_score) for item in result.selection.items] == [
        ("000001.SZ", 80.0),
        ("600519.SH", 80.0),
        ("601398.SH", 70.0),
    ]
    assert [item.market_rank for item in result.selection.items] == [1, 2, 3]
    assert result.selection.items[0].confidence_adjusted_score < result.selection.items[2].confidence_adjusted_score


def test_top_n_truncates_complete_base_score_ranking_in_service(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "000002.SZ", "000003.SZ", "600519.SH", "601398.SH")
    repository = _repository(tmp_path, symbols)
    _seed_factor_inputs(repository, symbols)
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in symbols))
    settings = Settings(selection={"top_n": 3})
    service = DailySelectionService(repository, settings)
    stubbed_scores = _stub_score(
        _AS_OF,
        tuple((symbol, score, 1.0) for symbol, score in zip(symbols, (91.0, 90.0, 89.0, 88.0, 87.0), strict=True)),
    )
    monkeypatch.setattr(service._score_engine, "compute", lambda _request: stubbed_scores)

    result = service.build(_AS_OF)

    assert result.diagnostics.scoreable_members == 5
    assert result.diagnostics.requested_top_n == 3
    assert result.diagnostics.returned_items == 3
    assert [(item.symbol, item.market_rank) for item in result.selection.items] == [
        ("000001.SZ", 1),
        ("000002.SZ", 2),
        ("000003.SZ", 3),
    ]


def test_no_scoreable_candidate_is_not_ranked_and_has_no_score_blocker(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbol = "600519.SH"
    repository = _repository(tmp_path, (symbol,))
    repository.upsert_industry_records((_industry(symbol),))
    repository.upsert_financial_records(
        (
            FinancialRecord(
                symbol=symbol,
                report_period=date(2025, 12, 31),
                announcement_date=date(2026, 3, 20),
                available_at=_AS_OF - timedelta(days=1),
                source="synthetic",
            ),
        )
    )
    repository.upsert_risk_states((_risk(symbol),))
    service = DailySelectionService(repository, Settings())
    factor_input = service._factor_input(symbol, _AS_OF)
    factors = service._factor_engine.compute(FiveFactorRequest(stocks=(factor_input,)))
    base_scores = service._score_engine.compute(BaseScoreRequest(factors=factors, config=Settings().factors))

    result = service.build(_AS_OF)

    assert base_scores.stocks[0].base_score is None
    assert result.diagnostics.selection_ready is False
    assert result.diagnostics.scoreable_members == 0
    assert result.selection.items == ()
    assert SelectionBlocker.NO_SCOREABLE_INSTRUMENTS in result.diagnostics.blockers
    assert SelectionBlocker.RISK_STATE_COVERAGE_INCOMPLETE not in result.diagnostics.blockers


def test_low_completeness_quality_only_candidate_remains_rankable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbol = "600519.SH"
    repository = _repository(tmp_path, (symbol,))
    repository.upsert_industry_records((_industry(symbol),))
    repository.upsert_financial_records((_financial(symbol, date(2025, 12, 31), 10),))
    repository.upsert_risk_states((_risk(symbol),))

    result = DailySelectionService(repository, Settings()).build(_AS_OF)

    assert result.diagnostics.selection_ready is True
    assert result.diagnostics.scoreable_members == 1
    assert len(result.selection.items) == 1
    assert result.selection.items[0].data_completeness == pytest.approx(0.3)
    assert result.selection.items[0].confidence < 1


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
