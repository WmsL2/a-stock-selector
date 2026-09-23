import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SelectionResearchEffectivenessResponse, SelectionResearchHistoryResponse, SelectionResearchSnapshotResponse, SelectionResearchStabilityResponse } from '@/api/types'

const api = vi.hoisted(() => ({
  getDailySelection: vi.fn(),
  getSelectionResearchEffectiveness: vi.fn(),
  getSelectionResearchHistory: vi.fn(),
  getSelectionResearchItems: vi.fn(),
  getSelectionResearchCompare: vi.fn(),
  getSelectionResearchLatest: vi.fn(),
  getSelectionResearchStability: vi.fn(),
  selectionResearchDownloadUrl: vi.fn(),
  selectionResearchItemsDownloadUrl: vi.fn(),
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
const stability: SelectionResearchStabilityResponse = {
  start_date: null, end_date: null, snapshot_count: 9, transition_count: 2, comparable_transition_count: 1,
  transitions: [
    { previous_as_of: '2026-09-17T16:00:00+08:00', current_as_of: '2026-09-20T16:00:00+08:00', previous_strategy_name: 'official', current_strategy_name: 'official', previous_selection_ready: true, current_selection_ready: true, previous_blockers: [], current_blockers: [], comparable: true, comparison_blockers: [], previous_item_count: 4, current_item_count: 4, retained_count: 3, entered_count: 1, exited_count: 1, retention_rate: 0.75, overlap_rate: 0.6, movements: [{ status: 'exited', symbol: 'Z', name: 'Zed', previous_rank: 2, current_rank: null, rank_change: null }, { status: 'retained', symbol: 'A', name: 'Alpha', previous_rank: 5, current_rank: 2, rank_change: 3 }, { status: 'retained', symbol: 'B', name: 'Beta', previous_rank: 2, current_rank: 5, rank_change: -3 }, { status: 'retained', symbol: 'C', name: 'Gamma', previous_rank: 4, current_rank: 4, rank_change: 0 }] },
    { previous_as_of: '2026-09-15T16:00:00+08:00', current_as_of: '2026-09-16T16:00:00+08:00', previous_strategy_name: 'official', current_strategy_name: 'other', previous_selection_ready: false, current_selection_ready: true, previous_blockers: ['eligible_factor_input_coverage_incomplete'], current_blockers: [], comparable: false, comparison_blockers: ['previous_selection_blocked', 'strategy_changed'], previous_item_count: 0, current_item_count: 2, retained_count: null, entered_count: null, exited_count: null, retention_rate: null, overlap_rate: null, movements: [] },
  ],
}

function mountView() { return mount(SelectionResearchView, { global: { plugins: [ElementPlus] } }) }
function mockSnapshot(value: SelectionResearchSnapshotResponse = snapshot) {
  api.getSelectionResearchLatest.mockResolvedValue({ available: true, snapshot: value })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

afterEach(() => { vi.resetAllMocks(); vi.restoreAllMocks() })

describe('SelectionResearchView', () => {
  it('keeps latest snapshot B after stale latest completion and rejection', async () => {
    const first = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>()
    const second = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>()
    api.getSelectionResearchLatest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView()
    await wrapper.get('button').trigger('click')
    second.resolve({ available: true, snapshot: { ...snapshot, as_of: '2026-09-22T16:00:00+08:00', strategy_name: 'B' } })
    await flushPromises(); expect(wrapper.text()).toContain('2026-09-22')
    first.reject(new Error('stale'))
    await flushPromises()
    expect(wrapper.text()).toContain('2026-09-22')
    expect(wrapper.text()).not.toContain('无法读取已导出的选股研究快照。')
  })

  it('suppresses stale latest success after newer latest success', async () => {
    const first = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>(); const second = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>()
    api.getSelectionResearchLatest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await wrapper.get('button').trigger('click')
    second.resolve({ available: true, snapshot: { ...snapshot, as_of: '2026-09-22T16:00:00+08:00' } }); await flushPromises()
    first.resolve({ available: true, snapshot: { ...snapshot, as_of: '2026-09-21T16:00:00+08:00' } }); await flushPromises()
    expect(wrapper.text()).toContain('2026-09-22'); expect(wrapper.text()).not.toContain('2026-09-21')
  })

  it('suppresses stale latest rejection while newer latest is pending', async () => {
    const first = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>(); const second = deferred<{ available: boolean; snapshot: SelectionResearchSnapshotResponse | null }>()
    api.getSelectionResearchLatest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await wrapper.get('button').trigger('click'); first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(true); expect(wrapper.text()).not.toContain('无法读取已导出的选股研究快照。')
    second.resolve({ available: true, snapshot: { ...snapshot, as_of: '2026-09-22T16:00:00+08:00' } }); await flushPromises(); expect(wrapper.text()).toContain('2026-09-22')
  })

  it('preserves successful effectiveness, history, and stability reports on replacement failure', async () => {
    mockSnapshot(); api.getSelectionResearchEffectiveness.mockResolvedValue(effectiveness); api.getSelectionResearchHistory.mockResolvedValue(history([historySnapshot('2026-09-16T16:00:00+08:00')])); api.getSelectionResearchStability.mockResolvedValue(stability)
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="evaluated-at-input"]').setValue('2026-09-20T16:00:00+08:00')
    await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await wrapper.get('[data-testid="load-history"]').trigger('click'); await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    api.getSelectionResearchEffectiveness.mockRejectedValue(new Error('offline')); api.getSelectionResearchHistory.mockRejectedValue(new Error('offline')); api.getSelectionResearchStability.mockRejectedValue(new Error('offline'))
    await wrapper.get('[data-testid="load-effectiveness"]').trigger('click'); await wrapper.get('[data-testid="load-history"]').trigger('click'); await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-testid="effectiveness-preserved-result"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="history-preserved-result"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stability-preserved-result"]').exists()).toBe(true)
  })

  it('suppresses stale effectiveness success after B resolves', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchEffectivenessResponse>(); const second = deferred<SelectionResearchEffectivenessResponse>()
    api.getSelectionResearchEffectiveness.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); await wrapper.get('[data-testid="evaluated-at-input"]').setValue('x')
    const state = (wrapper.vm.$ as unknown as { setupState: { loadEffectiveness: () => Promise<void> } }).setupState
    void state.loadEffectiveness(); void state.loadEffectiveness(); second.resolve({ ...effectiveness, evaluated_at: 'B-2026', snapshot_count: 202 }); await flushPromises()
    first.resolve({ ...effectiveness, evaluated_at: 'A-2026', snapshot_count: 101 }); await flushPromises()
    expect(wrapper.text()).toContain('B-2026'); expect(wrapper.text()).not.toContain('A-2026')
  })

  it('suppresses stale effectiveness rejection while newer request is pending', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchEffectivenessResponse>(); const second = deferred<SelectionResearchEffectivenessResponse>()
    api.getSelectionResearchEffectiveness.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); await wrapper.get('[data-testid="evaluated-at-input"]').setValue('x')
    const state = (wrapper.vm.$ as unknown as { setupState: { loadEffectiveness: () => Promise<void> } }).setupState
    void state.loadEffectiveness(); void state.loadEffectiveness(); first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).not.toContain('无法读取选股研究有效性')
    expect(wrapper.get('[data-testid="load-effectiveness"]').classes()).toContain('is-loading')
    second.resolve({ ...effectiveness, evaluated_at: 'B-effectiveness', snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('B-effectiveness'); expect(wrapper.text()).not.toContain('无法读取选股研究有效性')
  })

  it('suppresses stale history success after B resolves', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchHistoryResponse>(); const second = deferred<SelectionResearchHistoryResponse>()
    api.getSelectionResearchHistory.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); const state = (wrapper.vm.$ as unknown as { setupState: { loadHistory: () => Promise<void> } }).setupState
    void state.loadHistory(); void state.loadHistory(); second.resolve(history([historySnapshot('B-2026')])); await flushPromises()
    first.resolve(history([historySnapshot('A-2026')])); await flushPromises()
    expect(wrapper.text()).toContain('B-2026'); expect(wrapper.text()).not.toContain('A-2026')
  })

  it('suppresses stale history rejection while newer request is pending', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchHistoryResponse>(); const second = deferred<SelectionResearchHistoryResponse>()
    api.getSelectionResearchHistory.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); const state = (wrapper.vm.$ as unknown as { setupState: { loadHistory: () => Promise<void> } }).setupState
    void state.loadHistory(); void state.loadHistory(); first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).not.toContain('无法读取历史选股研究快照。')
    expect(wrapper.get('[data-testid="load-history"]').classes()).toContain('is-loading')
    second.resolve(history([historySnapshot('B-history')])); await flushPromises()
    expect(wrapper.text()).toContain('B-history'); expect(wrapper.text()).not.toContain('无法读取历史选股研究快照。')
  })

  it('suppresses stale stability success after B resolves', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchStabilityResponse>(); const second = deferred<SelectionResearchStabilityResponse>()
    api.getSelectionResearchStability.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); const state = (wrapper.vm.$ as unknown as { setupState: { loadStability: () => Promise<void> } }).setupState
    void state.loadStability(); void state.loadStability(); second.resolve({ ...stability, snapshot_count: 202 }); await flushPromises()
    first.resolve({ ...stability, snapshot_count: 101 }); await flushPromises()
    expect(wrapper.text()).toContain('202'); expect(wrapper.text()).not.toContain('101')
  })

  it('suppresses stale stability rejection while newer request is pending', async () => {
    mockSnapshot(); const first = deferred<SelectionResearchStabilityResponse>(); const second = deferred<SelectionResearchStabilityResponse>()
    api.getSelectionResearchStability.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountView(); await flushPromises(); const state = (wrapper.vm.$ as unknown as { setupState: { loadStability: () => Promise<void> } }).setupState
    void state.loadStability(); void state.loadStability(); first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).not.toContain('无法读取选股稳定性分析。')
    expect(wrapper.get('[data-testid="load-stability"]').classes()).toContain('is-loading')
    second.resolve({ ...stability, snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('202'); expect(wrapper.text()).not.toContain('无法读取选股稳定性分析。')
  })
  it('does not present the no-artifact empty state while the initial request is pending', async () => {
    api.getSelectionResearchLatest.mockReturnValue(new Promise(() => undefined))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).not.toContain('尚无官方导出快照')
    expect(wrapper.get('[role="status"]').text()).toContain('正在读取已导出的研究快照')
  })

  it('uses only the persisted research API and retains exact official item order', async () => {
    api.getDailySelection.mockImplementation(() => { throw new Error('daily API must not be called') })
    mockSnapshot()
    const wrapper = mountView(); await flushPromises()

    const text = wrapper.text()
    expect(api.getDailySelection).not.toHaveBeenCalled()
    expect(api.getSelectionResearchEffectiveness).not.toHaveBeenCalled()
    expect(api.getSelectionResearchHistory).not.toHaveBeenCalled()
    expect(api.getSelectionResearchStability).not.toHaveBeenCalled()
    expect(api.getSelectionResearchItems).not.toHaveBeenCalled()
    expect(api.getSelectionResearchCompare).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="research-explorer"]').exists()).toBe(true)
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

  it('expands the shared explainability presentation from the latest persisted item', async () => {
    mockSnapshot()
    const wrapper = mountView(); await flushPromises()
    await wrapper.find('.el-table__expand-icon').trigger('click'); await flushPromises()

    expect(wrapper.find('[data-testid="selection-item-explainability"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('五因子评分')
    expect(wrapper.text()).toContain('quality')
    expect(wrapper.text()).toContain('质量依据')
    expect(wrapper.text()).toContain('volatility')
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
    expect(api.getSelectionResearchLatest).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchHistory).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchEffectiveness).not.toHaveBeenCalled()
    await first.find('.el-table__expand-icon').trigger('click'); await flushPromises()
    expect(first.find('[data-testid="selection-item-explainability"]').exists()).toBe(true)
    expect(first.text()).toContain('quality')
    expect(first.text()).toContain('volatility')
    expect(api.getSelectionResearchLatest).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchHistory).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchEffectiveness).not.toHaveBeenCalled()
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
    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('无法读取历史选股研究快照。')
    expect(wrapper.find('[data-testid="history-preserved-result"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('600519.SH')
  })

  it('loads stability only explicitly and sends trimmed date filters without conversion', async () => {
    mockSnapshot(); api.getSelectionResearchStability.mockResolvedValue(stability)
    const wrapper = mountView(); await flushPromises()
    expect(api.getSelectionResearchStability).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="stability-start-date-input"]').setValue('')
    await wrapper.get('[data-testid="stability-end-date-input"]').setValue('')
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchStability).toHaveBeenLastCalledWith({})
    await wrapper.get('[data-testid="stability-start-date-input"]').setValue(' 2026-06-01 ')
    await wrapper.get('[data-testid="stability-end-date-input"]').setValue(' 2026-09-20 ')
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchStability).toHaveBeenLastCalledWith({ start_date: '2026-06-01', end_date: '2026-09-20' })
    await wrapper.get('[data-testid="stability-end-date-input"]').setValue('')
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchStability).toHaveBeenLastCalledWith({ start_date: '2026-06-01' })
    await wrapper.get('[data-testid="stability-start-date-input"]').setValue('')
    await wrapper.get('[data-testid="stability-end-date-input"]').setValue('2026-09-20')
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchStability).toHaveBeenLastCalledWith({ end_date: '2026-09-20' })
  })

  it('renders API stability order, supplied counts, rank changes, and unavailable facts', async () => {
    mockSnapshot(); api.getSelectionResearchStability.mockResolvedValue(stability)
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    const first = wrapper.get('[data-testid="stability-transition-0"]')
    const second = wrapper.get('[data-testid="stability-transition-1"]')
    expect(wrapper.text()).toContain('9')
    expect(wrapper.text()).toContain('2')
    expect(first.text().indexOf('Z')).toBeLessThan(first.text().indexOf('A'))
    expect(first.text()).toContain('+3')
    expect(first.text()).toContain('-3')
    expect(first.text()).toContain('0')
    expect(first.text()).toContain('—')
    expect(second.text()).toContain('previous_selection_blocked')
    expect(second.text()).toContain('strategy_changed')
    expect(second.text()).toContain('eligible_factor_input_coverage_incomplete')
    expect(second.find('[data-testid="stability-unavailable"]').exists()).toBe(true)
    expect(api.getSelectionResearchLatest).toHaveBeenCalledTimes(1)
    expect(api.getSelectionResearchHistory).not.toHaveBeenCalled()
    expect(api.getSelectionResearchEffectiveness).not.toHaveBeenCalled()
  })

  it('keeps the successful stability result visible while its replacement is pending', async () => {
    mockSnapshot(); const replacement = deferred<SelectionResearchStabilityResponse>()
    api.getSelectionResearchStability.mockResolvedValueOnce(stability).mockReturnValueOnce(replacement.promise)
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('9')
    const state = (wrapper.vm.$ as unknown as { setupState: { loadStability: () => Promise<void> } }).setupState
    void state.loadStability(); await flushPromises()
    expect(wrapper.text()).toContain('9')
    expect(wrapper.find('[data-testid="stability-preserved-result"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="load-stability"]').classes()).toContain('is-loading')
    replacement.resolve({ ...stability, snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('202')
  })

  it('distinguishes stability empty states and preserves latest snapshot on failure', async () => {
    mockSnapshot()
    api.getSelectionResearchStability.mockResolvedValue({ ...stability, snapshot_count: 0, transition_count: 0, comparable_transition_count: 0, transitions: [] })
    const wrapper = mountView(); await flushPromises()
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-testid="stability-empty"]').exists()).toBe(true)
    api.getSelectionResearchStability.mockResolvedValue({ ...stability, snapshot_count: 1, transition_count: 0, comparable_transition_count: 0, transitions: [] })
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-testid="stability-single-snapshot"]').exists()).toBe(true)
    api.getSelectionResearchStability.mockRejectedValue(new Error('offline'))
    await wrapper.get('[data-testid="load-stability"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('无法读取选股稳定性分析。')
    expect(wrapper.text()).toContain('600519.SH')
  })
})
