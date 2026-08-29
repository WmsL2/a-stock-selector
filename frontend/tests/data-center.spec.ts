import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getStorageStatus: vi.fn(),
  getUniverseStatus: vi.fn(),
  getQualityStatus: vi.fn(),
  getDailyStatus: vi.fn(),
  getFundamentalsStatus: vi.fn(),
}))
vi.mock('@/api/health', () => ({ getHealth: api.getHealth }))
vi.mock('@/api/storage', () => ({ getStorageStatus: api.getStorageStatus }))
vi.mock('@/api/universe', () => ({ getUniverseStatus: api.getUniverseStatus }))
vi.mock('@/api/quality', () => ({ getQualityStatus: api.getQualityStatus }))
vi.mock('@/api/daily', () => ({ getDailyStatus: api.getDailyStatus }))
vi.mock('@/api/fundamentals', () => ({ getFundamentalsStatus: api.getFundamentalsStatus }))

import DataCenterView from '@/views/DataCenterView.vue'

describe('DataCenterView structural universe section', () => {
  it('shows board counts plus survivorship and deferred-risk disclosures', async () => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue({ instrument_rows: 2, daily_rows: 0, daily_symbols: 0, earliest_daily_trade_date: null, latest_daily_trade_date: null, realtime_rows: 0, realtime_symbols: 0, realtime_snapshots: 0, latest_realtime_at: null, risk_state_rows: 0, risk_state_dates: 0, latest_risk_state_date: null, disk_usage_bytes: 0, storage_root: '/test/data', duckdb_path: '/test/catalog.duckdb' })
    api.getUniverseStatus.mockResolvedValue({ as_of: '2026-08-29', data_scope: 'current_instrument_master', input_instruments: 2, included_instruments: 1, excluded_instruments: 1, boards: { sh_main: 1, sz_main: 2, chinext: 3, star: 4, bse: 5 }, exclusions: { board_disabled: 1, not_yet_listed: 0, delisted: 0, min_listing_days: 0 }, risk_filters_applied: false, historical_survivorship_safe: false })
    api.getQualityStatus.mockResolvedValue({ as_of: '2026-08-29', structural_instruments: 2, risk_state_records: 0, risk_complete_instruments: 0, risk_coverage_ratio: 0, risk_filter_ready: false, risk_eligible_instruments: null, latest_realtime_at: null, realtime_age_seconds: null, realtime_freshness: 'unavailable' })
    api.getDailyStatus.mockResolvedValue({ stored_symbols: 0, stored_rows: 0, earliest_trade_date: null, latest_trade_date: null, adjustment_basis: 'raw', corporate_action_adjusted: false, full_market_completeness_verified: false, trading_calendar_gap_check_applied: false })
    api.getFundamentalsStatus.mockResolvedValue({ financial_symbols: 0, financial_rows: 0, latest_financial_available_at: null, valuation_symbols: 0, valuation_rows: 0, latest_valuation_at: null, industry_symbols: 0, industry_rows: 0, financial_point_in_time_safe: true, valuation_history_supported: true, industry_history_supported: true })
    const wrapper = mount(DataCenterView, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('结构股票池')
    expect(wrapper.text()).toContain('ChiNext')
    expect(wrapper.text()).toContain('当前股票池基于当前本地 Instrument Master')
    expect(wrapper.text()).toContain('ST、停牌、退市期等日期化风险过滤')
    expect(wrapper.text()).toContain('风险状态数据尚未完整覆盖')
    expect(wrapper.text()).toContain('暂无数据')
    expect(wrapper.text()).toContain('Daily Price Storage')
    expect(wrapper.text()).toContain('未做')
  })
})
