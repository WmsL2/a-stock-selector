"""Explicit, stable HTTP response data-transfer objects."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class APIResponseModel(BaseModel):
    """Base schema that rejects accidental response fields."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(APIResponseModel):
    status: str
    application: str
    version: str
    storage: str


class StorageStatusResponse(APIResponseModel):
    instrument_rows: int
    daily_rows: int
    daily_symbols: int
    realtime_rows: int
    realtime_symbols: int
    realtime_snapshots: int
    latest_realtime_at: datetime | None
    risk_state_rows: int
    risk_state_dates: int
    latest_risk_state_date: date | None
    disk_usage_bytes: int
    storage_root: str
    duckdb_path: str


class UniverseBoardCountsResponse(APIResponseModel):
    sh_main: int
    sz_main: int
    chinext: int
    star: int
    bse: int


class UniverseExclusionCountsResponse(APIResponseModel):
    board_disabled: int
    not_yet_listed: int
    delisted: int
    min_listing_days: int


class UniverseStatusResponse(APIResponseModel):
    as_of: date
    data_scope: str
    input_instruments: int
    included_instruments: int
    excluded_instruments: int
    boards: UniverseBoardCountsResponse
    exclusions: UniverseExclusionCountsResponse
    risk_filters_applied: bool
    historical_survivorship_safe: bool


class InstrumentResponse(APIResponseModel):
    symbol: str
    name: str
    exchange: str
    board: str
    listing_date: date
    delisting_date: date | None
    status: str


class InstrumentListResponse(APIResponseModel):
    total: int
    limit: int
    offset: int
    items: list[InstrumentResponse]


class DailyBarResponse(APIResponseModel):
    symbol: str
    trade_date: date
    adjustment: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: str


class DailyBarsResponse(APIResponseModel):
    symbol: str
    available_rows: int
    returned_rows: int
    items: list[DailyBarResponse]


class RealtimeQuoteResponse(APIResponseModel):
    symbol: str
    price: float
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume: float | None
    amount: float | None
    change_pct: float | None
    turnover_rate: float | None
    volume_ratio: float | None
    source_timestamp: datetime | None
    ingested_at: datetime
    source: str


class RealtimeLookupResponse(APIResponseModel):
    symbol: str
    available: bool
    latest_snapshot_at: datetime | None
    quote: RealtimeQuoteResponse | None


class PublicAppConfigResponse(APIResponseModel):
    timezone: str


class PublicUniverseConfigResponse(APIResponseModel):
    include_sh_main: bool
    include_sz_main: bool
    include_chinext: bool
    include_star_market: bool
    include_bse: bool
    min_listing_days: int
    exclude_st: bool
    exclude_delisting_period: bool
    exclude_suspended: bool
    liquidity_filter_enabled: bool
    min_avg_turnover_20d: float


class PublicFactorGroupResponse(APIResponseModel):
    enabled: bool
    weight: float


class PublicFactorsConfigResponse(APIResponseModel):
    quality: PublicFactorGroupResponse
    value: PublicFactorGroupResponse
    growth: PublicFactorGroupResponse
    momentum: PublicFactorGroupResponse
    low_volatility: PublicFactorGroupResponse


class PublicSelectionConfigResponse(APIResponseModel):
    top_n: int
    watchlist_n: int


class PublicRealtimeConfigResponse(APIResponseModel):
    enabled: bool
    snapshot_interval_seconds: int
    freshness_normal_max_seconds: int
    freshness_warning_max_seconds: int


class PublicConfigResponse(APIResponseModel):
    app: PublicAppConfigResponse
    universe: PublicUniverseConfigResponse
    factors: PublicFactorsConfigResponse
    selection: PublicSelectionConfigResponse
    realtime: PublicRealtimeConfigResponse


class QualityStatusResponse(APIResponseModel):
    as_of: date
    structural_instruments: int
    risk_state_records: int
    risk_complete_instruments: int
    risk_coverage_ratio: float
    risk_filter_ready: bool
    risk_eligible_instruments: int | None
    latest_realtime_at: datetime | None
    realtime_age_seconds: float | None
    realtime_freshness: str
