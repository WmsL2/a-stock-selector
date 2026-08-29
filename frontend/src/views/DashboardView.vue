<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'

import MetricCard from '@/components/MetricCard.vue'
import { useAppStore } from '@/stores/app'
import { getUniverseStatus } from '@/api/universe'
import { getQualityStatus } from '@/api/quality'
import { getDailyStatus } from '@/api/daily'
import type { DailyStatusResponse, QualityStatusResponse, UniverseStatusResponse } from '@/api/types'
import { formatBytes, formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { error, health, loading, storage } = storeToRefs(appStore)
const universe = ref<UniverseStatusResponse | null>(null)
const universeError = ref(false)
const quality = ref<QualityStatusResponse | null>(null)
const qualityError = ref(false)
const daily = ref<DailyStatusResponse | null>(null)
const dailyError = ref(false)

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

async function loadDailyStatus(): Promise<void> {
  dailyError.value = false
  try {
    daily.value = await getDailyStatus()
  } catch {
    daily.value = null
    dailyError.value = true
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
  void loadDailyStatus()
})
</script>

<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">LOCAL QUANT RESEARCH</p>
      <h1>A股量化选股系统</h1>
      <p>个人量化研究与选股工具</p>
    </div>
    <el-tag type="warning" effect="plain">仅供研究参考，不构成投资建议</el-tag>
  </section>

  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
  <el-skeleton v-else-if="loading && !storage" :rows="5" animated />
  <template v-else-if="storage">
    <section class="metrics-grid">
      <MetricCard label="全市场股票" :value="storage.instrument_rows" description="本地基础信息" />
      <MetricCard label="当前结构股票池" :value="universe?.included_instruments ?? '—'" :description="universeError ? '股票池状态暂不可用' : '本地结构性范围'" />
      <MetricCard label="风险数据覆盖" :value="quality ? `${Math.round(quality.risk_coverage_ratio * 100)}%` : '—'" :description="qualityError ? '质量状态暂不可用' : quality?.risk_filter_ready ? '风险过滤已就绪' : '风险过滤尚未就绪'" />
      <MetricCard label="实时数据状态" :value="quality ? freshnessLabel(quality.realtime_freshness) : '—'" description="本地抓取时间状态" />
      <MetricCard label="详细日线股票" :value="storage.daily_symbols" description="选择性持久化" />
      <MetricCard label="日线记录" :value="storage.daily_rows" description="本地 DailyBar" />
      <MetricCard label="最新日线日期" :value="daily?.latest_trade_date ?? '暂无数据'" :description="dailyError ? '日线状态暂不可用' : '未验证交易日历完整性'" />
      <MetricCard label="实时跟踪股票" :value="storage.realtime_symbols" description="最新本地快照覆盖" />
      <MetricCard label="实时快照" :value="storage.realtime_snapshots" description="已保存批次" />
      <MetricCard label="磁盘占用" :value="formatBytes(storage.disk_usage_bytes)" description="本地数据文件" />
    </section>
    <section class="panel status-panel">
      <div>
        <h2>系统状态</h2>
        <p>FastAPI：{{ health?.status === 'ok' ? '正常' : '不可用' }}</p>
        <p>本地存储：{{ health?.storage ?? 'unavailable' }}</p>
        <p>本地最近抓取时间：{{ formatLocalTime(storage.latest_realtime_at) }}</p>
      </div>
      <el-alert title="AKShare 已接入，当前页面未执行网络检查。" type="info" :closable="false" />
    </section>
  </template>
</template>
