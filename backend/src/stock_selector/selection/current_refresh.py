"""Finite refresh of the current official selection's upstream inputs only."""

from datetime import datetime

from pydantic import field_validator, model_validator

from stock_selector.collection import (
    CurrentRiskCollectionRequest,
    CurrentRiskCollectionResult,
    CurrentRiskStateCollector,
    StructuralMissingRefreshPlan,
    StructuralMissingRefreshPlanner,
    StructuralMissingRefreshPlanRequest,
    StructuralSlowInputSweepCollector,
    StructuralSlowInputSweepReport,
    StructuralSlowInputSweepRequest,
)
from stock_selector.config import Settings
from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.risk.evaluator import RiskEligibilityEvaluator
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe.models import UniverseSnapshot

from .current_coverage import (
    CurrentSelectionCoverageAuditor,
    CurrentSelectionCoverageReport,
    CurrentSelectionCoverageRequest,
)


class CurrentSelectionRefreshStep(DomainModel):
    """One outer, at-most-100-member Task36 invocation."""

    plan: StructuralMissingRefreshPlan
    sweep_report: StructuralSlowInputSweepReport
    coverage_after: CurrentSelectionCoverageReport

    @model_validator(mode="after")
    def exact_step(self) -> "CurrentSelectionRefreshStep":
        if self.sweep_report.requested_symbols != self.plan.selected_symbols:
            raise ValueError("sweep requested symbols must match plan selection")
        if self.sweep_report.as_of != self.plan.as_of or self.sweep_report.has_more_structural_members:
            raise ValueError("sweep must match plan and own no outer continuation")
        if self.coverage_after.as_of != self.plan.as_of or self.coverage_after.structural_symbols != self.plan.structural_symbols:
            raise ValueError("coverage after must match plan snapshot")
        return self


class CurrentSelectionRefreshReport(DomainModel):
    """Validated audit trail for a single finite refresh-current invocation."""

    as_of: datetime
    structural_symbols: tuple[str, ...]
    risk_collection_result: CurrentRiskCollectionResult
    initial_coverage: CurrentSelectionCoverageReport
    steps: tuple[CurrentSelectionRefreshStep, ...]
    final_coverage: CurrentSelectionCoverageReport
    attempted_symbols: tuple[str, ...]
    had_collection_failures: bool

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def exact_report(self) -> "CurrentSelectionRefreshReport":
        initial = self.initial_coverage
        if self.risk_collection_result.as_of != self.as_of.date() or self.risk_collection_result.requested_symbols != self.structural_symbols:
            raise ValueError("risk collection must exactly match refresh snapshot")
        fixed = (initial.as_of, initial.structural_symbols, initial.risk_record_symbols,
                 initial.risk_complete_symbols, initial.risk_eligible_symbols)
        if fixed[:2] != (self.as_of, self.structural_symbols):
            raise ValueError("initial coverage must match refresh snapshot")
        attempted = tuple(symbol for step in self.steps for symbol in step.plan.selected_symbols)
        if attempted != self.attempted_symbols or len(attempted) != len(set(attempted)):
            raise ValueError("attempted symbols must be ordered and unique")
        if not set(attempted) <= set(initial.input_readiness.eligible_factor_input_missing_symbols):
            raise ValueError("attempts must be initial eligible factor-input missing members")
        previous = initial
        previous_last: str | None = None
        for index, step in enumerate(self.steps):
            coverage = step.coverage_after
            if (coverage.as_of, coverage.structural_symbols, coverage.risk_record_symbols,
                coverage.risk_complete_symbols, coverage.risk_eligible_symbols) != fixed:
                raise ValueError("all coverage audits must retain the fixed risk snapshot")
            if step.plan.missing_structural_symbols != previous.input_readiness.eligible_factor_input_missing_symbols:
                raise ValueError("step plan must use preceding authoritative missing members")
            if step.plan.limit != 100 or not step.plan.selected_symbols:
                raise ValueError("each outer step must select one to 100 members at limit 100")
            if step.plan.selected_count != len(step.plan.selected_symbols):
                raise ValueError("plan selected count must match selected symbols")
            if (index == 0 and step.plan.start_after is not None) or (
                index and step.plan.start_after != previous_last
            ):
                raise ValueError("outer refresh cursor must continue from the prior selection")
            if previous_last is not None and step.plan.selected_symbols[0] <= previous_last:
                raise ValueError("outer refresh cursor must move strictly forward")
            previous_last = step.plan.selected_last_symbol
            previous = coverage
        if self.final_coverage != (self.steps[-1].coverage_after if self.steps else initial):
            raise ValueError("final coverage must be the final step or initial coverage")
        expected_failures = any(_sweep_failed(step.sweep_report) for step in self.steps)
        if self.had_collection_failures != expected_failures:
            raise ValueError("collection failure flag must exactly reflect nested failures")
        return self


class CurrentSelectionRefreshService:
    """Reusable orchestration with dependencies supplied by the CLI adapter."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings,
                 risk_collector: CurrentRiskStateCollector,
                 slow_input_sweep_collector: StructuralSlowInputSweepCollector) -> None:
        self._repository = repository
        self._settings = settings
        self._risk_collector = risk_collector
        self._slow_input_sweep_collector = slow_input_sweep_collector

    def refresh(self, current_at: datetime, structural: UniverseSnapshot) -> CurrentSelectionRefreshReport:
        current_at = ensure_aware_datetime(current_at, "current_at")
        if structural.as_of != current_at.date():
            raise ValueError("structural snapshot must match current_at date")
        risk_result = self._risk_collector.collect(CurrentRiskCollectionRequest(
            symbols=structural.members, as_of=current_at.date()))
        risk_states = self._repository.load_risk_states(current_at.date(), structural.members)
        risk = RiskEligibilityEvaluator().evaluate(structural, risk_states, self._settings.universe)
        risk_records = tuple(state.symbol for state in risk_states)
        complete = tuple(item.symbol for item in risk.decisions if item.risk_complete)
        initial = self._audit(current_at, structural.members, risk_records, complete, risk.eligible_members)
        if initial.input_readiness.risk_incomplete_members:
            raise ValueError("current-risk refresh did not produce complete risk coverage")
        steps: list[CurrentSelectionRefreshStep] = []
        coverage = initial
        cursor: str | None = None
        while (not coverage.input_readiness.upstream_inputs_ready
               and coverage.input_readiness.risk_eligible_members
               and coverage.input_readiness.eligible_factor_input_missing_symbols):
            plan = StructuralMissingRefreshPlanner().plan(StructuralMissingRefreshPlanRequest(
                as_of=current_at, structural_symbols=structural.members,
                missing_structural_symbols=coverage.input_readiness.eligible_factor_input_missing_symbols,
                limit=100, start_after=cursor))
            if not plan.selected_symbols:
                break
            sweep = self._slow_input_sweep_collector.collect(StructuralSlowInputSweepRequest(
                symbols=plan.selected_symbols, as_of=current_at, has_more_structural_members=False))
            coverage_after = self._audit(current_at, structural.members, risk_records, complete, risk.eligible_members)
            steps.append(CurrentSelectionRefreshStep(plan=plan, sweep_report=sweep, coverage_after=coverage_after))
            coverage = coverage_after
            cursor = plan.selected_symbols[-1]
        return CurrentSelectionRefreshReport(
            as_of=current_at, structural_symbols=structural.members,
            risk_collection_result=risk_result, initial_coverage=initial,
            steps=tuple(steps), final_coverage=coverage,
            attempted_symbols=tuple(symbol for step in steps for symbol in step.plan.selected_symbols),
            had_collection_failures=any(_sweep_failed(step.sweep_report) for step in steps),
        )

    def _audit(self, current_at: datetime, structural_symbols: tuple[str, ...],
               risk_records: tuple[str, ...], complete: tuple[str, ...], eligible: tuple[str, ...]) -> CurrentSelectionCoverageReport:
        return CurrentSelectionCoverageAuditor().audit(CurrentSelectionCoverageRequest(
            as_of=current_at, structural_symbols=structural_symbols,
            risk_record_symbols=risk_records, risk_complete_symbols=complete,
            risk_eligible_symbols=eligible,
            financial_symbols=self._repository.load_financial_symbols(),
            valuation_symbols=self._repository.load_valuation_symbols(),
            industry_symbols=self._repository.load_industry_symbols(),
            factor_input_symbols=self._repository.load_factor_input_symbols(),
            adjusted_return_symbols=self._repository.load_adjusted_return_symbols(),
        ))


def _sweep_failed(sweep: StructuralSlowInputSweepReport) -> bool:
    return any(
        batch.core_report.financial_failed or batch.core_report.industry_failed
        or batch.valuation_report.failed_symbols or batch.adjusted_return_report.failed_symbols
        for batch in sweep.batch_reports
    )
