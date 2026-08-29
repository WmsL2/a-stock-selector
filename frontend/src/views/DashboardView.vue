<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'

import MetricCard from '@/components/MetricCard.vue'
import { useAppStore } from '@/stores/app'
import { formatBytes, formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { error, health, loading, storage } = storeToRefs(appStore)

onMounted(() => {
  if (!health.value && !loading.value) {
    void appStore.refreshStatus()
  }
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
      <MetricCard label="详细日线股票" :value="storage.daily_symbols" description="选择性持久化" />
      <MetricCard label="日线记录" :value="storage.daily_rows" description="本地 DailyBar" />
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
