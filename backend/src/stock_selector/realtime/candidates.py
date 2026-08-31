"""Pure deterministic reduction from BaseScore and risk inputs to candidates."""

from math import ceil

from stock_selector.risk import RiskEligibilitySnapshot
from stock_selector.scoring import BaseScoreCrossSectionResult, BaseScoreStockResult

from .errors import RealtimeDataError
from .models import (
    RealtimeCandidate,
    RealtimeCandidateBlocker,
    RealtimeCandidateDiagnostics,
    RealtimeCandidatePolicy,
    RealtimeCandidateResult,
)


class RealtimeCandidateEngine:
    """Apply the official candidate policy without I/O, clocks, or side effects."""

    def build(
        self,
        scores: BaseScoreCrossSectionResult,
        risk: RiskEligibilitySnapshot,
        policy: RealtimeCandidatePolicy | None = None,
    ) -> RealtimeCandidateResult:
        """Return a deterministic policy result for one exact-date cross-section."""
        effective_policy = policy or RealtimeCandidatePolicy()
        if scores.as_of.date() != risk.as_of:
            raise RealtimeDataError("risk as_of must match BaseScore cross-section date")
        structural_symbols = {decision.symbol for decision in risk.decisions}
        foreign_symbols = {item.symbol for item in scores.stocks} - structural_symbols
        if foreign_symbols:
            raise RealtimeDataError("BaseScore cross-section contains non-structural symbols")

        blockers = _blockers(risk)
        if blockers:
            return _result(
                scores,
                risk,
                effective_policy,
                blockers=blockers,
                scoreable=(),
                top_bucket=(),
                threshold_qualified=(),
                candidates=(),
            )

        eligible_symbols = set(risk.eligible_members)
        scoreable = tuple(
            sorted(
                (
                    item
                    for item in scores.stocks
                    if item.symbol in eligible_symbols and item.base_score is not None
                ),
                key=lambda item: (-_base_score(item), item.symbol),
            )
        )
        if not scoreable:
            return _result(
                scores,
                risk,
                effective_policy,
                blockers=(RealtimeCandidateBlocker.NO_SCOREABLE_INSTRUMENTS,),
                scoreable=(),
                top_bucket=(),
                threshold_qualified=(),
                candidates=(),
            )

        top_bucket = scoreable[: ceil(len(scoreable) * effective_policy.top_fraction)]
        threshold_qualified = tuple(
            item
            for item in scoreable
            if _base_score(item) >= effective_policy.min_base_score
        )
        qualified_symbols = {item.symbol for item in threshold_qualified}
        candidates = tuple(
            RealtimeCandidate(
                symbol=item.symbol,
                as_of=scores.as_of,
                base_score=_base_score(item),
                market_rank=rank,
                data_completeness=item.data_completeness,
                confidence=item.confidence,
            )
            for rank, item in enumerate(top_bucket, start=1)
            if item.symbol in qualified_symbols
        )
        return _result(
            scores,
            risk,
            effective_policy,
            blockers=(),
            scoreable=scoreable,
            top_bucket=top_bucket,
            threshold_qualified=threshold_qualified,
            candidates=candidates,
        )


def _blockers(
    risk: RiskEligibilitySnapshot,
) -> tuple[RealtimeCandidateBlocker, ...]:
    if not risk.structural_members:
        return (RealtimeCandidateBlocker.NO_STRUCTURAL_MEMBERS,)
    if risk.risk_complete_members != risk.structural_members:
        return (RealtimeCandidateBlocker.RISK_STATE_COVERAGE_INCOMPLETE,)
    if not risk.eligible_members:
        return (RealtimeCandidateBlocker.NO_RISK_ELIGIBLE_MEMBERS,)
    return ()


def _result(
    scores: BaseScoreCrossSectionResult,
    risk: RiskEligibilitySnapshot,
    policy: RealtimeCandidatePolicy,
    *,
    blockers: tuple[RealtimeCandidateBlocker, ...],
    scoreable: tuple[BaseScoreStockResult, ...],
    top_bucket: tuple[BaseScoreStockResult, ...],
    threshold_qualified: tuple[BaseScoreStockResult, ...],
    candidates: tuple[RealtimeCandidate, ...],
) -> RealtimeCandidateResult:
    diagnostics = RealtimeCandidateDiagnostics(
        as_of=scores.as_of,
        policy=policy,
        candidate_ready=not blockers,
        blockers=blockers,
        structural_members=risk.structural_members,
        risk_complete_members=risk.risk_complete_members,
        risk_eligible_members=len(risk.eligible_members),
        base_score_input_members=len(scores.stocks),
        scoreable_risk_eligible_members=len(scoreable),
        top_bucket_size=len(top_bucket),
        top_bucket_members=len(top_bucket),
        threshold_qualified_members=len(threshold_qualified),
        final_candidate_members=len(candidates),
    )
    return RealtimeCandidateResult(
        as_of=scores.as_of,
        policy=policy,
        diagnostics=diagnostics,
        candidates=candidates,
    )


def _base_score(result: BaseScoreStockResult) -> float:
    if result.base_score is None:
        raise RealtimeDataError("scoreable candidate requires base_score")
    return result.base_score
