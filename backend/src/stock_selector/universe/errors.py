"""Small, explicit errors for structural universe construction."""


class UniverseError(Exception):
    """Base error for the structural universe boundary."""


class UniverseDataError(UniverseError):
    """Raised when input cannot produce an auditable deterministic universe."""
