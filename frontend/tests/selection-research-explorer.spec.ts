import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getSelectionResearchItems: vi.fn(),
  getSelectionResearchCompare: vi.fn(),
  selectionResearchItemsDownloadUrl: vi.fn(),
}))
vi.mock('@/api/selection', () => api)

import SelectionResearchExplorer from '@/components/SelectionResearchExplorer.vue'

function mountExplorer() { return mount(SelectionResearchExplorer, { global: { plugins: [ElementPlus] } }) }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const result = {
  schema_version: 1, start_date: null, end_date: null, strategy_name: null, q: null, board: null,
  industry_code: null, max_rank: null, snapshot_count: 9, matching_snapshot_count: 7,
  item_observation_count: 4, observations: [],
}
const comparison = (marker: string) => ({
  previous_snapshot: { as_of: `previous-${marker}`, strategy_name: `strategy-previous-${marker}`, selection_ready: true, blockers: [], refresh_had_collection_failures: false, items: [] },
  current_snapshot: { as_of: `current-${marker}`, strategy_name: `strategy-current-${marker}`, selection_ready: true, blockers: [], refresh_had_collection_failures: false, items: [] },
  transition: { comparable: false, comparison_blockers: [], previous_item_count: 0, current_item_count: 0, retained_count: null, entered_count: null, exited_count: null, retention_rate: null, overlap_rate: null, movements: [] },
})

afterEach(() => { vi.resetAllMocks(); vi.restoreAllMocks() })

describe('SelectionResearchExplorer', () => {
  it('keeps filtered result and export params atomic across stale completion and failure', async () => {
    const first = deferred<typeof result>(); const second = deferred<typeof result>()
    api.getSelectionResearchItems.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    api.selectionResearchItemsDownloadUrl.mockReturnValue('/export')
    vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountExplorer()
    const state = (wrapper.vm.$ as unknown as { setupState: { loadItems: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="research-query-input"]').setValue('A'); void state.loadItems()
    await nextTick()
    await wrapper.get('[data-testid="research-query-input"]').setValue('B'); void state.loadItems()
    await nextTick()
    second.resolve({ ...result, snapshot_count: 202 }); await flushPromises()
    first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).toContain('202')
    expect(wrapper.text()).not.toContain('无法读取筛选后的选股项。')
    await wrapper.get('[data-testid="research-export-json"]').trigger('click')
    expect(api.selectionResearchItemsDownloadUrl).toHaveBeenCalledWith('json', { q: 'B' })
  })

  it('suppresses stale filtered-items success and keeps B export parameters', async () => {
    const first = deferred<typeof result>(); const second = deferred<typeof result>()
    api.getSelectionResearchItems.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    api.selectionResearchItemsDownloadUrl.mockReturnValue('/export'); vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadItems: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="research-query-input"]').setValue('A'); void state.loadItems(); await nextTick()
    await wrapper.get('[data-testid="research-query-input"]').setValue('B'); void state.loadItems(); await nextTick()
    second.resolve({ ...result, snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('202')
    first.resolve({ ...result, snapshot_count: 101 }); await flushPromises()
    expect(wrapper.text()).toContain('202'); expect(wrapper.text()).not.toContain('101')
    await wrapper.get('[data-testid="research-export-json"]').trigger('click')
    expect(api.selectionResearchItemsDownloadUrl).toHaveBeenCalledWith('json', { q: 'B' })
  })

  it('suppresses stale filtered-items rejection while B remains pending', async () => {
    const first = deferred<typeof result>(); const second = deferred<typeof result>()
    api.getSelectionResearchItems.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadItems: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="research-query-input"]').setValue('A'); void state.loadItems(); await nextTick()
    await wrapper.get('[data-testid="research-query-input"]').setValue('B'); void state.loadItems(); await nextTick()
    first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).not.toContain('无法读取筛选后的选股研究项。')
    expect(wrapper.get('[data-testid="load-research-items"]').classes()).toContain('is-loading')
    second.resolve({ ...result, snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('202'); expect(wrapper.text()).not.toContain('无法读取筛选后的选股研究项。')
  })

  it('preserves submitted A result and export parameters when submitted B fails', async () => {
    api.getSelectionResearchItems.mockResolvedValueOnce({ ...result, snapshot_count: 101 }).mockRejectedValueOnce(new Error('offline'))
    api.selectionResearchItemsDownloadUrl.mockReturnValue('/export'); vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountExplorer()
    await wrapper.get('[data-testid="research-query-input"]').setValue('A'); await wrapper.get('[data-testid="load-research-items"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('101')
    await wrapper.get('[data-testid="research-query-input"]').setValue('B'); await wrapper.get('[data-testid="load-research-items"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('101'); expect(wrapper.text()).toContain('无法读取筛选后的选股研究项。')
    expect(wrapper.find('[data-testid="research-items-preserved-result"]').exists()).toBe(true)
    await wrapper.get('[data-testid="research-export-json"]').trigger('click')
    expect(api.selectionResearchItemsDownloadUrl).toHaveBeenCalledWith('json', { q: 'A' })
  })

  it('keeps A result and export parameters while submitted B remains pending', async () => {
    const replacement = deferred<typeof result>()
    api.getSelectionResearchItems.mockResolvedValueOnce({ ...result, snapshot_count: 101 }).mockReturnValueOnce(replacement.promise)
    api.selectionResearchItemsDownloadUrl.mockReturnValue('/export'); vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountExplorer()
    await wrapper.get('[data-testid="research-query-input"]').setValue('A'); await wrapper.get('[data-testid="load-research-items"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="research-query-input"]').setValue('B'); await wrapper.get('[data-testid="load-research-items"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('101'); expect(wrapper.find('[data-testid="research-items-preserved-result"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="research-export-json"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="research-export-json"]').trigger('click')
    expect(api.selectionResearchItemsDownloadUrl).toHaveBeenCalledWith('json', { q: 'A' })
    replacement.resolve({ ...result, snapshot_count: 202 }); await flushPromises()
    expect(wrapper.text()).toContain('202')
  })

  it('omits blank maximum rank from submitted filters', async () => {
    api.getSelectionResearchItems.mockResolvedValue(result)
    const wrapper = mountExplorer(); await wrapper.get('[data-testid="load-research-items"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchItems).toHaveBeenCalledWith({})
    expect(api.getSelectionResearchItems.mock.calls[0][0]).not.toHaveProperty('max_rank')
  })
  it('does not load on mount and submits only explicitly normalized filters', async () => {
    const wrapper = mountExplorer()
    expect(api.getSelectionResearchItems).not.toHaveBeenCalled()
    api.getSelectionResearchItems.mockResolvedValue(result)
    await wrapper.get('[data-testid="research-query-input"]').setValue('  茅台  ')
    await wrapper.get('[data-testid="research-max-rank-input"]').find('input').setValue('7')
    await wrapper.get('[data-testid="load-research-items"]').trigger('click')
    await flushPromises()
    expect(api.getSelectionResearchItems).toHaveBeenCalledWith({ q: '茅台', max_rank: 7 })
    expect(wrapper.text()).toContain('9')
    expect(wrapper.text()).toContain('7')
    expect(wrapper.text()).toContain('4')
  })

  it('exports exactly the last successfully loaded parameters', async () => {
    api.getSelectionResearchItems.mockResolvedValue(result)
    api.selectionResearchItemsDownloadUrl.mockReturnValue('/api/selection/research/items.json?q=A')
    vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountExplorer()
    await wrapper.get('[data-testid="research-query-input"]').setValue('A')
    await wrapper.get('[data-testid="load-research-items"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="research-query-input"]').setValue('B')
    await wrapper.get('[data-testid="research-export-json"]').trigger('click')
    expect(api.selectionResearchItemsDownloadUrl).toHaveBeenCalledWith('json', { q: 'A' })
  })

  it('loads comparison only when requested with unchanged date strings', async () => {
    api.getSelectionResearchCompare.mockRejectedValue(new Error('not found'))
    const wrapper = mountExplorer()
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('2026-09-10')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-current-date-input"]').setValue('2026-09-20')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeUndefined()
    expect(api.getSelectionResearchCompare).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="load-research-comparison"]').trigger('click')
    await flushPromises()
    expect(api.getSelectionResearchCompare).toHaveBeenCalledWith({ previous_date: '2026-09-10', current_date: '2026-09-20' })
    expect(wrapper.text()).toContain('无法读取指定选股研究快照比较')
  })

  it('keeps comparison A visible while replacement B is pending', async () => {
    const replacement = deferred<ReturnType<typeof comparison>>()
    api.getSelectionResearchCompare.mockResolvedValueOnce(comparison('A')).mockReturnValueOnce(replacement.promise)
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadComparison: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-A'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-A')
    void state.loadComparison(); await flushPromises(); expect(wrapper.text()).toContain('current-A')
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-B'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-B')
    void state.loadComparison(); await flushPromises()
    expect(wrapper.text()).toContain('current-A'); expect(wrapper.find('[data-testid="comparison-preserved-result"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="load-research-comparison"]').classes()).toContain('is-loading')
    replacement.resolve(comparison('B')); await flushPromises(); expect(wrapper.text()).toContain('current-B')
  })

  it('preserves comparison A when replacement B fails', async () => {
    api.getSelectionResearchCompare.mockResolvedValueOnce(comparison('A')).mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadComparison: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-A'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-A')
    void state.loadComparison(); await flushPromises()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-B'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-B')
    void state.loadComparison(); await flushPromises()
    expect(wrapper.text()).toContain('current-A'); expect(wrapper.text()).toContain('无法读取指定选股研究快照比较')
    expect(wrapper.find('[data-testid="comparison-preserved-result"]').exists()).toBe(true)
  })

  it('suppresses stale comparison success after B resolves', async () => {
    const first = deferred<ReturnType<typeof comparison>>(); const second = deferred<ReturnType<typeof comparison>>()
    api.getSelectionResearchCompare.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadComparison: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-A'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-A'); void state.loadComparison(); await nextTick()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-B'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-B'); void state.loadComparison(); await nextTick()
    second.resolve(comparison('B')); await flushPromises(); expect(wrapper.text()).toContain('current-B')
    first.resolve(comparison('A')); await flushPromises()
    expect(wrapper.text()).toContain('current-B'); expect(wrapper.text()).not.toContain('current-A')
  })

  it('suppresses stale comparison rejection while B remains pending', async () => {
    const first = deferred<ReturnType<typeof comparison>>(); const second = deferred<ReturnType<typeof comparison>>()
    api.getSelectionResearchCompare.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountExplorer(); const state = (wrapper.vm.$ as unknown as { setupState: { loadComparison: () => Promise<void> } }).setupState
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-A'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-A'); void state.loadComparison(); await nextTick()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('previous-input-B'); await wrapper.get('[data-testid="compare-current-date-input"]').setValue('current-input-B'); void state.loadComparison(); await nextTick()
    first.reject(new Error('stale')); await flushPromises()
    expect(wrapper.text()).not.toContain('无法读取指定选股研究快照比较')
    expect(wrapper.get('[data-testid="load-research-comparison"]').classes()).toContain('is-loading')
    second.resolve(comparison('B')); await flushPromises()
    expect(wrapper.text()).toContain('current-B'); expect(wrapper.text()).not.toContain('无法读取指定选股研究快照比较')
  })

  it('gates whitespace-only comparison values while preserving raw submitted strings', async () => {
    api.getSelectionResearchCompare.mockRejectedValue(new Error('offline'))
    const wrapper = mountExplorer()
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('2026-09-10')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('')
    await wrapper.get('[data-testid="compare-current-date-input"]').setValue('2026-09-20')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('   ')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue('2026-09-10')
    await wrapper.get('[data-testid="compare-current-date-input"]').setValue('   ')
    expect(wrapper.get('[data-testid="load-research-comparison"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="compare-previous-date-input"]').setValue(' 2026-09-10 ')
    await wrapper.get('[data-testid="compare-current-date-input"]').setValue(' 2026-09-20 ')
    await wrapper.get('[data-testid="load-research-comparison"]').trigger('click'); await flushPromises()
    expect(api.getSelectionResearchCompare).toHaveBeenCalledWith({ previous_date: ' 2026-09-10 ', current_date: ' 2026-09-20 ' })
  })
})
