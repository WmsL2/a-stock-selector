"""Read-only assembly of PIT slow inputs for the realtime application boundary."""

from datetime import datetime

from stock_selector.config.models import Settings
from stock_selector.factors import FiveFactorEngine, FiveFactorRequest, StockFactorInput
from stock_selector.models.common import ensure_aware_datetime
from stock_selector.risk import RiskEligibilitySnapshot
from stock_selector.risk.evaluator import RiskEligibilityEvaluator
from stock_selector.scoring import (
    BaseScoreCrossSectionResult,
    BaseScoreEngine,
    BaseScoreRequest,
)
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe import AshareUniverseBuilder

from .errors import RealtimeDataError
from .models import RealtimeSlowInputDiagnostics, RealtimeSlowInputResult


class RealtimeSlowInputService:
    """Assemble explicit-time local PIT inputs without selection or persistence."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._universe_builder = AshareUniverseBuilder()
        self._risk_evaluator = RiskEligibilityEvaluator()
        self._factor_engine = FiveFactorEngine()
        self._score_engine = BaseScoreEngine()

    def build(self, as_of: datetime) -> RealtimeSlowInputResult:
        """Build slow inputs from an already initialized repository at ``as_of``."""
        ensure_aware_datetime(as_of, "as_of")
        instruments = self._repository.load_instruments()
        structural = self._universe_builder.build(
            instruments, self._settings.universe, as_of.date()
        )
        risk = self._risk_evaluator.evaluate(
            structural,
            self._repository.load_risk_states(as_of.date(), structural.members),
            self._settings.universe,
        )
        risk_ready = (
            risk.structural_members > 0
            and risk.risk_complete_members == risk.structural_members
        )
        factor_inputs = self._factor_inputs(risk, as_of) if risk_ready else ()
        base_scores = self._base_scores(factor_inputs, as_of)
        diagnostics = RealtimeSlowInputDiagnostics(
            as_of=as_of,
            input_instruments=len(instruments),
            structural_members=len(structural.members),
            risk_records=risk.risk_records,
            risk_complete_members=risk.risk_complete_members,
            risk_eligible_members=len(risk.eligible_members),
            risk_coverage_ratio=(
                risk.risk_complete_members / risk.structural_members
                if risk.structural_members
                else 0.0
            ),
            risk_ready=risk_ready,
            factor_input_members=len(factor_inputs),
            financial_current_available_members=sum(
                item.financial_current is not None for item in factor_inputs
            ),
            financial_prior_year_available_members=sum(
                item.financial_prior_year is not None for item in factor_inputs
            ),
            valuation_available_members=sum(item.valuation is not None for item in factor_inputs),
            industry_available_members=sum(item.industry_key is not None for item in factor_inputs),
            base_score_input_members=base_scores.input_count,
            base_score_available_members=sum(
                item.base_score is not None for item in base_scores.stocks
            ),
            price_factors_operational=False,
        )
        return RealtimeSlowInputResult(
            as_of=as_of,
            structural=structural,
            risk=risk,
            factor_inputs=factor_inputs,
            base_scores=base_scores,
            diagnostics=diagnostics,
        )

    def _factor_inputs(
        self, risk: RiskEligibilitySnapshot, as_of: datetime
    ) -> tuple[StockFactorInput, ...]:
        covered_symbols = set(self._repository.load_factor_input_symbols())
        return tuple(
            self._factor_input(symbol, as_of)
            for symbol in risk.eligible_members
            if symbol in covered_symbols
        )

    def _factor_input(self, symbol: str, as_of: datetime) -> StockFactorInput:
        financials = self._repository.load_latest_financials_as_of(symbol, as_of)
        current = financials[-1] if financials else None
        prior = (
            next(
                (
                    item
                    for item in reversed(financials)
                    if (
                        item.report_period.year,
                        item.report_period.month,
                        item.report_period.day,
                    )
                    == (
                        current.report_period.year - 1,
                        current.report_period.month,
                        current.report_period.day,
                    )
                ),
                None,
            )
            if current is not None
            else None
        )
        industry_records = tuple(
            item
            for item in self._repository.load_industry_records(symbol, as_of=as_of.date())
            if item.classification == self._settings.selection.industry_classification
        )
        if len(industry_records) > 1:
            raise RealtimeDataError("multiple active records for selected classification")
        industry = industry_records[0] if industry_records else None
        return StockFactorInput(
            symbol=symbol,
            as_of=as_of,
            industry_key=(
                f"{industry.classification}:{industry.industry_code}"
                if industry is not None
                else None
            ),
            financial_current=current,
            financial_prior_year=prior,
            valuation=self._repository.load_latest_valuation_as_of(symbol, as_of),
            price_series=None,
        )

    def _base_scores(
        self, factor_inputs: tuple[StockFactorInput, ...], as_of: datetime
    ) -> BaseScoreCrossSectionResult:
        if not factor_inputs:
            return BaseScoreCrossSectionResult(as_of=as_of, input_count=0, stocks=())
        factors = self._factor_engine.compute(FiveFactorRequest(stocks=factor_inputs))
        return self._score_engine.compute(
            BaseScoreRequest(factors=factors, config=self._settings.factors)
        )
