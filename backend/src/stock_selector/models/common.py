"""Shared validation primitives for immutable domain models."""

import math
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict

_SYMBOL_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")


class DomainModel(BaseModel):
    """Base configuration for strict, immutable domain records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def ensure_finite_float(value: float | None, field_name: str | None) -> float | None:
    """Reject non-finite numeric values without coercing them to missing data."""
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field_name or 'value'} must be finite")
    return value


def ensure_aware_datetime(value: datetime, field_name: str | None) -> datetime:
    """Require an explicit timezone for timestamped domain data."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name or 'timestamp'} must be timezone-aware")
    return value


def ensure_nonempty_string(value: str, field_name: str | None) -> str:
    """Reject empty strings after the model-level whitespace normalization."""
    if not value:
        raise ValueError(f"{field_name or 'value'} must not be empty")
    return value


def validate_symbol(symbol: str) -> str:
    """Validate the canonical six-digit security symbol and exchange suffix."""
    if not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("symbol must use the XXXXXX.SH, XXXXXX.SZ, or XXXXXX.BJ format")
    return symbol
