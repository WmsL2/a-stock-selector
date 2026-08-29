import client from './client'
import type { DailyStatusResponse } from './types'

export async function getDailyStatus(): Promise<DailyStatusResponse> {
  const response = await client.get<DailyStatusResponse>('/daily/status')
  return response.data
}
