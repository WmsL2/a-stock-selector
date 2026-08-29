"""Errors specific to pure factor preprocessing."""


class FactorPreprocessingError(Exception):
    """Base error for a preprocessing operation that cannot be completed."""


class FactorPreprocessingDataError(FactorPreprocessingError):
    """Raised when a requested cross-section violates preprocessing invariants."""
