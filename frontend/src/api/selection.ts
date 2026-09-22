import client from './client'
import type { DailySelectionResponse, RealtimeSelectionResponse, SelectionResearchEffectivenessResponse, SelectionResearchHistoryResponse, SelectionResearchLatestResponse, SelectionResearchStabilityResponse } from './types'

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
export interface SelectionResearchHistoryParams {
  start_date?: string
  end_date?: string
}

export interface SelectionResearchStabilityParams {
  start_date?: string
  end_date?: string
}

export async function getSelectionResearchHistory(
  params: SelectionResearchHistoryParams,
): Promise<SelectionResearchHistoryResponse> {
  const response = await client.get<SelectionResearchHistoryResponse>('/selection/research/history', { params })
  return response.data
}

export async function getSelectionResearchStability(
  params: SelectionResearchStabilityParams,
): Promise<SelectionResearchStabilityResponse> {
  const response = await client.get<SelectionResearchStabilityResponse>('/selection/research/stability', { params })
  return response.data
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
