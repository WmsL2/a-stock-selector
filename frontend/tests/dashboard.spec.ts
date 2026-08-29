import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getStorageStatus: vi.fn(),
}))

vi.mock('@/api/health', () => ({ getHealth: api.getHealth }))
vi.mock('@/api/storage', () => ({ getStorageStatus: api.getStorageStatus }))

import DashboardView from '@/views/DashboardView.vue'

describe('DashboardView', () => {
  it('renders real values from the mocked local API response', async () => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue({ instrument_rows: 2, daily_rows: 3, daily_symbols: 1, realtime_rows: 1, realtime_symbols: 1, realtime_snapshots: 2, latest_realtime_at: '2026-08-28T08:00:00Z', disk_usage_bytes: 1024, storage_root: '/test/data', duckdb_path: '/test/catalog.duckdb' })
    const wrapper = mount(DashboardView, { global: { plugins: [createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('全市场股票')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('1.0 KB')
  })
})
