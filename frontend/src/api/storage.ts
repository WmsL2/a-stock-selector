import client from './client'
import type { StorageStatusResponse } from './types'

export async function getStorageStatus(): Promise<StorageStatusResponse> {
  const response = await client.get<StorageStatusResponse>('/storage/status')
  return response.data
}
