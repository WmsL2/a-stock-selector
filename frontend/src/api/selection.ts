import client from './client'
import type { DailySelectionResponse, RealtimeSelectionResponse, SelectionResearchEffectivenessResponse, SelectionResearchLatestResponse } from './types'

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

export async function getSelectionResearchLatest(): Promise<SelectionResearchLatestResponse> {
  const response = await client.get<SelectionResearchLatestResponse>('/selection/research/latest')
  return response.data
}

export interface SelectionResearchEffectivenessParams {
  evaluated_at: string
  start_date?: string
  end_date?: string
}

export async function getSelectionResearchEffectiveness(
  params: SelectionResearchEffectivenessParams,
): Promise<SelectionResearchEffectivenessResponse> {
  const response = await client.get<SelectionResearchEffectivenessResponse>(
    '/selection/research/effectiveness',
    { params },
  )
  return response.data
}

export function selectionResearchDownloadUrl(format: 'json' | 'csv'): string {
  return `/api/selection/research/latest.${format}`
}
