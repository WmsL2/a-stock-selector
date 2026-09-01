"""FastAPI dependencies backed by the application lifecycle."""

from datetime import datetime

from fastapi import HTTPException, Request, status

from stock_selector.config import Settings
from stock_selector.models.common import ensure_aware_datetime, validate_symbol
from stock_selector.providers.base import RealtimeMarketDataProvider
from stock_selector.storage import LocalMarketRepository


def get_repository(request: Request) -> LocalMarketRepository:
    """Return the repository initialized for this application instance."""
    repository = getattr(request.app.state, "repository", None)
    if not isinstance(repository, LocalMarketRepository):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="local storage unavailable",
        )
    return repository


def get_settings(request: Request) -> Settings:
    """Return the single lifespan-loaded settings object for this app instance."""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="application settings unavailable",
        )
    return settings


def get_realtime_provider(request: Request) -> RealtimeMarketDataProvider:
    """Return the lifespan-provided realtime provider without constructing one."""
    provider = getattr(request.app.state, "realtime_provider", None)
    if not isinstance(provider, RealtimeMarketDataProvider):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="realtime provider unavailable",
        )
    return provider


def canonical_symbol(symbol: str) -> str:
    """Validate a path symbol using the shared domain representation."""
    try:
        return validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


def aware_timestamp(value: datetime | None) -> datetime | None:
    """Reject naive timestamps before they can invalidate point-in-time reads."""
    if value is None:
        return None
    try:
        return ensure_aware_datetime(value, "as_of")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
