"""Explicit errors for dated risk-state validation and evaluation."""


class RiskError(Exception):
    """Base error for dated risk-state processing."""


class RiskDataError(RiskError):
    """Raised when dated risk data cannot support an auditable decision."""
