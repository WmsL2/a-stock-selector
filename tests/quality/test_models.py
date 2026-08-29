"""Data quality model validation tests."""

from datetime import date

import pytest
from pydantic import ValidationError

from stock_selector.quality import DataQualityStatus, RealtimeFreshness


def test_quality_status_rejects_unknown_eligible_count_before_readiness() -> None:
    with pytest.raises(ValidationError):
        DataQualityStatus(
            as_of=date(2026, 8, 29),
            structural_instruments=4,
            risk_state_records=2,
            risk_complete_instruments=2,
            risk_coverage_ratio=0.5,
            risk_filter_ready=False,
            risk_eligible_instruments=0,
            latest_realtime_at=None,
            realtime_age_seconds=None,
            realtime_freshness=RealtimeFreshness.UNAVAILABLE,
        )
