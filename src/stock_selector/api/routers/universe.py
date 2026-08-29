"""Current structural-universe read-only route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository
from stock_selector.api.schemas import UniverseStatusResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.config import load_settings
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/status", response_model=UniverseStatusResponse)
def get_universe_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> UniverseStatusResponse:
    """Report current local structural membership and its intentional limits."""
    return ReadOnlyMarketService(repository).universe_status(load_settings())
