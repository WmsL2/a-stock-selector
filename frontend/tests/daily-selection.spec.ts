import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getDailySelection: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('@/api/selection', () => api)
vi.mock('vue-router', () => ({ useRouter: () => router }))

import DailySelectionView from '@/views/DailySelectionView.vue'
import type { DailySelectionBlocker, DailySelectionResponse } from '@/api/types'

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

const notReadyResponse: DailySelectionResponse = {
  as_of: '2026-03-31T16:00:00+08:00',
  selection_ready: false,
  blockers: ['risk_state_coverage_incomplete'],
  diagnostics: { ...diagnostics, risk_records: 0, risk_complete_members: 0, risk_coverage_ratio: 0, risk_eligible_members: 0, factor_input_members: 0, scoreable_members: 0, returned_items: 0 },
  items: [],
}

const readyResponse: DailySelectionResponse = {
  as_of: '2026-03-31T16:00:00+08:00',
  selection_ready: true,
  blockers: [],
  diagnostics,
  items: [
    {
      rank: 1, symbol: '000001.SZ', name: '平安银行', board: 'sz_main', industry_code: 'J66', industry_name: '货币金融服务',
      base_score: 81.234, confidence_adjusted_score: 64.987, data_completeness: 0.75, confidence: 0.8,
      quality_score: 85, value_score: 80, growth_score: 79, momentum_score: null, low_volatility_score: null,
      evidence: [
        { code: 'family_quality_contribution', message: 'Quality 得分 85.0，对 BaseScore 贡献 34.0 分。', factor_name: 'quality', value: 85, percentile: null, contribution: 34 },
      ],
      risks: [
        { code: 'price_factors_unavailable', message: '当前本地 operational 日线为 RAW，Momentum 和 LowVol 未参与 BaseScore。', severity: 'warning' },
      ],
    },
    {
      rank: 2, symbol: '600519.SH', name: '贵州茅台', board: 'sh_main', industry_code: 'C15', industry_name: '酒、饮料和精制茶制造业',
      base_score: 80, confidence_adjusted_score: 60, data_completeness: 0.75, confidence: 0.75,
      quality_score: 80, value_score: 81, growth_score: 79, momentum_score: null, low_volatility_score: null,
      evidence: [
        { code: 'family_value_contribution', message: 'Value 得分 81.0，对 BaseScore 贡献 27.0 分。', factor_name: 'value', value: 81, percentile: null, contribution: 27 },
      ],
      risks: [
        { code: 'missing_momentum', message: 'Momentum 当前未参与 BaseScore。', severity: 'info' },
      ],
    },
  ],
}

const blockerFixtures: Record<DailySelectionBlocker, DailySelectionResponse> = {
  no_structural_members: { ...notReadyResponse, blockers: ['no_structural_members'], diagnostics: { ...notReadyResponse.diagnostics, structural_members: 0 } },
  risk_state_coverage_incomplete: notReadyResponse,
  no_risk_eligible_members: { ...notReadyResponse, blockers: ['no_risk_eligible_members'], diagnostics: { ...diagnostics, risk_eligible_members: 0, factor_input_members: 0, scoreable_members: 0, returned_items: 0 } },
  eligible_factor_input_coverage_incomplete: { ...notReadyResponse, blockers: ['eligible_factor_input_coverage_incomplete'], diagnostics: { ...diagnostics, scoreable_members: 0, returned_items: 0, factor_input_members: 2 } },
  no_scoreable_instruments: { ...notReadyResponse, blockers: ['no_scoreable_instruments'], diagnostics: { ...diagnostics, risk_eligible_members: 2, factor_input_members: 2, scoreable_members: 0, returned_items: 0 } },
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
    expect(wrapper.text()).toContain('精确日期风险覆盖不完整')
    expect(wrapper.text()).toContain('结构股票池')
    expect(wrapper.text()).toContain('风险完整覆盖')
    expect(wrapper.text()).toContain('0%')
  })

  it.each([
    ['no_structural_members', '当前结构股票池为空', '当前结构股票池规则'],
    ['risk_state_coverage_incomplete', '今日选股尚未就绪', '精确日期风险覆盖不完整'],
    ['no_risk_eligible_members', '当前无风险合格股票', '风险覆盖已完整'],
    ['eligible_factor_input_coverage_incomplete', '风险合格股票因子输入覆盖不完整', '官方排名被阻断'],
    ['no_scoreable_instruments', '当前无可评分股票', '可用 BaseScore'],
  ] as const)('renders %s as a truthful domain blocker', async (blocker, title, description) => {
    const response = blockerFixtures[blocker]
    api.getDailySelection.mockResolvedValue(response)
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain(title)
    expect(wrapper.text()).toContain(description)
    expect(wrapper.text()).toContain(`阻断原因：${blocker}`)
    expect(wrapper.text()).toContain('因子输入覆盖')
    expect(wrapper.find('tbody').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('无法读取本地今日选股状态。')
    if (blocker === 'no_structural_members') {
      expect(wrapper.text()).toContain('0')
      expect(wrapper.text()).not.toContain('风险覆盖不完整')
      expect(wrapper.text()).not.toContain('因子输入覆盖不完整')
    }
    if (blocker === 'no_risk_eligible_members') expect(wrapper.text()).toContain('100%')
    if (blocker === 'eligible_factor_input_coverage_incomplete') {
      expect(wrapper.text()).toContain('2 / 3')
      expect(wrapper.text()).toContain('不会只对已覆盖子集排名')
    }
    if (blocker === 'no_scoreable_instruments') {
      expect(wrapper.text()).toContain('2 / 2')
      expect(wrapper.text()).not.toContain('不会只对已覆盖子集排名')
    }
  })

  it('preserves returned blocker order and uses the first blocker presentation', async () => {
    api.getDailySelection.mockResolvedValue({
      ...notReadyResponse,
      blockers: ['no_risk_eligible_members', 'risk_state_coverage_incomplete'] as DailySelectionBlocker[],
    })
    const wrapper = mountView()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('当前无风险合格股票')
    expect(text.indexOf('no_risk_eligible_members')).toBeLessThan(text.indexOf('risk_state_coverage_incomplete'))
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
    expect(wrapper.text()).toContain('3 / 3')
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

  it('expands structured evidence and data limitations with severity presentation', async () => {
    api.getDailySelection.mockResolvedValue(readyResponse)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.el-table__expand-icon').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('主要依据')
    expect(wrapper.text()).toContain('数据与模型限制')
    expect(wrapper.text()).toContain('Quality 得分 85.0')
    expect(wrapper.text()).toContain('Momentum 和 LowVol 未参与 BaseScore')
    expect(wrapper.text()).toContain('warning')
    expect(wrapper.text()).toContain('不构成投资建议')
  })

  it('makes the empty-risk disclaimer explicit in an expanded row', async () => {
    api.getDailySelection.mockResolvedValue({
      ...readyResponse,
      items: [{ ...readyResponse.items[0], risks: [] }],
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.el-table__expand-icon').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('未生成额外数据/模型限制标签')
    expect(wrapper.text()).toContain('不代表证券无投资风险')
  })
})
