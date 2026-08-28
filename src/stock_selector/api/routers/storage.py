"""Local storage coverage routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_repository
from stock_selector.api.schemas import StorageStatusResponse
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/status", response_model=StorageStatusResponse)
def get_storage_status(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> StorageStatusResponse:
    """Expose local-only storage coverage and disk usage."""
    return ReadOnlyMarketService(repository).storage_status()
