import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getDailySelection: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('@/api/selection', () => api)
vi.mock('vue-router', () => ({ useRouter: () => router }))

import DailySelectionView from '@/views/DailySelectionView.vue'

const diagnostics = {
  input_instruments: 3,
  structural_members: 3,
  risk_records: 3,
  risk_complete_members: 3,
  risk_coverage_ratio: 1,
  risk_eligible_members: 3,
  factor_input_members: 3,
  scoreable_members: 2,
  requested_top_n: 20,
  returned_items: 2,
  price_factors_operational: false,
}

const notReadyResponse = {
  as_of: '2026-03-31T16:00:00+08:00',
  selection_ready: false,
  blockers: ['risk_state_coverage_incomplete'],
  diagnostics: { ...diagnostics, risk_records: 0, risk_complete_members: 0, risk_coverage_ratio: 0, risk_eligible_members: 0, factor_input_members: 0, scoreable_members: 0, returned_items: 0 },
  items: [],
}

const readyResponse = {
  as_of: '2026-03-31T16:00:00+08:00',
  selection_ready: true,
  blockers: [],
  diagnostics,
  items: [
    {
      rank: 1, symbol: '000001.SZ', name: '平安银行', board: 'sz_main', industry_code: 'J66', industry_name: '货币金融服务',
      base_score: 81.234, confidence_adjusted_score: 64.987, data_completeness: 0.75, confidence: 0.8,
      quality_score: 85, value_score: 80, growth_score: 79, momentum_score: null, low_volatility_score: null,
    },
    {
      rank: 2, symbol: '600519.SH', name: '贵州茅台', board: 'sh_main', industry_code: 'C15', industry_name: '酒、饮料和精制茶制造业',
      base_score: 80, confidence_adjusted_score: 60, data_completeness: 0.75, confidence: 0.75,
      quality_score: 80, value_score: 81, growth_score: 79, momentum_score: null, low_volatility_score: null,
    },
  ],
}

function mountView() {
  return mount(DailySelectionView, { global: { plugins: [ElementPlus] } })
}

afterEach(() => {
  vi.resetAllMocks()
})

describe('DailySelectionView', () => {
  it('renders explicit not-ready risk coverage diagnostics', async () => {
    api.getDailySelection.mockResolvedValue(notReadyResponse)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('今日选股尚未就绪')
    expect(wrapper.text()).toContain('风险状态覆盖不足')
    expect(wrapper.text()).toContain('结构股票池')
    expect(wrapper.text()).toContain('风险完整覆盖')
    expect(wrapper.text()).toContain('0%')
  })

  it('renders ready QVG rows with formatted scores and missing price families', async () => {
    api.getDailySelection.mockResolvedValue(readyResponse)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('000001.SZ')
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('81.2')
    expect(wrapper.text()).toContain('75%')
    expect(wrapper.text()).toContain('80%')
    expect(wrapper.text()).toContain('—')
  })

  it('shows loading and keeps HTTP failure separate from normal readiness', async () => {
    let resolveRequest: (value: typeof notReadyResponse) => void = () => undefined
    api.getDailySelection.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve }))
    const wrapper = mountView()
    await nextTick()
    expect(wrapper.get('[role="status"]').text()).toContain('正在读取本地今日选股状态')

    resolveRequest(notReadyResponse)
    await flushPromises()
    api.getDailySelection.mockRejectedValue(new Error('offline'))
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('无法读取本地今日选股状态。')
    expect(wrapper.text()).not.toContain('今日选股尚未就绪')
  })

  it('navigates to the clicked instrument detail row', async () => {
    api.getDailySelection.mockResolvedValue(readyResponse)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('tbody tr').trigger('click')

    expect(router.push).toHaveBeenCalledWith({
      name: 'instrument-detail',
      params: { symbol: '000001.SZ' },
    })
  })
})
