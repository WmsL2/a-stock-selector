import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const chartMocks = vi.hoisted(() => ({
  dispose: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
  init: vi.fn(),
}))

vi.mock('echarts', () => ({
  init: chartMocks.init.mockReturnValue({
    setOption: chartMocks.setOption,
    resize: chartMocks.resize,
    dispose: chartMocks.dispose,
  }),
}))

import StockDailyChart from '@/components/StockDailyChart.vue'

describe('StockDailyChart', () => {
  it('renders local OHLC bars and disposes its chart', async () => {
    const wrapper = mount(StockDailyChart, {
      props: {
        bars: [{ symbol: '600519.SH', trade_date: '2026-08-03', adjustment: 'raw', open: 10, high: 12, low: 9, close: 11, volume: 100, amount: 1100, source: 'test fixture' }],
      },
    })
    await nextTick()
    expect(chartMocks.init).toHaveBeenCalledOnce()
    expect(chartMocks.setOption).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(chartMocks.dispose).toHaveBeenCalledOnce()
  })
})
