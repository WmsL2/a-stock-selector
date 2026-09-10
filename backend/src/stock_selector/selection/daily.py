"""Purely local, explicit-time daily selection orchestration."""

from datetime import datetime

from stock_selector.config.models import Settings
from stock_selector.explanation import (
    ExplanationEngine,
    ExplanationInput,
    ExplanationResult,
)
from stock_selector.factors import (
    AdjustedReturnSeriesInput,
    FiveFactorEngine,
    FiveFactorRequest,
    StockFactorInput,
)
from stock_selector.models import Instrument
from stock_selector.models.common import ensure_aware_datetime
from stock_selector.models.selection import SelectionResult, StockScore
from stock_selector.risk import RiskEligibilitySnapshot
from stock_selector.risk.evaluator import RiskEligibilityEvaluator
from stock_selector.scoring import (
    BaseScoreEngine,
    BaseScoreRequest,
    BaseScoreStockResult,
)
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe import AshareUniverseBuilder

from .errors import SelectionDataError
from .input_readiness import (
    DailySelectionInputReadinessAuditor,
    DailySelectionInputReadinessBlocker,
    DailySelectionInputReadinessRequest,
)
from .models import DailySelectionDiagnostics, DailySelectionResult, SelectionBlocker


class DailySelectionService:
    """Build an on-demand official daily ranking from local PIT-safe records only."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._universe_builder = AshareUniverseBuilder()
        self._risk_evaluator = RiskEligibilityEvaluator()
        self._factor_engine = FiveFactorEngine()
        self._score_engine = BaseScoreEngine()
        self._explanation_engine = ExplanationEngine()
        self._input_readiness_auditor = DailySelectionInputReadinessAuditor()

    def build(self, as_of: datetime) -> DailySelectionResult:
        """Build one explicit-time result without a clock, provider, or storage mutation."""
        ensure_aware_datetime(as_of, "as_of")
        instruments = self._repository.load_instruments()
        structural = self._universe_builder.build(
            instruments, self._settings.universe, as_of.date()
        )
        risk_states = self._repository.load_risk_states(as_of.date(), structural.members)
        risk = self._risk_evaluator.evaluate(structural, risk_states, self._settings.universe)
        if not risk.structural_members:
            return self._result(
                as_of,
                instruments,
                risk,
                0,
                0,
                (),
                (SelectionBlocker.NO_STRUCTURAL_MEMBERS,),
            )
        risk_ready = (
            risk.risk_complete_members == risk.structural_members
        )
        if not risk_ready:
            return self._result(
                as_of,
                instruments,
                risk,
                0,
                0,
                (),
                (SelectionBlocker.RISK_STATE_COVERAGE_INCOMPLETE,),
            )
        if not risk.eligible_members:
            return self._result(
                as_of,
                instruments,
                risk,
                0,
                0,
                (),
                (SelectionBlocker.NO_RISK_ELIGIBLE_MEMBERS,),
            )
        factor_input_symbols = self._repository.load_factor_input_symbols()
        readiness = self._input_readiness_auditor.audit(
            DailySelectionInputReadinessRequest(
                as_of=as_of,
                structural_symbols=structural.members,
                risk_record_symbols=tuple(state.symbol for state in risk_states),
                risk_complete_symbols=tuple(
                    decision.symbol for decision in risk.decisions if decision.risk_complete
                ),
                risk_eligible_symbols=risk.eligible_members,
                factor_input_symbols=factor_input_symbols,
            )
        )
        if not readiness.upstream_inputs_ready:
            if readiness.blockers != (
                DailySelectionInputReadinessBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,
            ):
                raise SelectionDataError("contradictory upstream readiness after risk gates")
            return self._result(
                as_of,
                instruments,
                risk,
                readiness.eligible_factor_input_covered,
                0,
                (),
                (SelectionBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,),
            )
        factor_inputs = tuple(
            self._factor_input(symbol, as_of) for symbol in risk.eligible_members
        )
        factor_result = self._factor_engine.compute(FiveFactorRequest(stocks=factor_inputs))
        score_result = self._score_engine.compute(
            BaseScoreRequest(factors=factor_result, config=self._settings.factors)
        )
        scoreable = tuple(item for item in score_result.stocks if item.base_score is not None)
        ordered = tuple(sorted(scoreable, key=lambda item: (-_base_score(item), item.symbol)))
        factor_by_symbol = {item.symbol: item for item in factor_result.stocks}
        risk_by_symbol = {item.symbol: item for item in risk.decisions}
        top_items = tuple(
            _stock_score(
                item,
                rank,
                self._explanation_engine.explain(
                    ExplanationInput(
                        symbol=item.symbol,
                        as_of=as_of,
                        factor_result=factor_by_symbol[item.symbol],
                        score_result=item,
                        risk_decision=risk_by_symbol[item.symbol],
                        price_factors_operational=True,
                    )
                ),
            )
            for rank, item in enumerate(ordered[: self._settings.selection.top_n], start=1)
        )
        blockers: tuple[SelectionBlocker, ...] = ()
        if not ordered:
            blockers += (SelectionBlocker.NO_SCOREABLE_INSTRUMENTS,)
        return self._result(
            as_of,
            instruments,
            risk,
            readiness.eligible_factor_input_covered,
            len(ordered),
            top_items,
            blockers,
        )

    def _factor_input(self, symbol: str, as_of: datetime) -> StockFactorInput:
        financials = self._repository.load_latest_financials_as_of(symbol, as_of)
        current = financials[-1] if financials else None
        prior = (
            next(
                (
                    item
                    for item in reversed(financials)
                    if current is not None
                    and (item.report_period.year, item.report_period.month, item.report_period.day)
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
            raise SelectionDataError("multiple active records for selected classification")
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
            adjusted_return_series=(
                AdjustedReturnSeriesInput(symbol=symbol, as_of=as_of, points=returns)
                if (returns := self._repository.load_latest_adjusted_daily_returns_as_of(symbol, as_of))
                else None
            ),
        )

    def _result(
        self,
        as_of: datetime,
        instruments: tuple[Instrument, ...],
        risk: RiskEligibilitySnapshot,
        factor_input_members: int,
        scoreable_members: int,
        items: tuple[StockScore, ...],
        blockers: tuple[SelectionBlocker, ...],
    ) -> DailySelectionResult:
        diagnostics = DailySelectionDiagnostics(
            as_of=as_of,
            selection_ready=bool(items),
            blockers=blockers,
            input_instruments=len(instruments),
            structural_members=risk.structural_members,
            risk_records=risk.risk_records,
            risk_complete_members=risk.risk_complete_members,
            risk_coverage_ratio=(
                risk.risk_complete_members / risk.structural_members
                if risk.structural_members
                else 0.0
            ),
            risk_eligible_members=len(risk.eligible_members),
            factor_input_members=factor_input_members,
            scoreable_members=scoreable_members,
            requested_top_n=self._settings.selection.top_n,
            returned_items=len(items),
            price_factors_operational=True,
        )
        return DailySelectionResult(
            as_of=as_of,
            diagnostics=diagnostics,
            selection=SelectionResult(as_of=as_of, strategy_name="base_score_v1", items=items),
        )


def _stock_score(
    result: BaseScoreStockResult, rank: int, explanation: ExplanationResult
) -> StockScore:
    base_score = _base_score(result)
    families = {item.family.value: item.family_score for item in result.contributions}
    return StockScore(
        symbol=result.symbol,
        as_of=result.as_of,
        base_score=base_score,
        quality_score=families["quality"],
        value_score=families["value"],
        growth_score=families["growth"],
        momentum_score=families["momentum"],
        low_volatility_score=families["low_volatility"],
        data_completeness=result.data_completeness,
        confidence=result.confidence,
        confidence_adjusted_score=result.confidence_adjusted_score,
        market_rank=rank,
        industry_rank=None,
        evidence=explanation.evidence,
        risks=explanation.risks,
    )


def _base_score(result: BaseScoreStockResult) -> float:
    if result.base_score is None:
        raise SelectionDataError("scoreable result requires base_score")
    return result.base_score
