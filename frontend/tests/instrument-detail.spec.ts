import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getInstrument: vi.fn(),
  getDailyBars: vi.fn(),
  getLatestRealtime: vi.fn(),
}))
vi.mock('@/api/instruments', () => api)
vi.mock('echarts', () => ({ init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })) }))

import InstrumentDetailView from '@/views/InstrumentDetailView.vue'

describe('InstrumentDetailView', () => {
  it('handles local data absence without failing the instrument metadata page', async () => {
    api.getInstrument.mockResolvedValue({ symbol: '600519.SH', name: '测试茅台', exchange: 'SH', board: 'sh_main', listing_date: '2001-08-27', delisting_date: null, status: 'active' })
    api.getDailyBars.mockResolvedValue({ symbol: '600519.SH', available_rows: 0, returned_rows: 0, items: [] })
    api.getLatestRealtime.mockResolvedValue({ symbol: '600519.SH', available: false, latest_snapshot_at: '2026-08-28T08:00:00Z', quote: null })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/stocks/:symbol', component: InstrumentDetailView }] })
    await router.push('/stocks/600519.SH')
    await router.isReady()
    const wrapper = mount(InstrumentDetailView, { global: { plugins: [router, ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('测试茅台')
    expect(wrapper.text()).toContain('暂无可用的本地实时快照')
    expect(wrapper.text()).toContain('暂无本地日线数据')
  })

  it('shows a clear missing-instrument message for backend 404', async () => {
    api.getInstrument.mockRejectedValue({ response: { status: 404 } })
    api.getDailyBars.mockRejectedValue({ response: { status: 404 } })
    api.getLatestRealtime.mockRejectedValue({ response: { status: 404 } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/stocks/:symbol', component: InstrumentDetailView }] })
    await router.push('/stocks/600520.SH')
    await router.isReady()
    const wrapper = mount(InstrumentDetailView, { global: { plugins: [router, ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('未找到该股票')
  })
})
