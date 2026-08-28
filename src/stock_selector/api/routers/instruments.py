"""Instrument metadata and locally persisted market-data routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from stock_selector.api.dependencies import canonical_symbol, get_repository
from stock_selector.api.schemas import (
    DailyBarsResponse,
    InstrumentListResponse,
    InstrumentResponse,
    RealtimeLookupResponse,
)
from stock_selector.api.services import ReadOnlyMarketService
from stock_selector.storage import LocalMarketRepository

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=InstrumentListResponse)
def list_instruments(
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InstrumentListResponse:
    """List or simply substring-search locally stored instruments."""
    return ReadOnlyMarketService(repository).list_instruments(q, limit, offset)


@router.get("/{symbol}", response_model=InstrumentResponse)
def get_instrument(
    symbol: str,
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> InstrumentResponse:
    """Return one locally known instrument."""
    return ReadOnlyMarketService(repository).get_instrument(canonical_symbol(symbol))


@router.get("/{symbol}/daily", response_model=DailyBarsResponse)
def get_daily_bars(
    symbol: str,
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> DailyBarsResponse:
    """Return a date-clipped local daily-bar series."""
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must not precede start_date",
        )
    return ReadOnlyMarketService(repository).get_daily_bars(
        canonical_symbol(symbol), start_date, end_date, limit
    )


@router.get("/{symbol}/realtime", response_model=RealtimeLookupResponse)
def get_latest_realtime(
    symbol: str,
    repository: Annotated[LocalMarketRepository, Depends(get_repository)],
) -> RealtimeLookupResponse:
    """Return a target quote only from the newest local snapshot."""
    return ReadOnlyMarketService(repository).get_latest_realtime(canonical_symbol(symbol))
