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

export interface RealtimeStatusResponse {
  calculation_at: string
  latest_ingested_at: string | null
  source: string | null
  stored_quotes: number
  source_timestamp_available_quotes: number
  freshness: RealtimeFreshness
  age_seconds: number | null
  ranking_allowed: boolean
  normal_max_seconds: number
  warning_max_seconds: number
  snapshot_scope: 'selective_persisted'
}

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

export interface FundamentalsStatusResponse {
  financial_symbols: number
  financial_rows: number
  latest_financial_available_at: string | null
  valuation_symbols: number
  valuation_rows: number
  latest_valuation_at: string | null
  industry_symbols: number
  industry_rows: number
  financial_point_in_time_safe: boolean
  valuation_history_supported: boolean
  industry_history_supported: boolean
}

export interface FinancialRecordResponse {
  symbol: string
  report_period: string
  announcement_date: string
  available_at: string
  roe: number | null
  revenue: number | null
  net_profit: number | null
  source: string
}

export interface FinancialRecordsResponse {
  symbol: string
  available: boolean
  as_of: string | null
  items: FinancialRecordResponse[]
}

export interface ValuationRecordResponse {
  symbol: string
  as_of: string
  pe: number | null
  pb: number | null
  ps: number | null
  pcf: number | null
  total_market_cap: number | null
  source: string
}

export interface ValuationLookupResponse {
  symbol: string
  available: boolean
  requested_as_of: string | null
  record: ValuationRecordResponse | null
}

export interface IndustryRecordResponse {
  symbol: string
  industry_code: string
  industry_name: string
  classification: string
  effective_from: string
  effective_to: string | null
  source: string
}

export interface IndustryRecordsResponse {
  symbol: string
  available: boolean
  as_of: string | null
  items: IndustryRecordResponse[]
}

export interface DailySelectionItemResponse {
  rank: number
  symbol: string
  name: string
  board: string
  industry_code: string | null
  industry_name: string | null
  base_score: number
  confidence_adjusted_score: number | null
  data_completeness: number
  confidence: number
  quality_score: number | null
  value_score: number | null
  growth_score: number | null
  momentum_score: number | null
  low_volatility_score: number | null
  evidence: EvidenceResponse[]
  risks: RiskFlagResponse[]
}

export interface EvidenceResponse {
  code: string
  message: string
  factor_name: string | null
  value: number | null
  percentile: number | null
  contribution: number | null
}

export interface RiskFlagResponse {
  code: string
  message: string
  severity: 'high' | 'warning' | 'info'
}

export interface DailySelectionDiagnosticsResponse {
  input_instruments: number
  structural_members: number
  risk_records: number
  risk_complete_members: number
  risk_coverage_ratio: number
  risk_eligible_members: number
  factor_input_members: number
  scoreable_members: number
  requested_top_n: number
  returned_items: number
  price_factors_operational: boolean
}

export interface DailySelectionResponse {
  as_of: string
  selection_ready: boolean
  blockers: string[]
  diagnostics: DailySelectionDiagnosticsResponse
  items: DailySelectionItemResponse[]
}
