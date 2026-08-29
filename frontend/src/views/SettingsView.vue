<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getPublicConfig } from '@/api/config'
import type { PublicConfigResponse } from '@/api/types'

const config = ref<PublicConfigResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function loadConfig(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    config.value = await getPublicConfig()
  } catch {
    error.value = '无法读取后端公开配置。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadConfig())
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">READ-ONLY BACKEND CONFIG</p><h1>系统设置</h1><p>仅展示后端明确允许公开的只读配置。</p></div></section>
  <el-skeleton v-if="loading" :rows="8" animated />
  <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />
  <template v-else-if="config">
    <section class="panel"><h2>应用与实时配置</h2><el-descriptions :column="2" border><el-descriptions-item label="时区">{{ config.app.timezone }}</el-descriptions-item><el-descriptions-item label="Realtime enabled">{{ config.realtime.enabled ? '启用' : '停用' }}</el-descriptions-item><el-descriptions-item label="Snapshot interval">{{ config.realtime.snapshot_interval_seconds }} 秒</el-descriptions-item><el-descriptions-item label="Top N">{{ config.selection.top_n }}</el-descriptions-item><el-descriptions-item label="Watchlist N">{{ config.selection.watchlist_n }}</el-descriptions-item></el-descriptions></section>
    <section class="panel"><h2>因子权重</h2><el-table :data="Object.entries(config.factors)"><el-table-column label="因子"><template #default="scope">{{ scope.row[0] }}</template></el-table-column><el-table-column label="启用"><template #default="scope">{{ scope.row[1].enabled ? '是' : '否' }}</template></el-table-column><el-table-column label="权重"><template #default="scope">{{ (scope.row[1].weight * 100).toFixed(0) }}%</template></el-table-column></el-table></section>
  </template>
</template>
