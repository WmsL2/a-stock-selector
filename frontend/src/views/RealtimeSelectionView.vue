<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { getRealtimeStatus } from '@/api/realtime'
import type { RealtimeFreshness, RealtimeStatusResponse } from '@/api/types'
import { formatLocalTime } from '@/utils/format'

const status = ref<RealtimeStatusResponse | null>(null)
const loading = ref(true)
const loadFailed = ref(false)

const freshnessLabel = computed(() => {
  const labels: Record<RealtimeFreshness, string> = {
    fresh: '正常',
    warning: '警告',
    stale: '过期',
    unavailable: '暂无数据',
  }
  return status.value ? labels[status.value.freshness] : '读取中'
})

const infrastructureStatus = computed(() => {
  if (loadFailed.value) return '本地实时快照状态暂不可读。'
  if (!status.value) return '正在读取本地快照状态。'
  return `最近本地入库：${formatLocalTime(status.value.latest_ingested_at)}；已保存 ${status.value.stored_quotes} 条行情。`
})

async function loadStatus(): Promise<void> {
  loading.value = true
  loadFailed.value = false
  try {
    status.value = await getRealtimeStatus()
  } catch {
    status.value = null
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadStatus()
})
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">REALTIME SELECTION</p><h1>实时选股</h1></div></section>
  <el-skeleton v-if="loading" :rows="4" animated />
  <el-alert v-else-if="loadFailed" title="本地实时快照状态暂不可读。" type="warning" show-icon :closable="false" />
  <section v-else-if="status" class="panel">
    <h2>Realtime Foundation Status</h2>
    <el-descriptions :column="2" border>
      <el-descriptions-item label="Source">{{ status.source ?? 'unavailable' }}</el-descriptions-item>
      <el-descriptions-item label="Latest ingest">{{ formatLocalTime(status.latest_ingested_at) }}</el-descriptions-item>
      <el-descriptions-item label="Stored quotes">{{ status.stored_quotes }}</el-descriptions-item>
      <el-descriptions-item label="Source timestamps">{{ status.source_timestamp_available_quotes }}</el-descriptions-item>
      <el-descriptions-item label="Freshness">{{ freshnessLabel }}</el-descriptions-item>
      <el-descriptions-item label="Age">{{ status.age_seconds === null ? 'unavailable' : `${status.age_seconds.toFixed(1)}s` }}</el-descriptions-item>
      <el-descriptions-item label="Ranking gate">{{ status.ranking_allowed ? '允许（仅新鲜度门槛）' : '不允许（仅新鲜度门槛）' }}</el-descriptions-item>
      <el-descriptions-item label="Snapshot scope">{{ status.snapshot_scope }}</el-descriptions-item>
    </el-descriptions>
    <el-alert title="状态仅来自本地选择性持久化快照；不会触发网络拉取，也不代表全市场覆盖或交易所行情有效。" type="info" :closable="false" />
  </section>
  <section class="panel"><EmptyState title="实时选股引擎尚未实现" :description="`IntradayScore 核心评分已实现，但尚未接入实时选股 API/UI；Realtime Scanner 与 RealTimeScore 尚未实现。${infrastructureStatus}`" /></section>
</template>
