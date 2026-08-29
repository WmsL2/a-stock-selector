"""Read-only daily-price storage status route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository
from stock_selector.api.schemas import DailyStatusResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("/status", response_model=DailyStatusResponse)
def get_daily_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> DailyStatusResponse:
    """Expose local RAW daily coverage only; this endpoint never collects data."""
    return ReadOnlyMarketService(repository).daily_status()
