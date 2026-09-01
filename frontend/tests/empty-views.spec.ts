import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api/health', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', application: 'test', version: '0', storage: 'ready' }),
}))
vi.mock('@/api/storage', () => ({
  getStorageStatus: vi.fn().mockResolvedValue({ instrument_rows: 0, daily_rows: 0, daily_symbols: 0, realtime_rows: 0, realtime_symbols: 0, realtime_snapshots: 0, latest_realtime_at: null, disk_usage_bytes: 0, storage_root: '', duckdb_path: '' }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import BacktestView from '@/views/BacktestView.vue'
import FactorResearchView from '@/views/FactorResearchView.vue'

const mountView = (component: object) =>
  mount(component, { global: { plugins: [createPinia(), ElementPlus] } })

describe('truthful unfinished and readiness views', () => {
  it('preserves later truthful placeholders', () => {
    expect(mountView(FactorResearchView).text()).toContain('因子研究尚未实现')
    expect(mountView(BacktestView).text()).toContain('回测引擎尚未实现')
  })
})
