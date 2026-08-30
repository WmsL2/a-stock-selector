import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getRealtimeStatus: vi.fn() }))

vi.mock('@/api/realtime', () => ({ getRealtimeStatus: api.getRealtimeStatus }))

import RealtimeSelectionView from '@/views/RealtimeSelectionView.vue'

function response(freshness: 'fresh' | 'warning' | 'stale' | 'unavailable') {
  return {
    calculation_at: '2026-08-30T10:02:00Z',
    latest_ingested_at: freshness === 'unavailable' ? null : '2026-08-30T10:00:00Z',
    source: freshness === 'unavailable' ? null : 'akshare:stock_zh_a_spot_em',
    stored_quotes: freshness === 'unavailable' ? 0 : 2,
    source_timestamp_available_quotes: 0,
    freshness,
    age_seconds: freshness === 'unavailable' ? null : freshness === 'stale' ? 121 : 60,
    ranking_allowed: freshness === 'fresh' || freshness === 'warning',
    normal_max_seconds: 60,
    warning_max_seconds: 120,
    snapshot_scope: 'selective_persisted' as const,
  }
}

async function mountView() {
  const wrapper = mount(RealtimeSelectionView, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  return wrapper
}

describe('RealtimeSelectionView', () => {
  it.each([
    ['fresh', '正常', '允许（仅新鲜度门槛）'],
    ['warning', '警告', '允许（仅新鲜度门槛）'],
    ['stale', '过期', '不允许（仅新鲜度门槛）'],
    ['unavailable', '暂无数据', '不允许（仅新鲜度门槛）'],
  ] as const)('renders %s local status without a scanner', async (freshness, label, gate) => {
    api.getRealtimeStatus.mockResolvedValue(response(freshness))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).toContain(gate)
    expect(wrapper.text()).toContain('实时选股引擎尚未实现')
  })

  it('shows a truthful read failure without replacing the unfinished-engine notice', async () => {
    api.getRealtimeStatus.mockRejectedValue(new Error('offline'))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('本地实时快照状态暂不可读。')
    expect(wrapper.text()).toContain('Realtime Scanner、IntradayScore 与 RealTimeScore 尚未实现')
  })
})
