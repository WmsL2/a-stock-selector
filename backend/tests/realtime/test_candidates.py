"""Pure deterministic contracts for the Task 15 candidate foundation."""

from datetime import UTC, date, datetime
from math import nan

import pytest
from pydantic import ValidationError

from stock_selector.factors import FactorFamily
from stock_selector.realtime import (
    RealtimeCandidateBlocker,
    RealtimeCandidateEngine,
    RealtimeCandidatePolicy,
    RealtimeDataError,
)
from stock_selector.risk import (
    RiskEligibilityDecision,
    RiskEligibilitySnapshot,
    RiskExclusionReason,
)
from stock_selector.scoring import (
    BaseScoreCrossSectionResult,
    BaseScoreStockResult,
    FactorWeightContribution,
)

AS_OF = datetime(2026, 8, 31, 9, tzinfo=UTC)
WEIGHTS = {
    FactorFamily.QUALITY: 0.30,
    FactorFamily.VALUE: 0.25,
    FactorFamily.GROWTH: 0.20,
    FactorFamily.MOMENTUM: 0.15,
    FactorFamily.LOW_VOLATILITY: 0.10,
}


def test_default_policy_and_invalid_policy_values() -> None:
    assert RealtimeCandidatePolicy() == RealtimeCandidatePolicy(
        min_base_score=70.0, top_fraction=0.20
    )
    for values in (
        {"min_base_score": -0.001},
        {"min_base_score": 100.001},
        {"min_base_score": nan},
        {"top_fraction": 0},
        {"top_fraction": 1.001},
        {"top_fraction": nan},
    ):
        with pytest.raises(ValidationError):
            RealtimeCandidatePolicy(**values)


def test_ranks_by_base_score_then_symbol_not_confidence_adjusted_score() -> None:
    result = _build(
        _scores(
            _score("600519.SH", 80, confidence=0.30),
            _score("000001.SZ", 75, confidence=1),
            _score("000002.SZ", 75, confidence=1),
        ),
        _risk("000001.SZ", "000002.SZ", "600519.SH"),
        RealtimeCandidatePolicy(min_base_score=0, top_fraction=1),
    )
    assert [(item.symbol, item.market_rank) for item in result.candidates] == [
        ("600519.SH", 1),
        ("000001.SZ", 2),
        ("000002.SZ", 3),
    ]
    assert result.candidates[0].confidence < result.candidates[1].confidence


def test_low_completeness_remains_rankable_and_missing_base_score_does_not() -> None:
    result = _build(
        _scores(
            _score("000001.SZ", 80, low_completeness=True),
            _score("000002.SZ", None),
        ),
        _risk("000001.SZ", "000002.SZ"),
        RealtimeCandidatePolicy(min_base_score=70, top_fraction=1),
    )
    assert result.diagnostics.scoreable_risk_eligible_members == 1
    assert [(item.symbol, item.data_completeness) for item in result.candidates] == [
        ("000001.SZ", 0.30)
    ]


@pytest.mark.parametrize(
    ("count", "expected_bucket"), [(1000, 200), (999, 200), (5, 1), (1, 1)],
)
def test_top_fraction_uses_ceil_exact_size(count: int, expected_bucket: int) -> None:
    symbols = tuple(f"{code:06d}.SH" for code in range(600000, 600000 + count))
    result = _build(
        _scores(*(_score(symbol, 80) for symbol in symbols)),
        _risk(*symbols),
    )
    assert result.diagnostics.top_bucket_size == expected_bucket
    assert len(result.candidates) == expected_bucket


def test_tie_at_cutoff_uses_symbol_order_without_bucket_expansion() -> None:
    result = _build(
        _scores(*(_score(symbol, 80) for symbol in (
            "000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"
        ))),
        _risk("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"),
    )
    assert result.diagnostics.top_bucket_size == 1
    assert tuple(item.symbol for item in result.candidates) == ("000001.SZ",)


def test_threshold_is_inclusive_and_intersects_with_top_bucket() -> None:
    result = _build(
        _scores(
            _score("000001.SZ", 80),
        _score("000002.SZ", 75),
        _score("000003.SZ", 74),
        _score("000004.SZ", 70),
        _score("000005.SZ", 69.999),
        ),
        _risk("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"),
        RealtimeCandidatePolicy(min_base_score=70, top_fraction=0.20),
    )
    assert result.diagnostics.threshold_qualified_members == 4
    assert tuple(item.symbol for item in result.candidates) == ("000001.SZ",)


def test_risk_ineligible_member_never_enters_ranking_denominator() -> None:
    result = _build(
        _scores(_score("000001.SZ", 99), _score("000002.SZ", 80)),
        _risk("000001.SZ", "000002.SZ", eligible=("000002.SZ",)),
        RealtimeCandidatePolicy(min_base_score=70, top_fraction=1),
    )
    assert result.diagnostics.scoreable_risk_eligible_members == 1
    assert tuple(item.symbol for item in result.candidates) == ("000002.SZ",)


def test_incomplete_risk_coverage_blocks_without_candidate_ranking() -> None:
    result = _build(
        _scores(_score("000001.SZ", 80), _score("000002.SZ", 79)),
        _risk("000001.SZ", "000002.SZ", incomplete=("000002.SZ",)),
    )
    assert result.diagnostics.candidate_ready is False
    assert result.diagnostics.blockers == (
        RealtimeCandidateBlocker.RISK_STATE_COVERAGE_INCOMPLETE,
    )
    assert result.candidates == ()


@pytest.mark.parametrize(
    ("case", "blocker"),
    [
        ("empty", RealtimeCandidateBlocker.NO_STRUCTURAL_MEMBERS),
        ("no_eligible", RealtimeCandidateBlocker.NO_RISK_ELIGIBLE_MEMBERS),
        ("no_scoreable", RealtimeCandidateBlocker.NO_SCOREABLE_INSTRUMENTS),
    ],
)
def test_missing_required_candidate_inputs_produce_stable_blockers(
    case: str,
    blocker: RealtimeCandidateBlocker,
) -> None:
    scores, risk = {
        "empty": (_scores(), _risk()),
        "no_eligible": (
            _scores(_score("000001.SZ", 80)),
            _risk("000001.SZ", eligible=()),
        ),
        "no_scoreable": (
            _scores(_score("000001.SZ", None)),
            _risk("000001.SZ"),
        ),
    }[case]
    result = _build(scores, risk)
    assert result.diagnostics.candidate_ready is False
    assert result.diagnostics.blockers == (blocker,)
    assert result.candidates == ()


def test_ready_empty_result_has_no_fake_data_blocker() -> None:
    result = _build(
        _scores(_score("000001.SZ", 80)),
        _risk("000001.SZ"),
        RealtimeCandidatePolicy(min_base_score=90, top_fraction=0.20),
    )
    assert result.diagnostics.candidate_ready is True
    assert result.diagnostics.blockers == ()
    assert result.candidates == ()


def test_rejects_as_of_mismatch_and_foreign_score_symbols() -> None:
    with pytest.raises(RealtimeDataError, match="as_of"):
        _build(
            _scores(_score("000001.SZ", 80)),
            _risk("000001.SZ", as_of=date(2026, 8, 30)),
        )
    with pytest.raises(RealtimeDataError, match="non-structural"):
        _build(
            _scores(_score("000001.SZ", 80), _score("000002.SZ", 79)),
            _risk("000001.SZ"),
        )


def test_identical_inputs_produce_identical_results() -> None:
    scores = _scores(_score("000001.SZ", 80), _score("000002.SZ", 75))
    risk = _risk("000001.SZ", "000002.SZ")
    assert _build(scores, risk) == _build(scores, risk)


def _build(
    scores: BaseScoreCrossSectionResult,
    risk: RiskEligibilitySnapshot,
    policy: RealtimeCandidatePolicy | None = None,
):
    return RealtimeCandidateEngine().build(scores, risk, policy)


def _scores(*stocks: BaseScoreStockResult) -> BaseScoreCrossSectionResult:
    ordered = tuple(sorted(stocks, key=lambda item: item.symbol))
    return BaseScoreCrossSectionResult(as_of=AS_OF, input_count=len(ordered), stocks=ordered)


def _score(
    symbol: str,
    base_score: float | None,
    *,
    confidence: float = 1.0,
    low_completeness: bool = False,
) -> BaseScoreStockResult:
    available_families = (
        (FactorFamily.QUALITY,) if low_completeness and base_score is not None else tuple(FactorFamily)
    ) if base_score is not None else ()
    available_weight = sum(WEIGHTS[family] for family in available_families)
    resolved_confidence = 0.075 if low_completeness else confidence
    coverage = resolved_confidence / available_weight if low_completeness else resolved_confidence
    contributions = tuple(
        _contribution(
            family,
            base_score,
            family in available_families,
            coverage,
            available_weight,
        )
        for family in FactorFamily
    )
    return BaseScoreStockResult(
        symbol=symbol,
        as_of=AS_OF,
        base_score=base_score,
        data_completeness=available_weight,
        confidence=(resolved_confidence if base_score is not None else 0),
        confidence_adjusted_score=(
            base_score * resolved_confidence if base_score is not None else None
        ),
        available_family_weight=available_weight,
        enabled_family_weight=1.0,
        available_families=len(available_families),
        enabled_families=len(FactorFamily),
        contributions=contributions,
    )


def _contribution(
    family: FactorFamily,
    base_score: float | None,
    available: bool,
    coverage: float,
    available_weight: float,
) -> FactorWeightContribution:
    weight = WEIGHTS[family]
    return FactorWeightContribution(
        family=family,
        enabled=True,
        configured_weight=weight,
        family_score=(base_score if available else None),
        family_component_coverage=(coverage if available else 0),
        available=available,
        renormalized_weight=(weight / available_weight if available else 0),
        weighted_contribution=(base_score * weight / available_weight if available else None),
    )


def _risk(
    *symbols: str,
    eligible: tuple[str, ...] | None = None,
    incomplete: tuple[str, ...] = (),
    as_of: date | None = None,
) -> RiskEligibilitySnapshot:
    ordered = tuple(sorted(symbols))
    incomplete_symbols = set(incomplete)
    eligible_symbols = set(ordered if eligible is None else eligible) - incomplete_symbols
    decisions = tuple(
        RiskEligibilityDecision(
            symbol=symbol,
            eligible=symbol in eligible_symbols,
            risk_complete=symbol not in incomplete_symbols,
            reasons=(
                ()
                if symbol in eligible_symbols
                else (
                    (RiskExclusionReason.MISSING_RISK_STATE,)
                    if symbol in incomplete_symbols
                    else (RiskExclusionReason.ST,)
                )
            ),
        )
        for symbol in ordered
    )
    return RiskEligibilitySnapshot(
        as_of=as_of or AS_OF.date(),
        structural_members=len(decisions),
        risk_records=len(decisions),
        risk_complete_members=sum(item.risk_complete for item in decisions),
        eligible_members=tuple(symbol for symbol in ordered if symbol in eligible_symbols),
        decisions=decisions,
    )
