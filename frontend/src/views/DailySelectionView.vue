<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'

import EmptyState from '@/components/EmptyState.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const { storage } = storeToRefs(appStore)
const infrastructureStatus = computed(() =>
  storage.value
    ? `当前本地已保存 ${storage.value.daily_symbols} 只股票的 ${storage.value.daily_rows} 条日线记录。`
    : '正在读取本地数据基础设施状态。',
)

onMounted(() => {
  if (!storage.value) {
    void appStore.refreshStatus()
  }
})
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">DAILY SELECTION</p><h1>今日选股</h1></div></section>
  <section class="panel"><EmptyState title="今日选股引擎尚未实现" :description="`将在 BaseScore 完成后展示真实候选股票、评分、完整度与排名。${infrastructureStatus}`" /></section>
</template>
