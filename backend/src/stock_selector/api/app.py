"""FastAPI application factory for localhost-only local-data access."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from stock_selector import __version__
from stock_selector.api.errors import APIResourceNotFound
from stock_selector.api.routers import (
    config,
    daily,
    fundamentals,
    health,
    instruments,
    quality,
    realtime,
    selection,
    storage,
    universe,
)
from stock_selector.config import Settings, load_settings
from stock_selector.config.paths import AppPaths
from stock_selector.storage import LocalMarketRepository, StorageError

logger = logging.getLogger(__name__)


def create_app(paths: AppPaths | None = None, settings: Settings | None = None) -> FastAPI:
    """Create an application whose repository is initialized during lifespan."""
    resolved_paths = paths or AppPaths.from_project_root()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        repository = LocalMarketRepository(resolved_paths)
        repository.initialize()
        app_instance.state.repository = repository
        app_instance.state.settings = settings or load_settings(resolved_paths.config_dir)
        yield

    application = FastAPI(
        title="A Stock Selector API",
        version=__version__,
        description="Local read-only API for the A-share quantitative research application.",
        lifespan=lifespan,
    )
    application.add_exception_handler(APIResourceNotFound, _not_found_handler)
    application.add_exception_handler(StorageError, _storage_error_handler)
    application.include_router(health.router, prefix="/api")
    application.include_router(storage.router, prefix="/api")
    application.include_router(daily.router, prefix="/api")
    application.include_router(fundamentals.router, prefix="/api")
    application.include_router(instruments.router, prefix="/api")
    application.include_router(config.router, prefix="/api")
    application.include_router(universe.router, prefix="/api")
    application.include_router(quality.router, prefix="/api")
    application.include_router(realtime.router, prefix="/api")
    application.include_router(selection.router, prefix="/api")
    return application


async def _not_found_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Keep resource-not-found responses independent from internal exception shape."""
    assert isinstance(exc, APIResourceNotFound)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _storage_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Log local storage failures without leaking internal details to HTTP clients."""
    logger.exception("Local storage access failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "local storage unavailable"})


app = create_app()
