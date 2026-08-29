<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useAppStore } from '@/stores/app'
import { getUniverseStatus } from '@/api/universe'
import { getQualityStatus } from '@/api/quality'
import type { QualityStatusResponse, UniverseStatusResponse } from '@/api/types'
import { formatBytes, formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { error, loading, storage } = storeToRefs(appStore)
const universe = ref<UniverseStatusResponse | null>(null)
const universeError = ref(false)
const quality = ref<QualityStatusResponse | null>(null)
const qualityError = ref(false)

async function loadUniverseStatus(): Promise<void> {
  universeError.value = false
  try {
    universe.value = await getUniverseStatus()
  } catch {
    universe.value = null
    universeError.value = true
  }
}

async function loadQualityStatus(): Promise<void> {
  qualityError.value = false
  try {
    quality.value = await getQualityStatus()
  } catch {
    quality.value = null
    qualityError.value = true
  }
}

function freshnessLabel(value: QualityStatusResponse['realtime_freshness']): string {
  return {
    fresh: '正常',
    warning: '警告',
    stale: '过期',
    unavailable: '暂无数据',
  }[value]
}

onMounted(() => {
  appStore.ensureStatus()
  void loadUniverseStatus()
  void loadQualityStatus()
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
    <el-descriptions-item label="Risk state rows">{{ storage.risk_state_rows }}</el-descriptions-item>
    <el-descriptions-item label="Risk state dates">{{ storage.risk_state_dates }}</el-descriptions-item>
    <el-descriptions-item label="Latest risk state date">{{ storage.latest_risk_state_date ?? 'unavailable' }}</el-descriptions-item>
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
  <section v-if="quality" class="panel">
    <h2>Data Quality / Risk State</h2>
    <el-descriptions :column="2" border>
      <el-descriptions-item label="Risk state records">{{ quality.risk_state_records }}</el-descriptions-item>
      <el-descriptions-item label="Risk complete instruments">{{ quality.risk_complete_instruments }}</el-descriptions-item>
      <el-descriptions-item label="Risk coverage">{{ Math.round(quality.risk_coverage_ratio * 100) }}%</el-descriptions-item>
      <el-descriptions-item label="Risk filter ready">{{ quality.risk_filter_ready ? 'YES' : 'NO' }}</el-descriptions-item>
      <el-descriptions-item label="Risk eligible instruments">{{ quality.risk_eligible_instruments ?? 'unavailable' }}</el-descriptions-item>
      <el-descriptions-item label="Realtime freshness">{{ freshnessLabel(quality.realtime_freshness) }}</el-descriptions-item>
      <el-descriptions-item label="Realtime age">{{ quality.realtime_age_seconds === null ? 'unavailable' : `${quality.realtime_age_seconds.toFixed(1)}s` }}</el-descriptions-item>
      <el-descriptions-item label="Latest realtime">{{ formatLocalTime(quality.latest_realtime_at) }}</el-descriptions-item>
    </el-descriptions>
    <el-alert v-if="!quality.risk_filter_ready" title="风险状态数据尚未完整覆盖，未知状态不会被视为安全。" type="warning" :closable="false" />
    <el-alert title="实时新鲜度仅表示本地保存的最近 realtime 数据年龄，不表示交易所、AKShare 或股票交易状态正常。" type="info" :closable="false" />
  </section>
  <el-alert v-else-if="qualityError && storage" title="数据质量状态暂不可用。" type="warning" :closable="false" />
  <el-alert v-if="universeError && storage" title="结构股票池状态暂不可用。" type="warning" :closable="false" />
</template>
