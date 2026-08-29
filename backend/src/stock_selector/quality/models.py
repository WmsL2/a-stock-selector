"""Immutable data-quality status and realtime freshness classifications."""

from datetime import date, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime


class RealtimeFreshness(str, Enum):
    FRESH = "fresh"
    WARNING = "warning"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class DataQualityStatus(DomainModel):
    """Explicit local coverage and ingestion-age status, never inferred safety."""

    as_of: date
    structural_instruments: int = Field(ge=0)
    risk_state_records: int = Field(ge=0)
    risk_complete_instruments: int = Field(ge=0)
    risk_coverage_ratio: float = Field(ge=0, le=1)
    risk_filter_ready: bool
    risk_eligible_instruments: int | None = Field(default=None, ge=0)
    latest_realtime_at: datetime | None
    realtime_age_seconds: float | None = Field(default=None, ge=0)
    realtime_freshness: RealtimeFreshness

    @field_validator("latest_realtime_at")
    @classmethod
    def validate_realtime_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_aware_datetime(value, "latest_realtime_at")

    @model_validator(mode="after")
    def validate_quality_consistency(self) -> "DataQualityStatus":
        if self.risk_complete_instruments > self.structural_instruments:
            raise ValueError("risk complete instruments cannot exceed structural instruments")
        expected_ratio = (
            self.risk_complete_instruments / self.structural_instruments
            if self.structural_instruments
            else 0.0
        )
        if self.risk_coverage_ratio != expected_ratio:
            raise ValueError("risk coverage ratio must match instrument counts")
        expected_ready = (
            self.structural_instruments > 0
            and self.risk_complete_instruments == self.structural_instruments
        )
        if self.risk_filter_ready != expected_ready:
            raise ValueError("risk filter readiness must match complete coverage")
        if not self.risk_filter_ready and self.risk_eligible_instruments is not None:
            raise ValueError("risk eligible instruments are unknown until filters are ready")
        if self.risk_filter_ready and self.risk_eligible_instruments is None:
            raise ValueError("ready risk filters require an eligible instrument count")
        if self.realtime_freshness is RealtimeFreshness.UNAVAILABLE:
            if self.latest_realtime_at is not None or self.realtime_age_seconds is not None:
                raise ValueError("unavailable freshness requires no realtime timestamp or age")
        elif self.latest_realtime_at is None or self.realtime_age_seconds is None:
            raise ValueError("available freshness requires realtime timestamp and age")
        return self
