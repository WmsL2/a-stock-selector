import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listInstruments: vi.fn() }))
vi.mock('@/api/instruments', () => ({ listInstruments: api.listInstruments }))

import InstrumentsView from '@/views/InstrumentsView.vue'

describe('InstrumentsView', () => {
  it('renders local instruments and sends server-side search parameters', async () => {
    api.listInstruments.mockResolvedValue({ total: 1, limit: 50, offset: 0, items: [{ symbol: '600519.SH', name: '测试茅台', exchange: 'SH', board: 'sh_main', listing_date: '2001-08-27', delisting_date: null, status: 'active' }] })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/stocks', component: InstrumentsView }] })
    await router.push('/stocks')
    await router.isReady()
    const wrapper = mount(InstrumentsView, { global: { plugins: [router, createPinia(), ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('测试茅台')
    const input = wrapper.find('input')
    await input.setValue('茅台')
    await wrapper.get('button.el-button--primary').trigger('click')
    await flushPromises()
    expect(api.listInstruments).toHaveBeenLastCalledWith({ q: '茅台', limit: 50, offset: 0 })
  })
})
