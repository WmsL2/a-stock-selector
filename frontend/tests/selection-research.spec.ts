import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SelectionResearchEffectivenessResponse, SelectionResearchHistoryResponse, SelectionResearchSnapshotResponse } from '@/api/types'

const api = vi.hoisted(() => ({
  getDailySelection: vi.fn(),
  getSelectionResearchEffectiveness: vi.fn(),
  getSelectionResearchHistory: vi.fn(),
  getSelectionResearchLatest: vi.fn(),
  selectionResearchDownloadUrl: vi.fn(),
}))
vi.mock('@/api/selection', () => api)
import SelectionResearchView from '@/views/SelectionResearchView.vue'

const firstItem = {
  rank: 2, as_of: '2026-09-16T16:00:00+08:00', symbol: '600519.SH', name: '贵州茅台', board: 'sh_main',
  industry_code: 'C15', industry_name: '饮料制造', base_score: 72.5, confidence_adjusted_score: null,
  data_completeness: 0.75, confidence: 0.8, quality_score: 81, value_score: 70, growth_score: 68,
  momentum_score: null, low_volatility_score: null,
  evidence: [{ code: 'quality', message: '质量依据', factor_name: null, value: null, percentile: null, contribution: null }],
  risks: [{ code: 'volatility', message: '波动风险', severity: 'warning' as const }],
}
const secondItem = {
  ...firstItem, rank: 1, symbol: '000001.SZ', name: '平安银行', board: 'sz_main', base_score: 91,
  confidence_adjusted_score: 75, data_completeness: 0.8, confidence: 0.75,
  evidence: [{ ...firstItem.evidence[0], code: 'value', message: '价值依据' }], risks: [],
}
const snapshot: SelectionResearchSnapshotResponse = {
  schema_version: 1, as_of: '2026-09-16T16:00:00+08:00', strategy_name: 'official', selection_ready: true,
  blockers: [], refresh_had_collection_failures: false,
  diagnostics: { input_instruments: 2, structural_members: 2, risk_records: 2, risk_complete_members: 2, risk_coverage_ratio: 1, risk_eligible_members: 2, factor_input_members: 2, scoreable_members: 2, requested_top_n: 20, returned_items: 2, price_factors_operational: true },
  items: [firstItem, secondItem],
}
const horizon = (sessions: number, value: number | null = null) => ({ horizon_sessions: sessions, total_labels: 2, available_labels: value === null ? 0 : 2, anchor_unavailable_labels: 0, insufficient_future_returns_labels: 0, non_contiguous_return_evidence_labels: 0, availability_rate: value === null ? null : 1, positive_return_labels: 1, zero_return_labels: 1, negative_return_labels: 0, positive_return_rate: value === null ? null : 0.5, mean_return_fraction: value, median_return_fraction: value })
const effectiveness: SelectionResearchEffectivenessResponse = { evaluated_at: '2026-09-20T16:00:00+08:00', start_date: null, end_date: null, snapshot_count: 1, empty_snapshot_count: 0, item_observation_count: 2, overall_horizons: [horizon(5, 0.125), horizon(20), horizon(60)], ranks: [{ rank: 1, observation_count: 1, horizons: [horizon(5, 0.125), horizon(20), horizon(60)] }, { rank: 3, observation_count: 1, horizons: [horizon(5, 0.125), horizon(20), horizon(60)] }], cutoffs: [{ cutoff_rank: 1, included_ranks: [1], observation_count: 1, horizons: [horizon(5, 0.125), horizon(20), horizon(60)] }, { cutoff_rank: 3, included_ranks: [1, 3], observation_count: 2, horizons: [horizon(5, 0.125), horizon(20), horizon(60)] }] }
const historySnapshot = (as_of: string, value: SelectionResearchSnapshotResponse = snapshot): SelectionResearchSnapshotResponse => ({ ...value, as_of })
const history = (snapshots: SelectionResearchSnapshotResponse[]): SelectionResearchHistoryResponse => ({ start_date: null, end_date: null, snapshot_count: snapshots.length, snapshots })

function mountView() { return mount(SelectionResearchView, { global: { plugins: [ElementPlus] } }) }
function mockSnapshot(value: SelectionResearchSnapshotResponse = snapshot) {
  api.getSelectionResearchLatest.mockResolvedValue({ available: true, snapshot: value })
}

afterEach(() => { vi.resetAllMocks(); vi.restoreAllMocks() })

describe('SelectionResearchView', () => {
  it('uses only the persisted research API and retains exact official item order', async () => {
    api.getDailySelection.mockImplementation(() => { throw new Error('daily API must not be called') })
    mockSnapshot()
    const wrapper = mountView(); await flushPromises()

    const text = wrapper.text()
    expect(api.getDailySelection).not.toHaveBeenCalled()
    expect(api.getSelectionResearchEffectiveness).not.toHaveBeenCalled()
    expect(api.getSelectionResearchHistory).not.toHaveBeenCalled()
    expect(text.indexOf('600519.SH')).toBeLessThan(text.indexOf('000001.SZ'))
    expect(text).toContain('72.5')
    expect(text).toContain('91.0')
    expect(text).toContain('—')
    expect(text).toContain('75.0')
    expect(text).toContain('75%')
    expect(text).toContain('80%')
  })

  it('loads effectiveness only on explicit aware PIT input and preserves sparse ranks', async () => {
    mockSnapshot(); api.getSelectionResearchEffectiveness.mockResolvedValue(effectiveness)
    const wrapper = mountView(); await flushPromises()
    const button = wrapper.get('[data-testid="load-effectiveness"]')
    expect(button.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="evaluated-at-input"]').setValue(' 2026-09-20T16:00:00+08:00 ')
    await wrapper.get('[data-testid="start-date-input"]').setValue('')
    await wrapper.get('[data-testid="end-date-input"]').setValue('')
    await button.trigger('click'); await flushPromises()
    expect(api.getSelectionResearchEffectiveness).toHaveBeenCalledWith({ evaluated_at: '2026-09-20T16:00:00+08:00' })
    expect(wrapper.get('[data-testid="overall-horizons"]').text()).toContain('12.50%')
    const overall = wrapper.get('[data-testid="overall-horizons"]').text()
    expect(overall.indexOf('5')).toBeLessThan(overall.indexOf('20'))
    expect(overall.indexOf('20')).toBeLessThan(overall.indexOf('60'))
    expect(wrapper.find('[data-testid="effectiveness-rank-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="effectiveness-rank-3"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="effectiveness-rank-2"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="effectiveness-cutoff-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="effectiveness-cutoff-3"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="effectiveness-cutoff-2"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="rank-cutoffs"]').text()).toContain('1, 3')
  })

  it('sends explicit date ranges without time conversion', async () => {
    mockSnapshot(); api.getSelectionResearchEffectiveness.mockResolvedValue(effectiveness)
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="evaluated-at-input"]').setValue('2026-09-20T16:00:00+08:00')
    await wrapper.get('[data-testid="start-date-input"]').setValue('2026-06-01')
    await wrapper.get('[data-testid="end-date-input"]').setValue('2026-09-20')
    await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchEffectiveness).toHaveBeenCalledWith({ evaluated_at: '2026-09-20T16:00:00+08:00', start_date: '2026-06-01', end_date: '2026-09-20' })
  })

  it('distinguishes successful empty and blocked-only effectiveness histories', async () => {
    mockSnapshot(); api.getSelectionResearchEffectiveness.mockResolvedValue({ ...effectiveness, snapshot_count: 0, empty_snapshot_count: 0, item_observation_count: 0, ranks: [], cutoffs: [], overall_horizons: [horizon(5), horizon(20), horizon(60)] })
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="evaluated-at-input"]').setValue('2026-09-20T16:00:00+08:00'); await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="effectiveness-empty"]').text()).toContain('没有持久化的选股研究快照')
    expect(wrapper.find('[data-testid="effectiveness-blocked"]').exists()).toBe(false)
    api.getSelectionResearchEffectiveness.mockResolvedValue({ ...effectiveness, snapshot_count: 1, empty_snapshot_count: 1, item_observation_count: 0, ranks: [], cutoffs: [], overall_horizons: [horizon(5), horizon(20), horizon(60)] })
    await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="effectiveness-blocked"]').text()).toContain('存在持久化快照')
    expect(wrapper.find('[data-testid="effectiveness-empty"]').exists()).toBe(false)
  })

  it('keeps snapshot visible when effectiveness fails and distinguishes empty states', async () => {
    mockSnapshot(); api.getSelectionResearchEffectiveness.mockRejectedValue(new Error('offline'))
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="evaluated-at-input"]').setValue('2026-09-20T16:00:00+08:00')
    await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('无法读取选股研究有效性')
    expect(wrapper.text()).toContain('600519.SH')
  })

  it('renders blocked snapshots and raw official blockers without result rows', async () => {
    mockSnapshot({
      ...snapshot, selection_ready: false, blockers: ['eligible_factor_input_coverage_incomplete'],
      diagnostics: { ...snapshot.diagnostics, factor_input_members: 0, scoreable_members: 0, returned_items: 0 }, items: [],
    })
    const wrapper = mountView(); await flushPromises()

    expect(wrapper.text()).toContain('已阻断')
    expect(wrapper.text()).toContain('eligible_factor_input_coverage_incomplete')
    expect(wrapper.findAll('tbody tr')).toHaveLength(0)
  })

  it('renders nested refresh failure provenance without treating it as no artifact', async () => {
    mockSnapshot({ ...snapshot, refresh_had_collection_failures: true })
    const wrapper = mountView(); await flushPromises()

    expect(wrapper.text()).toContain('官方结果已导出，但本次刷新包含嵌套采集失败。')
    expect(wrapper.text()).toContain('包含失败')
  })

  it('expands evidence and risk details from the persisted item', async () => {
    mockSnapshot()
    const wrapper = mountView(); await flushPromises()
    await wrapper.find('.el-table__expand-icon').trigger('click'); await flushPromises()

    expect(wrapper.text()).toContain('主要依据')
    expect(wrapper.text()).toContain('质量依据')
    expect(wrapper.text()).toContain('风险')
    expect(wrapper.text()).toContain('波动风险')
  })

  it('opens exact JSON and CSV artifact download URLs', async () => {
    mockSnapshot()
    api.selectionResearchDownloadUrl.mockImplementation((format: string) => `/api/selection/research/latest.${format}`)
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountView(); await flushPromises()

    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')

    expect(api.selectionResearchDownloadUrl).toHaveBeenNthCalledWith(1, 'json')
    expect(api.selectionResearchDownloadUrl).toHaveBeenNthCalledWith(2, 'csv')
    expect(open).toHaveBeenNthCalledWith(1, '/api/selection/research/latest.json', '_blank')
    expect(open).toHaveBeenNthCalledWith(2, '/api/selection/research/latest.csv', '_blank')
  })

  it('distinguishes an absent artifact from an API error and keeps disclosures visible', async () => {
    api.getSelectionResearchLatest.mockResolvedValue({ available: false, snapshot: null })
    const wrapper = mountView(); await flushPromises()
    expect(wrapper.text()).toContain('尚无官方导出快照')
    expect(wrapper.text()).not.toContain('无法读取已导出的选股研究快照')

    api.getSelectionResearchLatest.mockRejectedValue(new Error('offline'))
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('无法读取已导出的选股研究快照')

    mockSnapshot()
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('持久化的官方选股快照')
    expect(wrapper.text()).toContain('同日重新运行 selection daily 可以替换它')
    expect(wrapper.text()).toContain('confidence-adjusted score 仅供展示，不构成投资建议')
  })

  it('loads history only on explicit action and trims blank or full date filters', async () => {
    mockSnapshot(); api.getSelectionResearchHistory.mockResolvedValue(history([]))
    const wrapper = mountView(); await flushPromises()
    expect(api.getSelectionResearchLatest).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchHistory).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="history-start-date-input"]').setValue('')
    await wrapper.get('[data-testid="history-end-date-input"]').setValue('')
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchHistory).toHaveBeenLastCalledWith({})

    await wrapper.get('[data-testid="history-start-date-input"]').setValue(' 2026-06-01 ')
    await wrapper.get('[data-testid="history-end-date-input"]').setValue(' 2026-09-20 ')
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchHistory).toHaveBeenLastCalledWith({ start_date: '2026-06-01', end_date: '2026-09-20' })
  })

  it('sends open-ended history filters without date conversion', async () => {
    mockSnapshot(); api.getSelectionResearchHistory.mockResolvedValue(history([]))
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="history-start-date-input"]').setValue('2026-06-01')
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchHistory).toHaveBeenLastCalledWith({ start_date: '2026-06-01' })
    await wrapper.get('[data-testid="history-start-date-input"]').setValue('')
    await wrapper.get('[data-testid="history-end-date-input"]').setValue('2026-09-20')
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchHistory).toHaveBeenLastCalledWith({ end_date: '2026-09-20' })
  })

  it('renders history snapshots and their persisted items in API order', async () => {
    mockSnapshot()
    api.getSelectionResearchHistory.mockResolvedValue(history([
      historySnapshot('2026-09-16T16:00:00+08:00', { ...snapshot, items: [firstItem, secondItem] }),
      historySnapshot('2026-09-17T16:00:00+08:00'),
    ]))
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    const first = wrapper.get('[data-testid="history-snapshot-0"]')
    const second = wrapper.get('[data-testid="history-snapshot-1"]')
    expect(first.text()).toContain('2026-09-16')
    expect(second.text()).toContain('2026-09-17')
    expect(first.text().indexOf('600519.SH')).toBeLessThan(first.text().indexOf('000001.SZ'))
  })

  it('shows blocked history snapshots and raw blocker codes', async () => {
    mockSnapshot()
    api.getSelectionResearchHistory.mockResolvedValue(history([historySnapshot('2026-09-16T16:00:00+08:00', {
      ...snapshot, selection_ready: false, blockers: ['eligible_factor_input_coverage_incomplete'],
      diagnostics: { ...snapshot.diagnostics, returned_items: 0 }, items: [],
    })]))
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    const row = wrapper.get('[data-testid="history-snapshot-0"]')
    expect(row.text()).toContain('已阻断')
    expect(row.text()).toContain('eligible_factor_input_coverage_incomplete')
  })

  it('distinguishes an empty history from history API failure without clearing latest', async () => {
    mockSnapshot(); api.getSelectionResearchHistory.mockResolvedValue(history([]))
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('无法读取历史选股研究快照。')

    api.getSelectionResearchHistory.mockRejectedValue(new Error('offline'))
    await wrapper.get('[data-testid="load-history"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('无法读取历史选股研究快照。')
    expect(wrapper.text()).toContain('600519.SH')
  })
})
