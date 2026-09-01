import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getRealtimeSelection: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('@/api/selection', () => api)
vi.mock('vue-router', () => ({ useRouter: () => router }))

import RealtimeSelectionView from '@/views/RealtimeSelectionView.vue'

const policy = {
  candidate_min_base_score: 70, candidate_top_fraction: 0.2,
  freshness_normal_max_seconds: 60, freshness_warning_max_seconds: 120,
  strong_move_pct: 3, high_turnover_rate_pct: 4.5, high_volume_ratio: 1.8,
  relative_strength: { enabled: true, weight: 0.3 }, activity_liquidity: { enabled: true, weight: 0.25 },
  vwap_trend: { enabled: true, weight: 0.2 }, short_momentum: { enabled: true, weight: 0.15 },
  risk_stability: { enabled: true, weight: 0.1 }, realtime_base_weight: 0.75,
  realtime_intraday_weight: 0.25, min_intraday_score: 65, top_n: 100,
}

const diagnostics = {
  structural_members: 100, risk_records: 100, risk_complete_members: 100, risk_coverage_ratio: 1,
  risk_eligible_members: 98, factor_input_members: 98, base_score_available_members: 98,
  price_factors_operational: false, capture_scope: 'all_market', capture_source: 'fake:realtime',
  capture_ingested_at: '2026-09-01T10:00:00+08:00', received_quotes: 5546,
  source_timestamp_available_quotes: 0, persisted_quotes: 0, freshness: 'fresh' as const,
  age_seconds: 3.5, freshness_allowed: true, candidate_ready: true, candidate_blockers: [],
  candidate_members: 20, snapshot_ready: true, snapshot_blockers: [], scan_ready: true,
  scan_blockers: [], normalization_ready: true, normalization_blockers: [], factor_ready: true,
  factor_blockers: [], intraday_score_ready: true, intraday_score_blockers: [], realtime_score_ready: true,
  realtime_score_blockers: [], selection_ready: true, selection_blockers: [],
  intraday_score_available_items: 20, ranking_universe_items: 2, selected_items: 2,
}

const firstItem = {
  realtime_rank: 1, market_rank: 4, symbol: '000001.SZ', name: '平安银行', board: 'sz_main', industry_key: '证监会:C15',
  quote: { symbol: '000001.SZ', price: 12.34, open: 12, high: 12.5, low: 11.8, prev_close: 11.95, volume: 100, amount: 1200, change_pct: 3.25, turnover_rate: 4.5, volume_ratio: 1.8, source_timestamp: null, ingested_at: '2026-09-01T10:00:00+08:00', source: 'fake:realtime' },
  base_score: 81.2, base_data_completeness: 0.8, base_confidence: 0.7,
  intraday_score: 73.4, intraday_data_completeness: 0.6, intraday_confidence: 0.5,
  intraday_confidence_adjusted_score: 36.7, relative_strength_score: 88.8,
  activity_liquidity_score: 77.7, vwap_trend_score: null, short_momentum_score: null,
  risk_stability_score: 66.6, realtime_score: 79.7, realtime_data_completeness: 0.75,
  realtime_confidence: 0.65, realtime_confidence_adjusted_score: 51.805,
}

function response(overrides: Record<string, unknown> = {}) {
  return {
    as_of: '2026-09-01T09:30:00+08:00', calculation_at: '2026-09-01T10:00:03+08:00',
    selection_ready: true, blockers: [], policy, diagnostics,
    items: [firstItem, { ...firstItem, realtime_rank: 2, market_rank: 1, symbol: '600519.SH', name: '贵州茅台', realtime_score: 70.1 }],
    ...overrides,
  }
}

function mountView() {
  return mount(RealtimeSelectionView, { global: { plugins: [ElementPlus] } })
}

async function run(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('button').trigger('click')
  await flushPromises()
}

afterEach(() => vi.resetAllMocks())

describe('RealtimeSelectionView', () => {
  it('stays idle without any realtime request until an explicit click', () => {
    const wrapper = mountView()
    expect(api.getRealtimeSelection).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('尚未运行实时选股')
    expect(wrapper.text()).toContain('运行一次实时选股')
  })

  it('runs exactly once per click and renders backend order and supplied scores', async () => {
    api.getRealtimeSelection.mockResolvedValue(response())
    const wrapper = mountView()
    await run(wrapper)

    expect(api.getRealtimeSelection).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('000001.SZ')
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('81.2')
    expect(wrapper.text()).toContain('73.4')
    expect(wrapper.text()).toContain('79.7')
    expect(wrapper.text()).toContain('3.25%')
    expect(wrapper.text()).toContain('证监会:C15')
    const rows = wrapper.findAll('.instrument-table tbody tr')
    expect(rows[0].text()).toContain('000001.SZ')
    expect(rows[1].text()).toContain('600519.SH')
  })

  it('shows loading without an old result and enables a manual rerun only after completion', async () => {
    let resolveRequest: (value: ReturnType<typeof response>) => void = () => undefined
    api.getRealtimeSelection.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve }))
    const wrapper = mountView()
    await wrapper.get('button').trigger('click')
    await nextTick()

    expect(wrapper.get('[role="status"]').text()).toContain('正在执行一次实时选股')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('tbody').exists()).toBe(false)
    resolveRequest(response())
    await flushPromises()
    expect(wrapper.text()).toContain('RealtimeScore Top 2')
  })

  it('shows selected-row audit evidence, quote units, and unavailable families faithfully', async () => {
    api.getRealtimeSelection.mockResolvedValue(response())
    const wrapper = mountView()
    await run(wrapper)
    await wrapper.find('.el-table__expand-icon').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('Relative Strength')
    expect(wrapper.text()).toContain('Activity / Liquidity')
    expect(wrapper.text()).toContain('VWAP / Trend')
    expect(wrapper.text()).toContain('Short Momentum')
    expect(wrapper.text()).toContain('Risk / Stability')
    expect(wrapper.text()).toContain('4.50% / 1.80x')
    expect(wrapper.text()).toContain('fake:realtime')
    expect(wrapper.text()).toContain('Base 完整度 / 置信度')
    expect(wrapper.text()).toContain('—')
  })

  it('distinguishes blocked and ready-empty API results without transport errors', async () => {
    api.getRealtimeSelection.mockResolvedValueOnce(response({ selection_ready: false, blockers: ['realtime_score_not_ready'], diagnostics: { ...diagnostics, snapshot_ready: false, snapshot_blockers: ['candidate_quote_coverage_incomplete'], realtime_score_ready: false, realtime_score_blockers: ['intraday_score_not_ready'], selection_ready: false, selection_blockers: ['realtime_score_not_ready'], selected_items: 0 }, items: [] }))
    const wrapper = mountView()
    await run(wrapper)
    expect(wrapper.text()).toContain('实时选股尚未就绪')
    expect(wrapper.text()).toContain('candidate_quote_coverage_incomplete')
    expect(wrapper.text()).toContain('realtime_score_not_ready')

    api.getRealtimeSelection.mockResolvedValueOnce(response({ items: [], diagnostics: { ...diagnostics, selected_items: 0, ranking_universe_items: 0 } }))
    await run(wrapper)
    expect(wrapper.text()).toContain('当前规则下暂无 Top100 入选股票')
    expect(wrapper.text()).not.toContain('实时选股尚未就绪')
  })

  it('clears stale selected rows after a failed rerun', async () => {
    api.getRealtimeSelection.mockResolvedValueOnce(response()).mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountView()
    await run(wrapper)
    expect(wrapper.text()).toContain('平安银行')
    await run(wrapper)
    expect(api.getRealtimeSelection).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('实时选股请求失败，本次结果未生成')
    expect(wrapper.text()).not.toContain('平安银行')
  })

  it('navigates a selected row to its existing instrument detail route', async () => {
    api.getRealtimeSelection.mockResolvedValue(response())
    const wrapper = mountView()
    await run(wrapper)
    await wrapper.find('.instrument-table tbody tr').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'instrument-detail', params: { symbol: '000001.SZ' } })
  })

  it('shows read-only API policy and capture diagnostics without controls', async () => {
    api.getRealtimeSelection.mockResolvedValue(response())
    const wrapper = mountView()
    await run(wrapper)
    await wrapper.find('.el-collapse-item__header').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('70.0')
    expect(wrapper.text()).toContain('20%')
    expect(wrapper.text()).toContain('Base 75% / Intraday 25%')
    expect(wrapper.text()).toContain('65.0 / 100')
    expect(wrapper.text()).toContain('5546')
    expect(wrapper.text()).toContain('persisted_quotes = 0')
  })
})
