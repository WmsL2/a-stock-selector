"""Deterministic, structured explanations for already-scored selections."""

from .engine import ExplanationEngine
from .errors import ExplanationDataError, ExplanationError
from .models import ExplanationInput, ExplanationResult

__all__ = [
    "ExplanationDataError",
    "ExplanationEngine",
    "ExplanationError",
    "ExplanationInput",
    "ExplanationResult",
]
