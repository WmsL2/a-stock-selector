"""Offline local data-quality status route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository, get_settings
from stock_selector.api.schemas import QualityStatusResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.config import Settings
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/status", response_model=QualityStatusResponse)
def get_quality_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QualityStatusResponse:
    """Report local risk coverage and realtime ingestion freshness without networking."""
    return ReadOnlyMarketService(repository).quality_status(settings)
