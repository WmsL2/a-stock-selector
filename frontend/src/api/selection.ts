import client from './client'
import type { DailySelectionResponse, RealtimeSelectionResponse } from './types'

export async function getDailySelection(): Promise<DailySelectionResponse> {
  const response = await client.get<DailySelectionResponse>('/selection/daily')
  return response.data
}

export async function getRealtimeSelection(): Promise<RealtimeSelectionResponse> {
  const response = await client.get<RealtimeSelectionResponse>('/selection/realtime', {
    timeout: 60_000,
  })
  return response.data
}
