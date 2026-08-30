"""Errors for deterministic explanation input contracts."""


class ExplanationError(Exception):
    """Base error for explanation-domain failures."""


class ExplanationDataError(ExplanationError):
    """Raised when explanation inputs cannot represent one official selection."""
