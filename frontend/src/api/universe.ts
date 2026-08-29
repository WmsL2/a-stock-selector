import client from './client'
import type { UniverseStatusResponse } from './types'

export async function getUniverseStatus(): Promise<UniverseStatusResponse> {
  const response = await client.get<UniverseStatusResponse>('/universe/status')
  return response.data
}
