export interface HealthResponse {
  status: string
  application: string
  version: string
  storage: string
}

export interface StorageStatusResponse {
  instrument_rows: number
  daily_rows: number
  daily_symbols: number
  earliest_daily_trade_date: string | null
  latest_daily_trade_date: string | null
  realtime_rows: number
  realtime_symbols: number
  realtime_snapshots: number
  latest_realtime_at: string | null
  risk_state_rows: number
  risk_state_dates: number
  latest_risk_state_date: string | null
  disk_usage_bytes: number
  storage_root: string
  duckdb_path: string
}

export interface UniverseBoardCounts {
  sh_main: number
  sz_main: number
  chinext: number
  star: number
  bse: number
}

export interface UniverseExclusionCounts {
  board_disabled: number
  not_yet_listed: number
  delisted: number
  min_listing_days: number
}

export interface UniverseStatusResponse {
  as_of: string
  data_scope: string
  input_instruments: number
  included_instruments: number
  excluded_instruments: number
  boards: UniverseBoardCounts
  exclusions: UniverseExclusionCounts
  risk_filters_applied: boolean
  historical_survivorship_safe: boolean
}

export interface InstrumentResponse {
  symbol: string
  name: string
  exchange: string
  board: string
  listing_date: string
  delisting_date: string | null
  status: string
}

export interface InstrumentListResponse {
  total: number
  limit: number
  offset: number
  items: InstrumentResponse[]
}

export interface DailyBarResponse {
  symbol: string
  trade_date: string
  adjustment: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
  source: string
}

export interface DailyBarsResponse {
  symbol: string
  available_rows: number
  returned_rows: number
  items: DailyBarResponse[]
}

export interface RealtimeQuoteResponse {
  symbol: string
  price: number
  open: number | null
  high: number | null
  low: number | null
  prev_close: number | null
  volume: number | null
  amount: number | null
  change_pct: number | null
  turnover_rate: number | null
  volume_ratio: number | null
  source_timestamp: string | null
  ingested_at: string
  source: string
}

export interface RealtimeLookupResponse {
  symbol: string
  available: boolean
  latest_snapshot_at: string | null
  quote: RealtimeQuoteResponse | null
}

export interface PublicAppConfigResponse {
  timezone: string
}

export interface PublicUniverseConfigResponse {
  include_sh_main: boolean
  include_sz_main: boolean
  include_chinext: boolean
  include_star_market: boolean
  include_bse: boolean
  min_listing_days: number
  exclude_st: boolean
  exclude_delisting_period: boolean
  exclude_suspended: boolean
  liquidity_filter_enabled: boolean
  min_avg_turnover_20d: number
}

export interface PublicFactorGroupResponse {
  enabled: boolean
  weight: number
}

export interface PublicFactorsConfigResponse {
  quality: PublicFactorGroupResponse
  value: PublicFactorGroupResponse
  growth: PublicFactorGroupResponse
  momentum: PublicFactorGroupResponse
  low_volatility: PublicFactorGroupResponse
}

export interface PublicSelectionConfigResponse {
  top_n: number
  watchlist_n: number
}

export interface PublicRealtimeConfigResponse {
  enabled: boolean
  snapshot_interval_seconds: number
  freshness_normal_max_seconds: number
  freshness_warning_max_seconds: number
}

export interface PublicConfigResponse {
  app: PublicAppConfigResponse
  universe: PublicUniverseConfigResponse
  factors: PublicFactorsConfigResponse
  selection: PublicSelectionConfigResponse
  realtime: PublicRealtimeConfigResponse
}

export type RealtimeFreshness = 'fresh' | 'warning' | 'stale' | 'unavailable'

export interface QualityStatusResponse {
  as_of: string
  structural_instruments: number
  risk_state_records: number
  risk_complete_instruments: number
  risk_coverage_ratio: number
  risk_filter_ready: boolean
  risk_eligible_instruments: number | null
  latest_realtime_at: string | null
  realtime_age_seconds: number | null
  realtime_freshness: RealtimeFreshness
}

export interface DailyStatusResponse {
  stored_symbols: number
  stored_rows: number
  earliest_trade_date: string | null
  latest_trade_date: string | null
  adjustment_basis: string
  corporate_action_adjusted: boolean
  full_market_completeness_verified: boolean
  trading_calendar_gap_check_applied: boolean
}
