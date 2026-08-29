"""Pure quality calculations with explicit timestamps and thresholds."""

from datetime import datetime

from stock_selector.models.common import ensure_aware_datetime
from stock_selector.quality.models import DataQualityStatus, RealtimeFreshness
from stock_selector.risk.models import RiskEligibilitySnapshot


class DataQualityError(Exception):
    """Raised when freshness input cannot describe a real elapsed duration."""


class DataQualityEvaluator:
    """Derive risk coverage and local-ingestion freshness without side effects."""

    def evaluate_freshness(
        self,
        latest_ingested_at: datetime | None,
        calculation_at: datetime,
        normal_max_seconds: int,
        warning_max_seconds: int,
    ) -> tuple[RealtimeFreshness, float | None]:
        """Classify local ingestion age using caller-supplied, positive thresholds."""
        ensure_aware_datetime(calculation_at, "calculation_at")
        if normal_max_seconds <= 0 or warning_max_seconds <= normal_max_seconds:
            raise DataQualityError("freshness thresholds must be positive and ordered")
        if latest_ingested_at is None:
            return RealtimeFreshness.UNAVAILABLE, None
        ensure_aware_datetime(latest_ingested_at, "latest_ingested_at")
        age_seconds = (calculation_at - latest_ingested_at).total_seconds()
        if age_seconds < 0:
            raise DataQualityError("latest realtime ingestion cannot be in the future")
        if age_seconds <= normal_max_seconds:
            return RealtimeFreshness.FRESH, age_seconds
        if age_seconds <= warning_max_seconds:
            return RealtimeFreshness.WARNING, age_seconds
        return RealtimeFreshness.STALE, age_seconds

    def evaluate(
        self,
        risk_snapshot: RiskEligibilitySnapshot,
        latest_realtime_at: datetime | None,
        calculation_at: datetime,
        normal_max_seconds: int,
        warning_max_seconds: int,
    ) -> DataQualityStatus:
        """Build the complete quality status from pure snapshots and timestamps."""
        freshness, age_seconds = self.evaluate_freshness(
            latest_realtime_at,
            calculation_at,
            normal_max_seconds,
            warning_max_seconds,
        )
        structural = risk_snapshot.structural_members
        complete = risk_snapshot.risk_complete_members
        ready = structural > 0 and complete == structural
        return DataQualityStatus(
            as_of=risk_snapshot.as_of,
            structural_instruments=structural,
            risk_state_records=risk_snapshot.risk_records,
            risk_complete_instruments=complete,
            risk_coverage_ratio=complete / structural if structural else 0.0,
            risk_filter_ready=ready,
            risk_eligible_instruments=(len(risk_snapshot.eligible_members) if ready else None),
            latest_realtime_at=latest_realtime_at,
            realtime_age_seconds=age_seconds,
            realtime_freshness=freshness,
        )
