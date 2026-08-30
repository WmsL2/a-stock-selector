import client from './client'
import type { DailySelectionResponse } from './types'

export async function getDailySelection(): Promise<DailySelectionResponse> {
  const response = await client.get<DailySelectionResponse>('/selection/daily')
  return response.data
}
