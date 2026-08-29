import { describe, expect, it, vi } from 'vitest'

import client from '@/api/client'
import { getDailyBars, getInstrument, getLatestRealtime, listInstruments } from '@/api/instruments'
import { getUniverseStatus } from '@/api/universe'

describe('local API client', () => {
  it('uses the relative API base URL', () => {
    expect(client.defaults.baseURL).toBe('/api')
    expect(client.defaults.timeout).toBe(10_000)
  })

  it('sends list, encoded detail, daily, realtime, and universe requests through the client', async () => {
    const get = vi.spyOn(client, 'get').mockResolvedValue({ data: {} } as never)
    await listInstruments({ q: '茅台', limit: 50, offset: 0 })
    await getInstrument('600519.SH/test')
    await getDailyBars('600519.SH', { start_date: '2026-08-01', limit: 200 })
    await getLatestRealtime('600519.SH')
    await getUniverseStatus()
    expect(get).toHaveBeenNthCalledWith(1, '/instruments', {
      params: { q: '茅台', limit: 50, offset: 0 },
    })
    expect(get).toHaveBeenNthCalledWith(2, '/instruments/600519.SH%2Ftest')
    expect(get).toHaveBeenNthCalledWith(3, '/instruments/600519.SH/daily', {
      params: { start_date: '2026-08-01', limit: 200 },
    })
    expect(get).toHaveBeenNthCalledWith(4, '/instruments/600519.SH/realtime')
    expect(get).toHaveBeenNthCalledWith(5, '/universe/status')
  })
})
