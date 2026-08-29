"""Point-in-time risk-state records and conservative eligibility evaluation."""

from stock_selector.risk.errors import RiskDataError, RiskError
from stock_selector.risk.models import (
    DatedRiskState,
    RiskEligibilityDecision,
    RiskEligibilitySnapshot,
    RiskExclusionReason,
)

__all__ = [
    "DatedRiskState",
    "RiskDataError",
    "RiskEligibilityDecision",
    "RiskEligibilityEvaluator",
    "RiskEligibilitySnapshot",
    "RiskError",
    "RiskExclusionReason",
]


def __getattr__(name: str) -> object:
    """Load the evaluator lazily so passive storage can depend on risk records."""
    if name == "RiskEligibilityEvaluator":
        from stock_selector.risk.evaluator import RiskEligibilityEvaluator

        return RiskEligibilityEvaluator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
