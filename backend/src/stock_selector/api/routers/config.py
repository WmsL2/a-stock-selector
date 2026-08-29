"""Safe public configuration route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from stock_selector.api.dependencies import get_settings
from stock_selector.api.schemas import (
    PublicAppConfigResponse,
    PublicConfigResponse,
    PublicFactorGroupResponse,
    PublicFactorsConfigResponse,
    PublicRealtimeConfigResponse,
    PublicSelectionConfigResponse,
    PublicUniverseConfigResponse,
)
from stock_selector.config import Settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/public", response_model=PublicConfigResponse)
def get_public_config(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicConfigResponse:
    """Expose only a deliberate, non-sensitive configuration allowlist."""
    return PublicConfigResponse(
        app=PublicAppConfigResponse(timezone=settings.app.timezone),
        universe=PublicUniverseConfigResponse(
            include_sh_main=settings.universe.include_sh_main,
            include_sz_main=settings.universe.include_sz_main,
            include_chinext=settings.universe.include_chinext,
            include_star_market=settings.universe.include_star_market,
            include_bse=settings.universe.include_bse,
            min_listing_days=settings.universe.min_listing_days,
            exclude_st=settings.universe.exclude_st,
            exclude_delisting_period=settings.universe.exclude_delisting_period,
            exclude_suspended=settings.universe.exclude_suspended,
            liquidity_filter_enabled=settings.universe.liquidity_filter_enabled,
            min_avg_turnover_20d=settings.universe.min_avg_turnover_20d,
        ),
        factors=PublicFactorsConfigResponse(
            quality=_factor_group(settings.factors.quality.enabled, settings.factors.quality.weight),
            value=_factor_group(settings.factors.value.enabled, settings.factors.value.weight),
            growth=_factor_group(settings.factors.growth.enabled, settings.factors.growth.weight),
            momentum=_factor_group(
                settings.factors.momentum.enabled, settings.factors.momentum.weight
            ),
            low_volatility=_factor_group(
                settings.factors.low_volatility.enabled,
                settings.factors.low_volatility.weight,
            ),
        ),
        selection=PublicSelectionConfigResponse(
            top_n=settings.selection.top_n,
            watchlist_n=settings.selection.watchlist_n,
        ),
        realtime=PublicRealtimeConfigResponse(
            enabled=settings.realtime.enabled,
            snapshot_interval_seconds=settings.realtime.snapshot_interval_seconds,
            freshness_normal_max_seconds=settings.realtime.freshness_normal_max_seconds,
            freshness_warning_max_seconds=settings.realtime.freshness_warning_max_seconds,
        ),
    )


def _factor_group(enabled: bool, weight: float) -> PublicFactorGroupResponse:
    return PublicFactorGroupResponse(enabled=enabled, weight=weight)
