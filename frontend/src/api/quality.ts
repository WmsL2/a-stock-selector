import client from './client'
import type { QualityStatusResponse } from './types'

export async function getQualityStatus(): Promise<QualityStatusResponse> {
  const response = await client.get<QualityStatusResponse>('/quality/status')
  return response.data
}
