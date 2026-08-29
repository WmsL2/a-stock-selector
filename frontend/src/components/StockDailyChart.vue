<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { DailyBarResponse } from '@/api/types'
import EmptyState from './EmptyState.vue'

const props = defineProps<{
  bars: DailyBarResponse[]
}>()

const chartElement = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function renderChart(): void {
  if (!chartElement.value || props.bars.length === 0) {
    return
  }
  chart ??= echarts.init(chartElement.value)
  chart.setOption({
    animation: false,
    backgroundColor: 'transparent',
    grid: { left: 54, right: 24, top: 24, bottom: 48 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: props.bars.map((bar) => bar.trade_date),
      axisLine: { lineStyle: { color: '#3a465b' } },
      axisLabel: { color: '#aab4c7' },
    },
    yAxis: {
      scale: true,
      axisLine: { lineStyle: { color: '#3a465b' } },
      splitLine: { lineStyle: { color: '#273244' } },
      axisLabel: { color: '#aab4c7' },
    },
    series: [
      {
        type: 'candlestick',
        data: props.bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]),
        itemStyle: {
          color: '#d85b64',
          color0: '#43a77b',
          borderColor: '#d85b64',
          borderColor0: '#43a77b',
        },
      },
    ],
  })
}

function resizeChart(): void {
  chart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', resizeChart)
  void nextTick(renderChart)
})

watch(
  () => props.bars,
  () => void nextTick(renderChart),
  { deep: true },
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <EmptyState
    v-if="bars.length === 0"
    title="暂无本地日线数据"
    description="该股票尚未持久化 DailyBar，无法绘制 K 线。"
  />
  <div v-else ref="chartElement" class="stock-daily-chart" aria-label="本地日线 K 线图" />
</template>
