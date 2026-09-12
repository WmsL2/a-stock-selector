"""Pure Task44 current official selection coverage contracts."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector import cli as cli_module
from stock_selector.cli import main
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    AdjustedDailyReturn,
    AdjustmentType,
    FinancialRecord,
    IndustryRecord,
    ValuationRecord,
)
from stock_selector.selection import (
    CurrentSelectionCoverageAuditor,
    CurrentSelectionCoverageReport,
    CurrentSelectionCoverageRequest,
)
from stock_selector.storage import LocalMarketRepository

NOW = datetime(2026, 9, 11, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
S = ("000001.SZ", "000002.SZ", "600519.SH")


def request(**changes: object) -> CurrentSelectionCoverageRequest:
    values: dict[str, object] = {
        "as_of": NOW, "structural_symbols": S, "risk_record_symbols": S,
        "risk_complete_symbols": S, "risk_eligible_symbols": ("000001.SZ", "000002.SZ"),
        "financial_symbols": ("000001.SZ",), "valuation_symbols": ("000002.SZ",),
        "industry_symbols": ("000001.SZ", "000002.SZ"),
        "factor_input_symbols": ("000001.SZ", "000002.SZ"), "adjusted_return_symbols": (),
    }
    values.update(changes)
    return CurrentSelectionCoverageRequest(**values)


def test_complete_membership_and_adjusted_return_is_nonblocking() -> None:
    report = CurrentSelectionCoverageAuditor().audit(
        request(adjusted_return_symbols=("000001.SZ", "000002.SZ"))
    )
    assert report.input_readiness.upstream_inputs_ready
    assert report.eligible_adjusted_return_symbols == ("000001.SZ", "000002.SZ")
    assert report.minimum_prepare_runs_at_max_limit == 0


@pytest.mark.parametrize(
    (
        "financial",
        "valuation",
        "industry",
        "factor",
        "missing_industry",
        "missing_both",
    ),
    (
        (("000001.SZ",), (), ("000002.SZ",), (), ("000001.SZ",), ("000002.SZ",)),
        (
            ("000001.SZ",),
            (),
            ("000001.SZ", "000002.SZ"),
            ("000001.SZ",),
            (),
            ("000002.SZ",),
        ),
        ((), (), (), (), ("000001.SZ", "000002.SZ"), ("000001.SZ", "000002.SZ")),
    ),
)
def test_missing_causes_are_exact_and_may_overlap(
    financial, valuation, industry, factor, missing_industry, missing_both
) -> None:
    report = CurrentSelectionCoverageAuditor().audit(
        request(
            financial_symbols=financial,
            valuation_symbols=valuation,
            industry_symbols=industry,
            factor_input_symbols=factor,
        )
    )
    assert report.eligible_missing_industry_symbols == missing_industry
    assert report.eligible_missing_financial_and_valuation_symbols == missing_both
    assert set(missing_industry) | set(missing_both) == set(
        report.input_readiness.eligible_factor_input_missing_symbols
    )


@pytest.mark.parametrize(
    ("missing", "runs"), ((0, 0), (1, 1), (100, 1), (101, 2), (200, 2), (201, 3))
)
def test_prepare_run_lower_bound(missing: int, runs: int) -> None:
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, max(1, missing) + 1))
    report = CurrentSelectionCoverageAuditor().audit(
        request(
            structural_symbols=symbols,
            risk_record_symbols=symbols,
            risk_complete_symbols=symbols,
            risk_eligible_symbols=symbols if missing else (),
            financial_symbols=(),
            valuation_symbols=(),
            industry_symbols=(),
            factor_input_symbols=(),
        )
    )
    assert report.minimum_prepare_runs_at_max_limit == runs


def test_invalid_factor_rule_and_risk_subset_rejected() -> None:
    with pytest.raises(ValidationError):
        request(factor_input_symbols=("000001.SZ",))
    with pytest.raises(ValidationError):
        request(risk_eligible_symbols=("300001.SZ",))


def test_risk_ineligible_structural_gap_and_adjusted_returns_do_not_change_readiness() -> (
    None
):
    base = request(
        factor_input_symbols=("000001.SZ",),
        risk_eligible_symbols=("000001.SZ",),
        industry_symbols=("000001.SZ",),
        valuation_symbols=(),
    )
    auditor = CurrentSelectionCoverageAuditor()
    assert auditor.audit(base).input_readiness.upstream_inputs_ready
    assert (
        auditor.audit(
            base.model_copy(update={"adjusted_return_symbols": ("000001.SZ",)})
        ).input_readiness.blockers
        == ()
    )


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("as_of", NOW.replace(hour=10)),
        ("structural_symbols", ("000001.SZ",)),
        ("risk_record_symbols", ()),
        ("risk_complete_symbols", ()),
        ("risk_eligible_symbols", ()),
        ("factor_input_symbols", ()),
        ("structural_financial_symbols", ()),
        ("structural_valuation_symbols", ()),
        ("structural_industry_symbols", ()),
        ("structural_adjusted_return_symbols", ("000001.SZ",)),
        ("eligible_financial_symbols", ()),
        ("eligible_valuation_symbols", ()),
        ("eligible_industry_symbols", ()),
        ("eligible_adjusted_return_symbols", ("000001.SZ",)),
        ("eligible_adjusted_return_missing_symbols", ()),
        ("eligible_missing_industry_symbols", ()),
        ("eligible_missing_financial_and_valuation_symbols", ()),
        ("prepare_inputs_max_limit", 99),
        ("minimum_prepare_runs_at_max_limit", 1),
    ),
)
def test_report_rejects_tampered_retained_or_derived_semantics(
    change: str, value: object
) -> None:
    report = CurrentSelectionCoverageAuditor().audit(request())
    values = report.model_dump()
    original = values[change]
    values[change] = value
    if values[change] == original:
        values[change] = ("600519.SH",)
    with pytest.raises(ValidationError):
        CurrentSelectionCoverageReport.model_validate(values)


def test_nonstructural_component_membership_and_financial_or_valuation_coverage() -> None:
    report = CurrentSelectionCoverageAuditor().audit(
        request(
            financial_symbols=("000001.SZ", "300001.SZ"),
            valuation_symbols=("000002.SZ", "300001.SZ"),
            industry_symbols=("000001.SZ", "000002.SZ", "300001.SZ"),
            factor_input_symbols=("000001.SZ", "000002.SZ", "300001.SZ"),
            adjusted_return_symbols=("000001.SZ",),
        )
    )
    assert report.structural_financial_symbols == ("000001.SZ",)
    assert report.structural_valuation_symbols == ("000002.SZ",)
    assert report.eligible_adjusted_return_missing_symbols == ("000002.SZ",)
    assert report.input_readiness.upstream_inputs_ready


def test_temporary_repository_component_memberships_preserve_factor_input_formula(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    at = NOW - timedelta(days=1)
    financial = ("000001.SZ", "000003.SZ")
    valuation = ("000002.SZ", "000004.SZ")
    industry = ("000001.SZ", "000002.SZ", "000005.SZ")
    for symbol in financial:
        repository.upsert_financial_records((FinancialRecord(symbol=symbol, report_period=date(2025, 12, 31), announcement_date=at.date(), available_at=at, roe=1, roa=1, gross_margin=1, net_margin=1, revenue=1, net_profit=1, deducted_net_profit=1, source="test"),))
    for symbol in valuation:
        repository.upsert_valuation_records((ValuationRecord(symbol=symbol, as_of=at, pe=1, pb=1, pcf=1, source="test"),))
    for symbol in industry:
        repository.upsert_industry_records((IndustryRecord(symbol=symbol, industry_code="C15", industry_name="test", classification="test", effective_from=date(2020, 1, 1), source="test"),))
    repository.upsert_adjusted_daily_returns((AdjustedDailyReturn(symbol="000006.SZ", trade_date=at.date(), previous_trade_date=(at - timedelta(days=1)).date(), return_fraction=0.01, adjustment=AdjustmentType.HFQ, observed_at=at, source="test"),))
    assert repository.load_financial_symbols() == financial
    assert repository.load_valuation_symbols() == valuation
    assert repository.load_industry_symbols() == industry
    assert repository.load_adjusted_return_symbols() == ("000006.SZ",)
    assert repository.load_factor_input_symbols() == ("000001.SZ", "000002.SZ")


def test_coverage_status_is_one_read_only_not_ready_audit(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    calls: dict[str, object] = {key: 0 for key in ("now", "universe_construct", "universe", "risk", "evaluate", "financial", "valuation", "industry", "factor", "adjusted", "audit")}
    structural = SimpleNamespace(members=("000001.SZ", "000002.SZ"))
    states = tuple(SimpleNamespace(symbol=symbol) for symbol in structural.members)
    original_paths = AppPaths.from_project_root
    class Repository:
        def __init__(self, _paths): pass
        def initialize(self): pass
        def load_risk_states(self, as_of, symbols): calls["risk"] += 1; assert (as_of, symbols) == (NOW.date(), structural.members); return states
        def load_financial_symbols(self): calls["financial"] += 1; return ("000001.SZ",)
        def load_valuation_symbols(self): calls["valuation"] += 1; return ()
        def load_industry_symbols(self): calls["industry"] += 1; return structural.members
        def load_factor_input_symbols(self): calls["factor"] += 1; return ("000001.SZ",)
        def load_adjusted_return_symbols(self): calls["adjusted"] += 1; return ("000001.SZ",)
        def __getattr__(self, name):
            # Any accidental repository write-method lookup must fail immediately.
            if name.startswith(("save_", "upsert_")): raise AssertionError(name)
            raise AttributeError(name)
    class Universe:
        def __init__(self, *_): calls["universe_construct"] += 1
        def build_current(self, as_of): calls["universe"] += 1; assert as_of == NOW.date(); return structural
    class Evaluator:
        def evaluate(self, received_structural, received_states, config):
            calls["evaluate"] += 1; assert (received_structural, received_states, config) == (structural, states, settings.universe)
            return SimpleNamespace(eligible_members=structural.members, decisions=tuple(SimpleNamespace(symbol=symbol, risk_complete=True) for symbol in structural.members))
    real_auditor = CurrentSelectionCoverageAuditor
    class Auditor(real_auditor):
        def audit(self, received): calls["audit"] += 1; calls["request"] = received; return super().audit(received)
    settings = Settings()
    def now(timezone):
        calls["now"] += 1; calls["timezone"] = timezone; return NOW
    def forbidden(*_args, **_kwargs): raise AssertionError("forbidden dependency invoked")
    monkeypatch.setattr(cli_module, "load_settings", lambda _path: settings)
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr(cli_module, "datetime", SimpleNamespace(now=now))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    monkeypatch.setattr("stock_selector.universe.CurrentUniverseService", Universe)
    monkeypatch.setattr("stock_selector.risk.evaluator.RiskEligibilityEvaluator", Evaluator)
    monkeypatch.setattr("stock_selector.selection.CurrentSelectionCoverageAuditor", Auditor)
    for target in ("stock_selector.providers.AKShareProvider", "stock_selector.collection.CurrentRiskStateCollector", "stock_selector.collection.FinancialCollector", "stock_selector.collection.IndustryCollector", "stock_selector.collection.ValuationCollector", "stock_selector.collection.AdjustedDailyReturnCollector", "stock_selector.collection.StructuralSlowInputCollector", "stock_selector.collection.StructuralSlowInputSweepCollector", "stock_selector.factors.FiveFactorEngine", "stock_selector.scoring.BaseScoreEngine", "stock_selector.explanation.ExplanationEngine", "stock_selector.selection.DailySelectionService"):
        monkeypatch.setattr(target, forbidden)
    monkeypatch.setattr(cli_module, "_run_selection_prepare_inputs_command", lambda *_: (_ for _ in ()).throw(AssertionError("prepare")))
    assert main(["selection", "coverage-status"]) == 0
    assert all(calls[key] == 1 for key in ("now", "universe_construct", "universe", "risk", "evaluate", "financial", "valuation", "industry", "factor", "adjusted", "audit"))
    assert calls["timezone"] == ZoneInfo(settings.app.timezone)
    received = calls["request"]
    assert (received.as_of, received.structural_symbols, received.risk_record_symbols, received.risk_complete_symbols, received.risk_eligible_symbols, received.financial_symbols, received.valuation_symbols, received.industry_symbols, received.factor_input_symbols, received.adjusted_return_symbols) == (NOW, structural.members, structural.members, structural.members, structural.members, ("000001.SZ",), (), structural.members, ("000001.SZ",), ("000001.SZ",))
    output = capsys.readouterr().out
    assert "Blockers: eligible_factor_input_coverage_incomplete" in output
    assert "Official upstream inputs ready: NO" in output
    assert "Eligible adjusted-return evidence: 1 / 2" in output
    assert "Eligible adjusted-return evidence: 1 /2" not in output
    for label in ("As of:", "Structural members:", "Structural stored financial:", "Structural stored valuation:", "Structural stored industry:", "Structural factor-input covered:", "Structural factor-input missing:", "Exact-date risk records:", "Risk-complete members:", "Risk coverage:", "Risk-eligible members:", "Eligible stored financial:", "Eligible stored valuation:", "Eligible stored industry:", "Eligible factor-input covered:", "Eligible factor-input missing:", "Eligible missing industry:", "Eligible missing financial AND valuation:", "Eligible adjusted-return evidence:", "Eligible adjusted-return evidence missing:", "Minimum prepare-inputs runs at --limit 100:", "Official upstream inputs ready:", "Blockers:"):
        assert label in output
    assert "Adjusted-return evidence is optional and does not block official upstream readiness." in output
    assert "Minimum prepare-inputs runs assume all targeted refreshes succeed." in output
    assert "Coverage audit is read-only and does not run official selection." in output


def test_coverage_status_maps_local_error_to_one(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    original_paths = AppPaths.from_project_root
    class Repository:
        def __init__(self, _paths): pass
        def initialize(self): raise ValueError("local failure")
    monkeypatch.setattr(cli_module.AppPaths, "from_project_root", lambda: original_paths(tmp_path))
    monkeypatch.setattr("stock_selector.storage.LocalMarketRepository", Repository)
    assert main(["selection", "coverage-status"]) == 1
    assert "Selection coverage audit error:" in capsys.readouterr().err
