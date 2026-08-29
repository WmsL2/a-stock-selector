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
}))

vi.mock('@/api/health', () => ({ getHealth: api.getHealth }))
vi.mock('@/api/storage', () => ({ getStorageStatus: api.getStorageStatus }))
vi.mock('@/api/universe', () => ({ getUniverseStatus: api.getUniverseStatus }))
vi.mock('@/api/quality', () => ({ getQualityStatus: api.getQualityStatus }))
vi.mock('@/api/daily', () => ({ getDailyStatus: api.getDailyStatus }))

import DashboardView from '@/views/DashboardView.vue'

describe('DashboardView', () => {
  it('renders real values from the mocked local API response', async () => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue({ instrument_rows: 2, daily_rows: 3, daily_symbols: 1, earliest_daily_trade_date: '2026-08-03', latest_daily_trade_date: '2026-08-05', realtime_rows: 1, realtime_symbols: 1, realtime_snapshots: 2, latest_realtime_at: '2026-08-28T08:00:00Z', risk_state_rows: 0, risk_state_dates: 0, latest_risk_state_date: null, disk_usage_bytes: 1024, storage_root: '/test/data', duckdb_path: '/test/catalog.duckdb' })
    api.getUniverseStatus.mockResolvedValue({ as_of: '2026-08-29', data_scope: 'current_instrument_master', input_instruments: 2, included_instruments: 1, excluded_instruments: 1, boards: { sh_main: 1, sz_main: 0, chinext: 0, star: 0, bse: 0 }, exclusions: { board_disabled: 1, not_yet_listed: 0, delisted: 0, min_listing_days: 0 }, risk_filters_applied: false, historical_survivorship_safe: false })
    api.getQualityStatus.mockResolvedValue({ as_of: '2026-08-29', structural_instruments: 2, risk_state_records: 0, risk_complete_instruments: 0, risk_coverage_ratio: 0, risk_filter_ready: false, risk_eligible_instruments: null, latest_realtime_at: null, realtime_age_seconds: null, realtime_freshness: 'unavailable' })
    api.getDailyStatus.mockResolvedValue({ stored_symbols: 1, stored_rows: 3, earliest_trade_date: '2026-08-03', latest_trade_date: '2026-08-05', adjustment_basis: 'raw', corporate_action_adjusted: false, full_market_completeness_verified: false, trading_calendar_gap_check_applied: false })
    const wrapper = mount(DashboardView, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('全市场股票')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('1.0 KB')
    expect(wrapper.text()).toContain('当前结构股票池')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('2026-08-05')
  })

  it('keeps the dashboard available when universe status fails', async () => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue({ instrument_rows: 2, daily_rows: 0, daily_symbols: 0, earliest_daily_trade_date: null, latest_daily_trade_date: null, realtime_rows: 0, realtime_symbols: 0, realtime_snapshots: 0, latest_realtime_at: null, risk_state_rows: 0, risk_state_dates: 0, latest_risk_state_date: null, disk_usage_bytes: 0, storage_root: '/test/data', duckdb_path: '/test/catalog.duckdb' })
    api.getUniverseStatus.mockRejectedValue(new Error('universe unavailable'))
    api.getQualityStatus.mockRejectedValue(new Error('quality unavailable'))
    api.getDailyStatus.mockRejectedValue(new Error('daily unavailable'))
    const wrapper = mount(DashboardView, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('全市场股票')
    expect(wrapper.text()).toContain('股票池状态暂不可用')
  })
})
