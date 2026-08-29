import client from './client'
import type { HealthResponse } from './types'

export async function getHealth(): Promise<HealthResponse> {
  const response = await client.get<HealthResponse>('/health')
  return response.data
}
