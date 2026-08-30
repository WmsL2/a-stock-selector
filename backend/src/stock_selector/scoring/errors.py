"""Small errors for pure BaseScore composition."""


class ScoringError(Exception):
    """Base error for a scoring operation."""


class ScoringDataError(ScoringError):
    """Raised when a factor cross-section violates scoring contracts."""
