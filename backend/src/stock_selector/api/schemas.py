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
    earliest_daily_trade_date: date | None
    latest_daily_trade_date: date | None
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
    non_a_share_security: int
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


class RealtimeStatusResponse(APIResponseModel):
    calculation_at: datetime
    latest_ingested_at: datetime | None
    source: str | None
    stored_quotes: int
    source_timestamp_available_quotes: int
    freshness: str
    age_seconds: float | None
    ranking_allowed: bool
    normal_max_seconds: int
    warning_max_seconds: int
    snapshot_scope: str


class RealtimeSelectionFamilyPolicyResponse(APIResponseModel):
    enabled: bool
    weight: float


class RealtimeSelectionPolicyResponse(APIResponseModel):
    candidate_min_base_score: float
    candidate_top_fraction: float
    freshness_normal_max_seconds: int
    freshness_warning_max_seconds: int
    strong_move_pct: float
    high_turnover_rate_pct: float
    high_volume_ratio: float
    relative_strength: RealtimeSelectionFamilyPolicyResponse
    activity_liquidity: RealtimeSelectionFamilyPolicyResponse
    vwap_trend: RealtimeSelectionFamilyPolicyResponse
    short_momentum: RealtimeSelectionFamilyPolicyResponse
    risk_stability: RealtimeSelectionFamilyPolicyResponse
    realtime_base_weight: float
    realtime_intraday_weight: float
    min_intraday_score: float
    top_n: int


class RealtimeSelectionDiagnosticsResponse(APIResponseModel):
    structural_members: int
    risk_records: int
    risk_complete_members: int
    risk_coverage_ratio: float
    risk_eligible_members: int
    factor_input_members: int
    base_score_available_members: int
    price_factors_operational: bool
    capture_scope: str | None
    capture_source: str | None
    capture_ingested_at: datetime | None
    received_quotes: int
    source_timestamp_available_quotes: int
    persisted_quotes: int
    freshness: str
    age_seconds: float | None
    freshness_allowed: bool
    candidate_ready: bool
    candidate_blockers: list[str]
    candidate_members: int
    snapshot_ready: bool
    snapshot_blockers: list[str]
    scan_ready: bool
    scan_blockers: list[str]
    normalization_ready: bool
    normalization_blockers: list[str]
    factor_ready: bool
    factor_blockers: list[str]
    intraday_score_ready: bool
    intraday_score_blockers: list[str]
    realtime_score_ready: bool
    realtime_score_blockers: list[str]
    selection_ready: bool
    selection_blockers: list[str]
    intraday_score_available_items: int
    ranking_universe_items: int
    selected_items: int


class RealtimeSelectionItemResponse(APIResponseModel):
    realtime_rank: int
    market_rank: int
    symbol: str
    name: str
    board: str
    industry_key: str | None
    quote: RealtimeQuoteResponse
    base_score: float
    base_data_completeness: float
    base_confidence: float
    intraday_score: float
    intraday_data_completeness: float
    intraday_confidence: float
    intraday_confidence_adjusted_score: float
    relative_strength_score: float | None
    activity_liquidity_score: float | None
    vwap_trend_score: float | None
    short_momentum_score: float | None
    risk_stability_score: float | None
    realtime_score: float
    realtime_data_completeness: float
    realtime_confidence: float
    realtime_confidence_adjusted_score: float


class RealtimeSelectionResponse(APIResponseModel):
    as_of: datetime
    calculation_at: datetime
    selection_ready: bool
    blockers: list[str]
    policy: RealtimeSelectionPolicyResponse
    diagnostics: RealtimeSelectionDiagnosticsResponse
    items: list[RealtimeSelectionItemResponse]


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
    industry_classification: str


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


class DailyStatusResponse(APIResponseModel):
    stored_symbols: int
    stored_rows: int
    earliest_trade_date: date | None
    latest_trade_date: date | None
    adjustment_basis: str
    corporate_action_adjusted: bool
    full_market_completeness_verified: bool
    trading_calendar_gap_check_applied: bool


class FundamentalsStatusResponse(APIResponseModel):
    financial_symbols: int
    financial_rows: int
    latest_financial_available_at: datetime | None
    valuation_symbols: int
    valuation_rows: int
    latest_valuation_at: datetime | None
    industry_symbols: int
    industry_rows: int
    financial_point_in_time_safe: bool
    valuation_history_supported: bool
    industry_history_supported: bool


class FinancialRecordResponse(APIResponseModel):
    symbol: str
    report_period: date
    announcement_date: date
    available_at: datetime
    roe: float | None
    roa: float | None
    gross_margin: float | None
    net_margin: float | None
    revenue: float | None
    net_profit: float | None
    deducted_net_profit: float | None
    operating_cash_flow: float | None
    total_assets: float | None
    total_liabilities: float | None
    source: str


class FinancialRecordsResponse(APIResponseModel):
    symbol: str
    available: bool
    as_of: datetime | None
    items: list[FinancialRecordResponse]


class ValuationRecordResponse(APIResponseModel):
    symbol: str
    as_of: datetime
    pe: float | None
    pb: float | None
    ps: float | None
    pcf: float | None
    dividend_yield: float | None
    total_market_cap: float | None
    float_market_cap: float | None
    source: str


class ValuationLookupResponse(APIResponseModel):
    symbol: str
    available: bool
    requested_as_of: datetime | None
    record: ValuationRecordResponse | None


class IndustryRecordResponse(APIResponseModel):
    symbol: str
    industry_code: str
    industry_name: str
    classification: str
    effective_from: date
    effective_to: date | None
    source: str


class IndustryRecordsResponse(APIResponseModel):
    symbol: str
    available: bool
    as_of: date | None
    items: list[IndustryRecordResponse]


class EvidenceResponse(APIResponseModel):
    code: str
    message: str
    factor_name: str | None
    value: float | None
    percentile: float | None
    contribution: float | None


class RiskFlagResponse(APIResponseModel):
    code: str
    message: str
    severity: str


class DailySelectionItemResponse(APIResponseModel):
    rank: int
    symbol: str
    name: str
    board: str
    industry_code: str | None
    industry_name: str | None
    base_score: float
    confidence_adjusted_score: float | None
    data_completeness: float
    confidence: float
    quality_score: float | None
    value_score: float | None
    growth_score: float | None
    momentum_score: float | None
    low_volatility_score: float | None
    evidence: list[EvidenceResponse]
    risks: list[RiskFlagResponse]


class DailySelectionDiagnosticsResponse(APIResponseModel):
    input_instruments: int
    structural_members: int
    risk_records: int
    risk_complete_members: int
    risk_coverage_ratio: float
    risk_eligible_members: int
    factor_input_members: int
    scoreable_members: int
    requested_top_n: int
    returned_items: int
    price_factors_operational: bool


class DailySelectionResponse(APIResponseModel):
    as_of: datetime
    selection_ready: bool
    blockers: list[str]
    diagnostics: DailySelectionDiagnosticsResponse
    items: list[DailySelectionItemResponse]
