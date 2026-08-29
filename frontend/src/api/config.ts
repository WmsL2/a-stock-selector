import client from './client'
import type { PublicConfigResponse } from './types'

export async function getPublicConfig(): Promise<PublicConfigResponse> {
  const response = await client.get<PublicConfigResponse>('/config/public')
  return response.data
}
