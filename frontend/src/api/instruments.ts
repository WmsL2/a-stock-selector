import client from './client'
import type {
  DailyBarsResponse,
  InstrumentListResponse,
  InstrumentResponse,
  RealtimeLookupResponse,
} from './types'

export interface InstrumentListParams {
  q?: string
  limit?: number
  offset?: number
}

export interface DailyBarsParams {
  start_date?: string
  end_date?: string
  limit?: number
}

export async function listInstruments(
  params: InstrumentListParams,
): Promise<InstrumentListResponse> {
  const response = await client.get<InstrumentListResponse>('/instruments', { params })
  return response.data
}

export async function getInstrument(symbol: string): Promise<InstrumentResponse> {
  const response = await client.get<InstrumentResponse>(
    `/instruments/${encodeURIComponent(symbol)}`,
  )
  return response.data
}

export async function getDailyBars(
  symbol: string,
  params: DailyBarsParams = {},
): Promise<DailyBarsResponse> {
  const response = await client.get<DailyBarsResponse>(
    `/instruments/${encodeURIComponent(symbol)}/daily`,
    { params },
  )
  return response.data
}

export async function getLatestRealtime(
  symbol: string,
): Promise<RealtimeLookupResponse> {
  const response = await client.get<RealtimeLookupResponse>(
    `/instruments/${encodeURIComponent(symbol)}/realtime`,
  )
  return response.data
}
