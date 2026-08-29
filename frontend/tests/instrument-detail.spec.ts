import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getInstrument: vi.fn(),
  getDailyBars: vi.fn(),
  getLatestRealtime: vi.fn(),
}))
vi.mock('@/api/instruments', () => api)
vi.mock('echarts', () => ({ init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })) }))

import InstrumentDetailView from '@/views/InstrumentDetailView.vue'

const testInstrument = {
  symbol: '600519.SH', name: '测试茅台', exchange: 'SH', board: 'sh_main',
  listing_date: '2001-08-27', delisting_date: null, status: 'active',
}
const testDailyBar = {
  symbol: '600519.SH', trade_date: '2026-08-03', adjustment: 'raw', open: 10,
  high: 12, low: 9, close: 11, volume: 100, amount: 1100, source: 'test fixture',
}
const testQuote = {
  symbol: '600519.SH', price: 11, open: 10, high: 12, low: 9, prev_close: 10,
  volume: 100, amount: 1100, change_pct: 10, turnover_rate: null, volume_ratio: null,
  source_timestamp: null, ingested_at: '2026-08-28T08:00:00Z', source: 'test fixture',
}

async function mountDetail(symbol = '600519.SH') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/stocks/:symbol', component: InstrumentDetailView }],
  })
  await router.push(`/stocks/${symbol}`)
  await router.isReady()
  const wrapper = mount(InstrumentDetailView, { global: { plugins: [router, ElementPlus] } })
  await flushPromises()
  return wrapper
}

function resolveInstrument(): void {
  api.getInstrument.mockResolvedValue(testInstrument)
}

afterEach(() => vi.resetAllMocks())

describe('InstrumentDetailView', () => {
  it('distinguishes successful empty local data from request failures', async () => {
    resolveInstrument()
    api.getDailyBars.mockResolvedValue({ symbol: '600519.SH', available_rows: 0, returned_rows: 0, items: [] })
    api.getLatestRealtime.mockResolvedValue({ symbol: '600519.SH', available: false, latest_snapshot_at: '2026-08-28T08:00:00Z', quote: null })
    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('测试茅台')
    expect(wrapper.text()).toContain('暂无可用的本地实时快照')
    expect(wrapper.text()).toContain('暂无本地日线数据')
    expect(wrapper.text()).not.toContain('无法读取本地日线数据')
  })

  it('keeps metadata and realtime quote visible when daily request fails', async () => {
    resolveInstrument()
    api.getDailyBars.mockRejectedValue(new Error('daily unavailable'))
    api.getLatestRealtime.mockResolvedValue({ symbol: '600519.SH', available: true, latest_snapshot_at: '2026-08-28T08:00:00Z', quote: testQuote })
    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('测试茅台')
    expect(wrapper.text()).toContain('最新价')
    expect(wrapper.text()).toContain('无法读取本地日线数据')
    expect(wrapper.text()).not.toContain('暂无本地日线数据')
  })

  it('keeps metadata and daily content visible when realtime request fails', async () => {
    resolveInstrument()
    api.getDailyBars.mockResolvedValue({ symbol: '600519.SH', available_rows: 1, returned_rows: 1, items: [testDailyBar] })
    api.getLatestRealtime.mockRejectedValue(new Error('realtime unavailable'))
    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('2026-08-03')
    expect(wrapper.text()).toContain('无法读取本地实时数据')
    expect(wrapper.text()).not.toContain('暂无可用的本地实时快照')
  })

  it('shows a clear missing-instrument message for backend 404', async () => {
    api.getInstrument.mockRejectedValue({ response: { status: 404 } })
    api.getDailyBars.mockRejectedValue({ response: { status: 404 } })
    api.getLatestRealtime.mockRejectedValue({ response: { status: 404 } })
    const wrapper = await mountDetail('600520.SH')
    expect(wrapper.text()).toContain('未找到该股票')
  })
})
