import client from './client'
import type { FundamentalsStatusResponse } from './types'

export async function getFundamentalsStatus(): Promise<FundamentalsStatusResponse> {
  const response = await client.get<FundamentalsStatusResponse>('/fundamentals/status')
  return response.data
}
