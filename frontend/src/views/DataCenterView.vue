<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'

import { useAppStore } from '@/stores/app'
import { formatBytes, formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { error, loading, storage } = storeToRefs(appStore)

onMounted(() => {
  if (!storage.value) {
    void appStore.refreshStatus()
  }
})
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">LOCAL DATA COVERAGE</p><h1>数据中心</h1></div></section>
  <el-alert title="详细行情采用选择性持久化，详细数据股票数不等于全市场股票数。" type="info" :closable="false" />
  <el-skeleton v-if="loading && !storage" :rows="8" animated />
  <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />
  <el-descriptions v-else-if="storage" :column="2" border class="panel data-descriptions">
    <el-descriptions-item label="Storage root">{{ storage.storage_root }}</el-descriptions-item>
    <el-descriptions-item label="DuckDB path">{{ storage.duckdb_path }}</el-descriptions-item>
    <el-descriptions-item label="Instrument universe">{{ storage.instrument_rows }}</el-descriptions-item>
    <el-descriptions-item label="Daily stored symbols">{{ storage.daily_symbols }}</el-descriptions-item>
    <el-descriptions-item label="Daily rows">{{ storage.daily_rows }}</el-descriptions-item>
    <el-descriptions-item label="Realtime stored symbols">{{ storage.realtime_symbols }}</el-descriptions-item>
    <el-descriptions-item label="Realtime snapshots">{{ storage.realtime_snapshots }}</el-descriptions-item>
    <el-descriptions-item label="Realtime rows">{{ storage.realtime_rows }}</el-descriptions-item>
    <el-descriptions-item label="Latest realtime ingestion">{{ formatLocalTime(storage.latest_realtime_at) }}</el-descriptions-item>
    <el-descriptions-item label="Disk usage">{{ formatBytes(storage.disk_usage_bytes) }}</el-descriptions-item>
  </el-descriptions>
</template>
