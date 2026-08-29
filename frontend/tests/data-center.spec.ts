import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getStorageStatus: vi.fn(),
  getUniverseStatus: vi.fn(),
}))
vi.mock('@/api/health', () => ({ getHealth: api.getHealth }))
vi.mock('@/api/storage', () => ({ getStorageStatus: api.getStorageStatus }))
vi.mock('@/api/universe', () => ({ getUniverseStatus: api.getUniverseStatus }))

import DataCenterView from '@/views/DataCenterView.vue'

describe('DataCenterView structural universe section', () => {
  it('shows board counts plus survivorship and deferred-risk disclosures', async () => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue({ instrument_rows: 2, daily_rows: 0, daily_symbols: 0, realtime_rows: 0, realtime_symbols: 0, realtime_snapshots: 0, latest_realtime_at: null, disk_usage_bytes: 0, storage_root: '/test/data', duckdb_path: '/test/catalog.duckdb' })
    api.getUniverseStatus.mockResolvedValue({ as_of: '2026-08-29', data_scope: 'current_instrument_master', input_instruments: 2, included_instruments: 1, excluded_instruments: 1, boards: { sh_main: 1, sz_main: 2, chinext: 3, star: 4, bse: 5 }, exclusions: { board_disabled: 1, not_yet_listed: 0, delisted: 0, min_listing_days: 0 }, risk_filters_applied: false, historical_survivorship_safe: false })
    const wrapper = mount(DataCenterView, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('结构股票池')
    expect(wrapper.text()).toContain('ChiNext')
    expect(wrapper.text()).toContain('当前股票池基于当前本地 Instrument Master')
    expect(wrapper.text()).toContain('ST、停牌、退市期等日期化风险过滤')
  })
})
