"""Read-only on-demand daily BaseScore selection route."""

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from stock_selector.api.dependencies import (
    aware_timestamp,
    get_realtime_provider,
    get_repository,
    get_settings,
)
from stock_selector.api.realtime_selection import RealtimeSelectionAPIService
from stock_selector.api.schemas import DailySelectionResponse, RealtimeSelectionResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.config import Settings
from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/selection", tags=["selection"])


@router.get("/daily", response_model=DailySelectionResponse)
def get_daily_selection(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    as_of: Annotated[datetime | None, Query()] = None,
) -> DailySelectionResponse:
    """Return truthful local selection readiness or an on-demand ranked result."""
    resolved_as_of = aware_timestamp(as_of) or datetime.now(
        ZoneInfo(settings.app.timezone)
    )
    return ReadOnlyMarketService(repository).daily_selection(settings, resolved_as_of)


@router.get("/realtime", response_model=RealtimeSelectionResponse)
def get_realtime_selection(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[RealtimeMarketDataProvider, Depends(get_realtime_provider)],
    as_of: Annotated[datetime | None, Query()] = None,
) -> RealtimeSelectionResponse:
    """Project one all-market Task25 runtime execution into the compact Top100 API DTO."""
    resolved_as_of = aware_timestamp(as_of) or datetime.now(
        ZoneInfo(settings.app.timezone)
    )
    return RealtimeSelectionAPIService(repository, settings, provider).build(
        resolved_as_of
    )
