"""Read-only local fundamentals coverage route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository
from stock_selector.api.schemas import FundamentalsStatusResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])


@router.get("/status", response_model=FundamentalsStatusResponse)
def get_fundamentals_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> FundamentalsStatusResponse:
    """Expose only persisted point-in-time domain coverage and capability flags."""
    return ReadOnlyMarketService(repository).fundamentals_status()
