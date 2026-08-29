"""Local composition boundary for current quality status."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from stock_selector.config.models import Settings
from stock_selector.quality.evaluator import DataQualityEvaluator
from stock_selector.quality.models import DataQualityStatus
from stock_selector.risk.evaluator import RiskEligibilityEvaluator
from stock_selector.storage import LocalMarketRepository
from stock_selector.universe.service import CurrentUniverseService


class CurrentQualityService:
    """Combine local repository records with explicit, testable quality logic."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._risk_evaluator = RiskEligibilityEvaluator()
        self._quality_evaluator = DataQualityEvaluator()

    def build_current(
        self,
        calculation_at: datetime | None = None,
        as_of: date | None = None,
    ) -> DataQualityStatus:
        """Build one offline status using the configured local timezone at the boundary."""
        timezone = ZoneInfo(self._settings.app.timezone)
        effective_calculation_at = calculation_at or datetime.now(timezone)
        effective_as_of = as_of or effective_calculation_at.astimezone(timezone).date()
        structural = CurrentUniverseService(self._repository, self._settings).build_current(
            effective_as_of
        )
        risk_snapshot = self._risk_evaluator.evaluate(
            structural,
            self._repository.load_risk_states(effective_as_of),
            self._settings.universe,
        )
        return self._quality_evaluator.evaluate(
            risk_snapshot,
            self._repository.get_stats().latest_realtime_at,
            effective_calculation_at,
            self._settings.realtime.freshness_normal_max_seconds,
            self._settings.realtime.freshness_warning_max_seconds,
        )
