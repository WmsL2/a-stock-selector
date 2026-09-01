"""Task24 local PIT slow-input assembly regressions."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.config import AppPaths, Settings
from stock_selector.factors import FactorFamily, PriceSeriesInput, StockFactorInput
from stock_selector.models import (
    AdjustmentType,
    Board,
    DailyBar,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    ValuationRecord,
)
from stock_selector.realtime import (
    RealtimeDataError,
    RealtimeSelectionApplicationService,
    RealtimeSlowInputDiagnostics,
    RealtimeSlowInputResult,
    RealtimeSlowInputService,
)
from stock_selector.risk import DatedRiskState
from stock_selector.selection import DailySelectionService
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


def _instrument(symbol: str, *, board: Board | None = None) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=board or (Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN),
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


def _financial(
    symbol: str, period: date, value: float, available_at: datetime | None = None
) -> FinancialRecord:
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


def _industry(
    symbol: str, *, code: str = "C15", classification: str = _CLASSIFICATION
) -> IndustryRecord:
    return IndustryRecord(
        symbol=symbol,
        industry_code=code,
        industry_name=f"industry-{code}",
        classification=classification,
        effective_from=date(2020, 1, 1),
        source="synthetic",
    )


def _seed_factor_inputs(
    repository: LocalMarketRepository,
    symbols: tuple[str, ...] = ("000001.SZ", "600519.SH", "601398.SH"),
) -> None:
    for symbol in symbols:
        repository.upsert_financial_records(
            (
                _financial(symbol, date(2024, 12, 31), 10),
                _financial(symbol, date(2025, 12, 31), 20),
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


def _complete(repository: LocalMarketRepository, symbols: tuple[str, ...]) -> None:
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in symbols))


def test_complete_pit_assembly_is_deterministic_read_only_and_qvg_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    _complete(repository, ("000001.SZ", "600519.SH", "601398.SH"))
    before = repository.get_stats()
    service = RealtimeSlowInputService(repository, Settings())

    first = service.build(_AS_OF)
    second = service.build(_AS_OF)

    assert first == second
    assert repository.get_stats() == before
    assert first.diagnostics.risk_ready is True
    assert first.diagnostics.factor_input_members == 3
    assert first.diagnostics.base_score_available_members == 3
    assert first.diagnostics.price_factors_operational is False
    assert all(item.price_series is None for item in first.factor_inputs)
    assert first.factors is not None
    assert tuple(item.symbol for item in first.factors.stocks) == tuple(
        item.symbol for item in first.factor_inputs
    )
    assert first.factor_config == Settings().factors
    assert all(item.base_score is not None for item in first.base_scores.stocks)
    assert all(item.available_families == 3 for item in first.base_scores.stocks)


def test_risk_incomplete_and_unknown_short_circuit_without_factor_loading(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    repository.upsert_risk_states(
        (_risk("000001.SZ"), _risk("600519.SH", is_st=None))
    )

    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)

    assert result.diagnostics.risk_ready is False
    assert result.diagnostics.risk_complete_members == 1
    assert result.factor_inputs == ()
    assert result.factors is None
    assert result.base_scores.input_count == 0
    assert result.base_scores.stocks == ()


def test_exact_date_risk_does_not_carry_forward(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    _seed_factor_inputs(repository, ("600519.SH",))
    previous = _risk("600519.SH").model_copy(
        update={"as_of": _AS_OF.date() - timedelta(days=1)}
    )
    repository.upsert_risk_states((previous,))

    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)

    assert result.diagnostics.risk_records == 0
    assert result.diagnostics.risk_ready is False
    assert result.factor_inputs == ()
    assert result.base_scores.stocks == ()


def test_complete_but_zero_eligible_and_eligible_without_local_inputs_are_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    excluded = _repository(tmp_path / "excluded", ("600519.SH",))
    _complete(excluded, ("600519.SH",))
    excluded.upsert_risk_states((_risk("600519.SH", is_st=True),))
    no_eligible = RealtimeSlowInputService(excluded, Settings()).build(_AS_OF)
    assert no_eligible.diagnostics.risk_ready is True
    assert no_eligible.diagnostics.risk_eligible_members == 0
    assert no_eligible.factor_inputs == ()
    assert no_eligible.factors is None

    missing = _repository(tmp_path / "missing", ("600519.SH",))
    _complete(missing, ("600519.SH",))
    no_inputs = RealtimeSlowInputService(missing, Settings()).build(_AS_OF)
    assert no_inputs.diagnostics.risk_ready is True
    assert no_inputs.diagnostics.risk_eligible_members == 1
    assert no_inputs.factor_inputs == ()
    assert no_inputs.factors is None
    assert no_inputs.base_scores.stocks == ()


def test_factor_scope_excludes_risk_ineligible_local_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path, symbols)
    _seed_factor_inputs(repository, symbols)
    repository.upsert_risk_states((_risk("000001.SZ"), _risk("600519.SH", is_st=True)))

    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)

    assert tuple(item.symbol for item in result.factor_inputs) == ("000001.SZ",)
    assert tuple(item.symbol for item in result.base_scores.stocks) == ("000001.SZ",)


def test_financial_revision_prior_year_valuation_and_industry_are_pit_safe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbol = "600519.SH"
    repository = _repository(tmp_path, (symbol,))
    repository.upsert_financial_records(
        (
            _financial(symbol, date(2024, 9, 30), 10),
            _financial(symbol, date(2025, 9, 30), 20, _AS_OF - timedelta(days=2)),
            _financial(symbol, date(2025, 9, 30), 99, _AS_OF + timedelta(days=1)),
        )
    )
    repository.upsert_valuation_records(
        (
            ValuationRecord(symbol=symbol, as_of=_AS_OF - timedelta(days=1), pe=10, source="test"),
            ValuationRecord(symbol=symbol, as_of=_AS_OF + timedelta(days=1), pe=99, source="test"),
        )
    )
    repository.upsert_industry_records(
        (
            IndustryRecord(symbol=symbol, industry_code="OLD", industry_name="old", classification=_CLASSIFICATION, effective_from=date(2020, 1, 1), effective_to=_AS_OF.date(), source="test"),
            IndustryRecord(symbol=symbol, industry_code="NEW", industry_name="new", classification=_CLASSIFICATION, effective_from=_AS_OF.date() + timedelta(days=1), source="test"),
            _industry(symbol, code="ALT", classification="other"),
        )
    )
    _complete(repository, (symbol,))

    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)
    repository.upsert_risk_states(
        (_risk(symbol).model_copy(update={"as_of": (_AS_OF + timedelta(days=2)).date()}),)
    )
    future = RealtimeSlowInputService(repository, Settings()).build(_AS_OF + timedelta(days=2))

    item = result.factor_inputs[0]
    assert item.financial_current is not None and item.financial_current.roe == 20
    assert item.financial_prior_year is not None
    assert item.financial_prior_year.report_period == date(2024, 9, 30)
    assert item.valuation is not None and item.valuation.pe == 10
    assert item.industry_key == f"{_CLASSIFICATION}:OLD"
    assert future.factor_inputs[0].financial_current is not None
    assert future.factor_inputs[0].financial_current.roe == 99
    assert future.factor_inputs[0].valuation is not None
    assert future.factor_inputs[0].valuation.pe == 99
    assert future.factor_inputs[0].industry_key == f"{_CLASSIFICATION}:NEW"


def test_missing_configured_industry_is_not_replaced_by_another_classification(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    repository.upsert_financial_records((_financial("600519.SH", date(2025, 12, 31), 10),))
    repository.upsert_industry_records((_industry("600519.SH", classification="other"),))
    _complete(repository, ("600519.SH",))

    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)

    assert result.factor_inputs[0].industry_key is None
    assert result.diagnostics.industry_available_members == 0


def test_raw_daily_bars_are_ignored_for_price_factors_and_base_score(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    _seed_factor_inputs(repository, ("600519.SH",))
    _complete(repository, ("600519.SH",))
    service = RealtimeSlowInputService(repository, Settings())
    before = service.build(_AS_OF)
    repository.upsert_daily_bars(
        (
            DailyBar(symbol="600519.SH", trade_date=_AS_OF.date() - timedelta(days=1), open=10, high=11, low=9, close=10, volume=1, amount=10, adjustment=AdjustmentType.RAW, source="test"),
        )
    )

    after = service.build(_AS_OF)

    assert after.factor_inputs[0].price_series is None
    assert after.base_scores == before.base_scores
    assert after.base_scores.stocks[0].contributions[3].family_score is None
    assert after.base_scores.stocks[0].contributions[4].family_score is None


def test_settings_factor_and_universe_configuration_propagate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "688001.SH")
    repository = _repository(tmp_path, symbols)
    repository.save_instruments((_instrument("000001.SZ"), _instrument("688001.SH", board=Board.STAR)))
    _seed_factor_inputs(repository, symbols)
    _complete(repository, symbols)
    settings = Settings(
        universe={"include_star_market": False},
        factors={
            "quality": {"weight": 0.5},
            "value": {"weight": 0.5},
            "growth": {"enabled": False, "weight": 0.0},
            "momentum": {"enabled": False, "weight": 0.0},
            "low_volatility": {"enabled": False, "weight": 0.0},
        },
    )

    result = RealtimeSlowInputService(repository, settings).build(_AS_OF)

    assert result.structural.members == ("000001.SZ",)
    assert tuple(item.symbol for item in result.base_scores.stocks) == ("000001.SZ",)
    assert tuple(item.configured_weight for item in result.base_scores.stocks[0].contributions) == (
        0.5,
        0.5,
        0.0,
        0.0,
        0.0,
    )


def test_daily_selection_parity_and_task23_compatibility(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed_factor_inputs(repository)
    _complete(repository, ("000001.SZ", "600519.SH", "601398.SH"))
    settings = Settings(selection={"top_n": 10})
    slow = RealtimeSlowInputService(repository, settings).build(_AS_OF)
    daily = DailySelectionService(repository, settings).build(_AS_OF)
    slow_by_symbol = {item.symbol: item for item in slow.base_scores.stocks}

    assert slow.diagnostics.structural_members == daily.diagnostics.structural_members
    assert slow.diagnostics.risk_complete_members == daily.diagnostics.risk_complete_members
    assert slow.diagnostics.risk_eligible_members == daily.diagnostics.risk_eligible_members
    for item in daily.selection.items:
        score = slow_by_symbol[item.symbol]
        assert (score.base_score, score.data_completeness, score.confidence) == (
            item.base_score,
            item.data_completeness,
            item.confidence,
        )
        assert slow.factors is not None
        factor_item = next(factor for factor in slow.factors.stocks if factor.symbol == item.symbol)
        for contribution, family, evidence in zip(
            score.contributions,
            FactorFamily,
            (
                factor_item.quality,
                factor_item.value,
                factor_item.growth,
                factor_item.momentum,
                factor_item.low_volatility,
            ),
            strict=True,
        ):
            assert contribution.family is family
            assert contribution.family_score == evidence.score
            assert contribution.available is (contribution.enabled and evidence.score is not None)
            assert contribution.configured_weight == getattr(settings.factors, family.value).weight
    pipeline = RealtimeSelectionApplicationService().run(
        slow.base_scores, slow.risk, None, _AS_OF + timedelta(minutes=1)
    )
    assert pipeline.candidates.as_of == slow.as_of


def test_naive_time_and_multiple_selected_industries_propagate_errors(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    _seed_factor_inputs(repository, ("600519.SH",))
    _complete(repository, ("600519.SH",))
    service = RealtimeSlowInputService(repository, Settings())
    with pytest.raises(ValueError, match="timezone-aware"):
        service.build(_AS_OF.replace(tzinfo=None))

    records = (_industry("600519.SH"), _industry("600519.SH", code="SECOND"))
    monkeypatch.setattr(
        repository, "load_industry_records", lambda _symbol, *, as_of: records
    )
    with pytest.raises(RealtimeDataError, match="multiple active records"):
        service.build(_AS_OF)


def test_result_models_reject_corrupted_cross_section_contracts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    _seed_factor_inputs(repository, ("600519.SH",))
    _complete(repository, ("600519.SH",))
    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)
    valid = result.model_dump()
    for update in (
        {"risk_ready": False},
        {"price_factors_operational": True},
    ):
        with pytest.raises(ValidationError):
            RealtimeSlowInputDiagnostics(
                **result.diagnostics.model_copy(update=update).model_dump()
            )
    non_eligible_input = StockFactorInput.model_construct(
        symbol="000001.SZ",
        as_of=_AS_OF,
        industry_key=None,
        financial_current=None,
        financial_prior_year=None,
        valuation=None,
        price_series=None,
    )
    wrong_score_symbol = result.base_scores.stocks[0].model_copy(
        update={"symbol": "000001.SZ"}
    )
    for update in (
        {"as_of": _AS_OF + timedelta(days=1)},
        {"diagnostics": result.diagnostics.model_copy(update={"as_of": _AS_OF + timedelta(days=1)})},
        {"structural": result.structural.model_copy(update={"as_of": _AS_OF.date() - timedelta(days=1)})},
        {"risk": result.risk.model_copy(update={"as_of": _AS_OF.date() - timedelta(days=1)})},
        {"diagnostics": result.diagnostics.model_copy(update={"risk_records": 0})},
        {"diagnostics": result.diagnostics.model_copy(update={"risk_coverage_ratio": 0.0})},
        {"factor_inputs": (result.factor_inputs[0], result.factor_inputs[0])},
        {"factor_inputs": (non_eligible_input,)},
        {"factor_inputs": (result.factor_inputs[0].model_copy(update={"as_of": _AS_OF + timedelta(days=1)}),)},
        {"factor_inputs": (result.factor_inputs[0].model_copy(update={"price_series": PriceSeriesInput(symbol="600519.SH", as_of=_AS_OF, points=(), corporate_action_adjusted=True)}),)},
        {"factors": None},
        {"factors": result.factors.model_copy(update={"as_of": _AS_OF + timedelta(days=1)})},
        {"base_scores": result.base_scores.model_copy(update={"input_count": 0})},
        {"base_scores": result.base_scores.model_copy(update={"as_of": _AS_OF + timedelta(days=1)})},
        {"base_scores": result.base_scores.model_copy(update={"stocks": (wrong_score_symbol,)})},
        {"diagnostics": result.diagnostics.model_copy(update={"base_score_available_members": 0})},
    ):
        with pytest.raises(ValidationError):
            RealtimeSlowInputResult(**(valid | update))


def test_empty_factor_inputs_reject_retained_factor_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path, ("600519.SH",))
    _complete(repository, ("600519.SH",))
    empty = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)
    populated_repository = _repository(tmp_path / "populated", ("600519.SH",))
    _seed_factor_inputs(populated_repository, ("600519.SH",))
    _complete(populated_repository, ("600519.SH",))
    populated = RealtimeSlowInputService(populated_repository, Settings()).build(_AS_OF)

    with pytest.raises(ValidationError):
        RealtimeSlowInputResult(**(empty.model_dump() | {"factors": populated.factors}))


def test_unsorted_factor_inputs_are_rejected_with_normal_result_construction(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path, symbols)
    _seed_factor_inputs(repository, symbols)
    _complete(repository, symbols)
    result = RealtimeSlowInputService(repository, Settings()).build(_AS_OF)

    with pytest.raises(ValidationError, match="unique and sorted"):
        RealtimeSlowInputResult(
            **(result.model_dump() | {"factor_inputs": tuple(reversed(result.factor_inputs))})
        )


def test_cross_run_base_score_and_config_linkage_are_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path, symbols)
    _seed_factor_inputs(repository, symbols)
    _complete(repository, symbols)
    settings_a = Settings()
    settings_b = Settings(
        factors={
            "quality": {"weight": 0.4},
            "value": {"weight": 0.3},
            "growth": {"weight": 0.2},
            "momentum": {"weight": 0.05},
            "low_volatility": {"weight": 0.05},
        }
    )
    result_a = RealtimeSlowInputService(repository, settings_a).build(_AS_OF)
    result_b = RealtimeSlowInputService(repository, settings_b).build(_AS_OF)

    assert result_a.base_scores != result_b.base_scores
    for update in (
        {"base_scores": result_b.base_scores},
        {"factor_config": result_b.factor_config},
    ):
        with pytest.raises(ValidationError):
            RealtimeSlowInputResult(**(result_a.model_dump() | update))

    repository.upsert_financial_records(
        (
            _financial(
                "600519.SH",
                date(2025, 12, 31),
                80,
                _AS_OF - timedelta(hours=1),
            ),
        )
    )
    evidence_run = RealtimeSlowInputService(repository, settings_a).build(_AS_OF)
    assert evidence_run.factors != result_a.factors
    with pytest.raises(ValidationError):
        RealtimeSlowInputResult(
            **(result_a.model_dump() | {"factors": evidence_run.factors})
        )
