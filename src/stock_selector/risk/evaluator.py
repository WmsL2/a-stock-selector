"""Pure exact-date, conservative dated-risk eligibility logic."""

from stock_selector.config.models import UniverseConfig
from stock_selector.risk.errors import RiskDataError
from stock_selector.risk.models import (
    DatedRiskState,
    RiskEligibilityDecision,
    RiskEligibilitySnapshot,
    RiskExclusionReason,
)
from stock_selector.universe.models import UniverseSnapshot


class RiskEligibilityEvaluator:
    """Evaluate only structural members without storage, providers, or clocks."""

    def evaluate(
        self,
        structural_snapshot: UniverseSnapshot,
        risk_states: tuple[DatedRiskState, ...],
        config: UniverseConfig,
    ) -> RiskEligibilitySnapshot:
        """Return exact-date eligibility without history lookup or carry-forward."""
        states = self._index_exact_states(structural_snapshot, risk_states)
        decisions = tuple(
            self._decide(symbol, states.get(symbol), config)
            for symbol in structural_snapshot.members
        )
        return RiskEligibilitySnapshot(
            as_of=structural_snapshot.as_of,
            structural_members=len(structural_snapshot.members),
            risk_records=len(risk_states),
            risk_complete_members=sum(decision.risk_complete for decision in decisions),
            eligible_members=tuple(
                decision.symbol for decision in decisions if decision.eligible
            ),
            decisions=decisions,
        )

    @staticmethod
    def _index_exact_states(
        structural_snapshot: UniverseSnapshot, risk_states: tuple[DatedRiskState, ...]
    ) -> dict[str, DatedRiskState]:
        states: dict[str, DatedRiskState] = {}
        for state in risk_states:
            if state.as_of != structural_snapshot.as_of:
                raise RiskDataError("risk state as_of must match structural snapshot as_of")
            if state.symbol in states:
                raise RiskDataError("duplicate risk state for symbol and as_of")
            states[state.symbol] = state
        return states

    @staticmethod
    def _decide(
        symbol: str, state: DatedRiskState | None, config: UniverseConfig
    ) -> RiskEligibilityDecision:
        if state is None:
            return RiskEligibilityDecision(
                symbol=symbol,
                eligible=False,
                risk_complete=False,
                reasons=(RiskExclusionReason.MISSING_RISK_STATE,),
            )
        fields = (
            (config.exclude_st, state.is_st, RiskExclusionReason.ST),
            (config.exclude_suspended, state.is_suspended, RiskExclusionReason.SUSPENDED),
            (
                config.exclude_delisting_period,
                state.is_delisting_period,
                RiskExclusionReason.DELISTING_PERIOD,
            ),
        )
        reasons = tuple(reason for enabled, value, reason in fields if enabled and value is True)
        risk_complete = all(value is not None for enabled, value, _ in fields if enabled)
        if not risk_complete:
            reasons += (RiskExclusionReason.UNKNOWN_RISK_FIELD,)
        return RiskEligibilityDecision(
            symbol=symbol,
            eligible=risk_complete and not reasons,
            risk_complete=risk_complete,
            reasons=reasons,
        )
