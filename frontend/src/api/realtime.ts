import client from './client'
import type { RealtimeStatusResponse } from './types'

/** Read local realtime freshness only; this endpoint never initiates a capture. */
export async function getRealtimeStatus(): Promise<RealtimeStatusResponse> {
  const response = await client.get<RealtimeStatusResponse>('/realtime/status')
  return response.data
}
