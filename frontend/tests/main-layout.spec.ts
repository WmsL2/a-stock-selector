import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getStorageStatus: vi.fn(),
}))
vi.mock('@/api/health', () => ({ getHealth: api.getHealth }))
vi.mock('@/api/storage', () => ({ getStorageStatus: api.getStorageStatus }))

import MainLayout from '@/layouts/MainLayout.vue'

function statusStorage() {
  return {
    instrument_rows: 0,
    daily_rows: 0,
    daily_symbols: 0,
    realtime_rows: 0,
    realtime_symbols: 0,
    realtime_snapshots: 0,
    latest_realtime_at: null,
    disk_usage_bytes: 0,
    storage_root: '',
    duckdb_path: '',
  }
}

async function mountLayout(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: MainLayout }],
  })
  await router.push(path)
  await router.isReady()
  return mount(MainLayout, { global: { plugins: [router, createPinia(), ElementPlus] } })
}

afterEach(() => vi.resetAllMocks())

describe('MainLayout API status and navigation', () => {
  it('checks status from a direct non-dashboard route and renders checking then online', async () => {
    let resolveHealth: (value: { status: string; application: string; version: string; storage: string }) => void
    const healthPromise = new Promise<{ status: string; application: string; version: string; storage: string }>((resolve) => { resolveHealth = resolve })
    api.getHealth.mockReturnValue(healthPromise)
    api.getStorageStatus.mockResolvedValue(statusStorage())
    const wrapper = await mountLayout('/stocks')
    expect(api.getHealth).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('API：检查中')
    resolveHealth!({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    await flushPromises()
    expect(wrapper.text()).toContain('API：在线')
  })

  it('renders offline after the first status check fails', async () => {
    api.getHealth.mockRejectedValue(new Error('offline'))
    api.getStorageStatus.mockResolvedValue(statusStorage())
    const wrapper = await mountLayout('/settings')
    await flushPromises()
    expect(wrapper.text()).toContain('API：离线')
  })

  it.each([
    ['/', '/'],
    ['/stocks', '/stocks'],
    ['/stocks/600519.SH', '/stocks'],
    ['/data-center', '/data-center'],
    ['/settings', '/settings'],
  ])('uses %s as route-aware active menu %s', async (path, activeMenu) => {
    api.getHealth.mockResolvedValue({ status: 'ok', application: 'a-stock-selector', version: '0.1.0', storage: 'ready' })
    api.getStorageStatus.mockResolvedValue(statusStorage())
    const wrapper = await mountLayout(path)
    expect(wrapper.findComponent({ name: 'ElMenu' }).props('defaultActive')).toBe(activeMenu)
  })
})
