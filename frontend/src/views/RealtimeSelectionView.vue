<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'

import EmptyState from '@/components/EmptyState.vue'
import { useAppStore } from '@/stores/app'
import { formatLocalTime } from '@/utils/format'

const appStore = useAppStore()
const { storage } = storeToRefs(appStore)
const infrastructureStatus = computed(() =>
  storage.value
    ? `最近本地快照：${formatLocalTime(storage.value.latest_realtime_at)}；已保存 ${storage.value.realtime_symbols} 只股票、${storage.value.realtime_snapshots} 个快照。`
    : '正在读取本地快照状态。',
)

onMounted(() => {
  if (!storage.value) {
    void appStore.refreshStatus()
  }
})
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">REALTIME SELECTION</p><h1>实时选股</h1></div></section>
  <section class="panel"><EmptyState title="实时选股引擎尚未实现" :description="`Realtime Scanner、IntradayScore 与 RealTimeScore 尚未实现。${infrastructureStatus}`" /></section>
</template>
