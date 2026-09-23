import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getSelectionResearchItems: vi.fn(),
  getSelectionResearchCompare: vi.fn(),
  selectionResearchItemsDownloadUrl: vi.fn(),
}))
vi.mock('@/api/selection', () => api)

import SelectionResearchExplorer from '@/components/SelectionResearchExplorer.vue'

function mountExplorer() { return mount(SelectionResearchExplorer, { global: { plugins: [ElementPlus] } }) }

const result = {
  schema_version: 1, start_date: null, end_date: null, strategy_name: null, q: null, board: null,
  industry_code: null, max_rank: null, snapshot_count: 9, matching_snapshot_count: 7,
  item_observation_count: 4, observations: [],
}

afterEach(() => { vi.resetAllMocks(); vi.restoreAllMocks() })

describe('SelectionResearchExplorer', () => {
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
})
