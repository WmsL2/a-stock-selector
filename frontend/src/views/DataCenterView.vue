<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useAppStore } from '@/stores/app'
import { getUniverseStatus } from '@/api/universe'
import type { UniverseStatusResponse } from '@/api/types'
import { formatBytes, formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { error, loading, storage } = storeToRefs(appStore)
const universe = ref<UniverseStatusResponse | null>(null)
const universeError = ref(false)

async function loadUniverseStatus(): Promise<void> {
  universeError.value = false
  try {
    universe.value = await getUniverseStatus()
  } catch {
    universe.value = null
    universeError.value = true
  }
}

onMounted(() => {
  appStore.ensureStatus()
  void loadUniverseStatus()
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
  <section v-if="universe" class="panel">
    <h2>结构股票池</h2>
    <el-descriptions :column="2" border>
      <el-descriptions-item label="As of">{{ universe.as_of }}</el-descriptions-item>
      <el-descriptions-item label="Input">{{ universe.input_instruments }}</el-descriptions-item>
      <el-descriptions-item label="Included">{{ universe.included_instruments }}</el-descriptions-item>
      <el-descriptions-item label="Excluded">{{ universe.excluded_instruments }}</el-descriptions-item>
      <el-descriptions-item label="SH Main">{{ universe.boards.sh_main }}</el-descriptions-item>
      <el-descriptions-item label="SZ Main">{{ universe.boards.sz_main }}</el-descriptions-item>
      <el-descriptions-item label="ChiNext">{{ universe.boards.chinext }}</el-descriptions-item>
      <el-descriptions-item label="STAR">{{ universe.boards.star }}</el-descriptions-item>
      <el-descriptions-item label="BSE">{{ universe.boards.bse }}</el-descriptions-item>
    </el-descriptions>
    <el-alert v-if="!universe.historical_survivorship_safe" title="当前股票池基于当前本地 Instrument Master，不能直接作为历史回测的无生存者偏差证券样本。" type="warning" :closable="false" />
    <el-alert v-if="!universe.risk_filters_applied" title="ST、停牌、退市期等日期化风险过滤将在后续风险状态模块接入。" type="info" :closable="false" />
  </section>
  <el-alert v-else-if="universeError && storage" title="结构股票池状态暂不可用。" type="warning" :closable="false" />
</template>
