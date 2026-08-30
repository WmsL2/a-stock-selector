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
vi.mock('@/api/realtime', () => ({
  getRealtimeStatus: vi.fn().mockResolvedValue({ calculation_at: '2026-08-30T10:00:00Z', latest_ingested_at: null, source: null, stored_quotes: 0, source_timestamp_available_quotes: 0, freshness: 'unavailable', age_seconds: null, ranking_allowed: false, normal_max_seconds: 60, warning_max_seconds: 120, snapshot_scope: 'selective_persisted' }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import BacktestView from '@/views/BacktestView.vue'
import FactorResearchView from '@/views/FactorResearchView.vue'
import RealtimeSelectionView from '@/views/RealtimeSelectionView.vue'

const mountView = (component: object) =>
  mount(component, { global: { plugins: [createPinia(), ElementPlus] } })

describe('truthful unfinished and readiness views', () => {
  it('preserves later truthful placeholders', () => {
    expect(mountView(RealtimeSelectionView).text()).toContain('实时选股引擎尚未实现')
    expect(mountView(FactorResearchView).text()).toContain('因子研究尚未实现')
    expect(mountView(BacktestView).text()).toContain('回测引擎尚未实现')
  })
})
