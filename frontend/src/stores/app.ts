import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getHealth } from '@/api/health'
import { getStorageStatus } from '@/api/storage'
import type { HealthResponse, StorageStatusResponse } from '@/api/types'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const health = ref<HealthResponse | null>(null)
  const storage = ref<StorageStatusResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const apiOnline = computed(() => health.value?.status === 'ok')

  async function refreshStatus(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [healthResponse, storageResponse] = await Promise.all([
        getHealth(),
        getStorageStatus(),
      ])
      health.value = healthResponse
      storage.value = storageResponse
    } catch {
      health.value = null
      storage.value = null
      error.value = '无法连接本地 API，请确认 FastAPI 服务已在 127.0.0.1:8000 启动。'
    } finally {
      loading.value = false
    }
  }

  return {
    sidebarCollapsed,
    health,
    storage,
    loading,
    error,
    apiOnline,
    refreshStatus,
  }
})
