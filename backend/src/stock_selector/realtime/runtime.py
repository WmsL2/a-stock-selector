"""One-shot runtime orchestration over existing slow, capture, and pipeline stages."""

from datetime import datetime
from zoneinfo import ZoneInfo

from stock_selector.config.models import Settings
from stock_selector.models.common import ensure_aware_datetime
from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.storage import LocalMarketRepository

from .application import RealtimeSelectionApplicationService
from .collector import RealtimeSnapshotCollector
from .models import (
    RealtimeCaptureRequest,
    RealtimeSelectionPipelinePolicy,
    RealtimeSelectionRuntimeResult,
)
from .slow_inputs import RealtimeSlowInputService


class RealtimeSelectionRuntimeService:
    """Run Task24, one non-persistent all-market capture, and Task23 exactly once."""

    def __init__(
        self,
        repository: LocalMarketRepository,
        settings: Settings,
        provider: RealtimeMarketDataProvider,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._provider = provider

    def run(
        self,
        as_of: datetime,
        *,
        calculation_at: datetime | None = None,
        policy: RealtimeSelectionPipelinePolicy | None = None,
    ) -> RealtimeSelectionRuntimeResult:
        """Run one explicit slow/capture/pipeline sequence without persistence."""
        ensure_aware_datetime(as_of, "as_of")
        if calculation_at is not None:
            ensure_aware_datetime(calculation_at, "calculation_at")
        slow_inputs = RealtimeSlowInputService(self._repository, self._settings).build(as_of)
        capture = RealtimeSnapshotCollector(self._provider).capture(
            RealtimeCaptureRequest(symbols=None, persist_symbols=())
        )
        resolved_calculation_at = calculation_at or _system_calculation_at(
            self._settings.app.timezone
        )
        resolved_policy = policy or RealtimeSelectionPipelinePolicy(
            freshness_normal_max_seconds=self._settings.realtime.freshness_normal_max_seconds,
            freshness_warning_max_seconds=self._settings.realtime.freshness_warning_max_seconds,
        )
        pipeline = RealtimeSelectionApplicationService().run(
            slow_inputs.base_scores,
            slow_inputs.risk,
            capture,
            resolved_calculation_at,
            resolved_policy,
        )
        return RealtimeSelectionRuntimeResult(
            as_of=as_of,
            calculation_at=resolved_calculation_at,
            slow_inputs=slow_inputs,
            capture=capture,
            pipeline_policy=resolved_policy,
            pipeline=pipeline,
        )


def _system_calculation_at(timezone_name: str) -> datetime:
    """Read one aware system instant only after a successful capture."""
    return datetime.now(ZoneInfo(timezone_name))
