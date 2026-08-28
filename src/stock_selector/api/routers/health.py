"""Application health route without upstream network checks."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector import __version__
from stock_selector.api.dependencies import get_repository
from stock_selector.api.schemas import HealthResponse
from stock_selector.storage import LocalMarketRepository

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(
    _repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> HealthResponse:
    """Confirm the application and local storage boundary are ready."""
    return HealthResponse(
        status="ok",
        application="a-stock-selector",
        version=__version__,
        storage="ready",
    )
