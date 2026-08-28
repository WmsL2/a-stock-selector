"""FastAPI dependencies backed by the application lifecycle."""

from fastapi import HTTPException, Request, status

from stock_selector.models.common import validate_symbol
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


def canonical_symbol(symbol: str) -> str:
    """Validate a path symbol using the shared domain representation."""
    try:
        return validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
