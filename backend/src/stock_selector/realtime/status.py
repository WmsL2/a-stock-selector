from datetime import datetime

from stock_selector.config.models import Settings
from stock_selector.quality import DataQualityError, DataQualityEvaluator
from stock_selector.quality.models import RealtimeFreshness
from stock_selector.storage import LocalMarketRepository

from .errors import RealtimeDataError
from .models import RealtimeMarketStatus


class RealtimeStatusService:
    """Build an offline-only view of the latest locally persisted snapshot."""

    def __init__(self, repository: LocalMarketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def build(self, calculation_at: datetime) -> RealtimeMarketStatus:
        """Evaluate freshness with caller-supplied time and no provider access."""
        quotes = self._repository.load_latest_realtime_snapshot()
        latest = quotes[0].ingested_at if quotes else None
        try:
            freshness, age = DataQualityEvaluator().evaluate_freshness(
                latest,
                calculation_at,
                self._settings.realtime.freshness_normal_max_seconds,
                self._settings.realtime.freshness_warning_max_seconds,
            )
        except DataQualityError as exc:
            raise RealtimeDataError("invalid realtime freshness input") from exc
        return RealtimeMarketStatus(
            calculation_at=calculation_at,
            latest_ingested_at=latest,
            source=quotes[0].source if quotes else None,
            stored_quotes=len(quotes),
            source_timestamp_available_quotes=sum(
                quote.source_timestamp is not None for quote in quotes
            ),
            freshness=freshness,
            age_seconds=age,
            ranking_allowed=freshness
            in {RealtimeFreshness.FRESH, RealtimeFreshness.WARNING},
            normal_max_seconds=self._settings.realtime.freshness_normal_max_seconds,
            warning_max_seconds=self._settings.realtime.freshness_warning_max_seconds,
        )
