"""Read-only realtime snapshot foundation status."""

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository, get_settings
from stock_selector.api.schemas import RealtimeStatusResponse
from stock_selector.config import Settings
from stock_selector.realtime import RealtimeStatusService
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/status", response_model=RealtimeStatusResponse)
def get_realtime_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealtimeStatusResponse:
    status = RealtimeStatusService(repository, settings).build(
        datetime.now(ZoneInfo(settings.app.timezone))
    )
    return RealtimeStatusResponse(**status.model_dump(mode="json"))
