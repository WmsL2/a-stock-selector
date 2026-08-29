import client from './client'
import type {
  DailyBarsResponse,
  FinancialRecordsResponse,
  IndustryRecordsResponse,
  InstrumentListResponse,
  InstrumentResponse,
  RealtimeLookupResponse,
  ValuationLookupResponse,
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

export async function getFinancialRecords(symbol: string): Promise<FinancialRecordsResponse> {
  const response = await client.get<FinancialRecordsResponse>(`/instruments/${encodeURIComponent(symbol)}/fundamentals`)
  return response.data
}

export async function getValuation(symbol: string): Promise<ValuationLookupResponse> {
  const response = await client.get<ValuationLookupResponse>(`/instruments/${encodeURIComponent(symbol)}/valuation`)
  return response.data
}

export async function getIndustryRecords(symbol: string): Promise<IndustryRecordsResponse> {
  const response = await client.get<IndustryRecordsResponse>(`/instruments/${encodeURIComponent(symbol)}/industry`)
  return response.data
}
