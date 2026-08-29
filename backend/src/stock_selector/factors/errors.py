"""Small errors for pure five-family factor computation."""


class FactorError(Exception):
    """Base error for a factor-engine operation."""


class FactorDataError(FactorError):
    """Raised when explicit factor inputs violate point-in-time contracts."""
