import client from './client'
import type { DailySelectionResponse, RealtimeSelectionResponse, SelectionResearchComparisonResponse, SelectionResearchEffectivenessResponse, SelectionResearchHistoryResponse, SelectionResearchItemQueryResponse, SelectionResearchLatestResponse, SelectionResearchStabilityResponse } from './types'

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
export interface SelectionResearchItemsParams {
  start_date?: string
  end_date?: string
  strategy_name?: string
  q?: string
  board?: string
  industry_code?: string
  max_rank?: number
}
export interface SelectionResearchCompareParams {
  previous_date: string
  current_date: string
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

export async function getSelectionResearchItems(
  params: SelectionResearchItemsParams,
): Promise<SelectionResearchItemQueryResponse> {
  const response = await client.get<SelectionResearchItemQueryResponse>('/selection/research/items', { params })
  return response.data
}

export async function getSelectionResearchCompare(
  params: SelectionResearchCompareParams,
): Promise<SelectionResearchComparisonResponse> {
  const response = await client.get<SelectionResearchComparisonResponse>('/selection/research/compare', { params })
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

export function selectionResearchItemsDownloadUrl(
  format: 'json' | 'csv',
  params: SelectionResearchItemsParams,
): string {
  const search = new URLSearchParams()
  const keys: (keyof SelectionResearchItemsParams)[] = [
    'start_date', 'end_date', 'strategy_name', 'q', 'board', 'industry_code', 'max_rank',
  ]
  for (const key of keys) {
    const value = params[key]
    if (value !== undefined) search.set(key, String(value))
  }
  const suffix = search.toString()
  return `/api/selection/research/items.${format}${suffix ? `?${suffix}` : ''}`
}
