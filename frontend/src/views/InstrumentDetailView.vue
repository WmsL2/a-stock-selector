<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getDailyBars, getFinancialRecords, getIndustryRecords, getInstrument, getLatestRealtime, getValuation } from '@/api/instruments'
import type { DailyBarsResponse, FinancialRecordsResponse, IndustryRecordsResponse, InstrumentResponse, RealtimeLookupResponse, ValuationLookupResponse } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'
import StockDailyChart from '@/components/StockDailyChart.vue'
import { formatLocalTime, formatNumber } from '@/utils/format'

const route = useRoute()
const symbol = computed(() => String(route.params.symbol ?? ''))
const instrument = ref<InstrumentResponse | null>(null)
const daily = ref<DailyBarsResponse | null>(null)
const realtime = ref<RealtimeLookupResponse | null>(null)
const financials = ref<FinancialRecordsResponse | null>(null)
const valuation = ref<ValuationLookupResponse | null>(null)
const industries = ref<IndustryRecordsResponse | null>(null)
const loading = ref(false)
const instrumentError = ref<string | null>(null)
const dailyError = ref<string | null>(null)
const realtimeError = ref<string | null>(null)

function isNotFound(reason: unknown): boolean {
  return typeof reason === 'object' && reason !== null && 'response' in reason &&
    (reason as { response?: { status?: number } }).response?.status === 404
}

async function loadDetail(): Promise<void> {
  loading.value = true
  instrumentError.value = null
  dailyError.value = null
  realtimeError.value = null
  instrument.value = null
  daily.value = null
  realtime.value = null
  financials.value = null
  valuation.value = null
  industries.value = null
  const [instrumentResult, dailyResult, realtimeResult, financialResult, valuationResult, industryResult] = await Promise.allSettled([
    getInstrument(symbol.value),
    getDailyBars(symbol.value, { limit: 500 }),
    getLatestRealtime(symbol.value),
    getFinancialRecords(symbol.value),
    getValuation(symbol.value),
    getIndustryRecords(symbol.value),
  ])
  if (instrumentResult.status === 'fulfilled') {
    instrument.value = instrumentResult.value
  } else {
    instrumentError.value = isNotFound(instrumentResult.reason) ? '未找到该股票。' : '无法读取本地股票基础信息。'
  }
  if (dailyResult.status === 'fulfilled') {
    daily.value = dailyResult.value
  } else {
    dailyError.value = '无法读取本地日线数据。'
  }
  if (realtimeResult.status === 'fulfilled') {
    realtime.value = realtimeResult.value
  } else {
    realtimeError.value = '无法读取本地实时数据。'
  }
  if (financialResult.status === 'fulfilled') financials.value = financialResult.value
  if (valuationResult.status === 'fulfilled') valuation.value = valuationResult.value
  if (industryResult.status === 'fulfilled') industries.value = industryResult.value
  loading.value = false
}

function changeClass(value: number | null | undefined): string {
  if (value === undefined || value === null || value === 0) return 'quote-neutral'
  return value > 0 ? 'quote-up' : 'quote-down'
}

watch(symbol, () => void loadDetail())
onMounted(() => void loadDetail())
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">LOCAL STOCK DETAIL</p><h1>{{ symbol }}</h1></div></section>
  <el-skeleton v-if="loading" :rows="10" animated />
  <el-alert v-else-if="instrumentError" :title="instrumentError" type="error" show-icon :closable="false" />
  <template v-else-if="instrument">
    <section class="panel detail-meta">
      <div><span>股票名称</span><strong>{{ instrument.name }}</strong></div><div><span>代码</span><strong>{{ instrument.symbol }}</strong></div><div><span>交易所</span><strong>{{ instrument.exchange }}</strong></div><div><span>板块</span><strong>{{ instrument.board }}</strong></div><div><span>上市日期</span><strong>{{ instrument.listing_date }}</strong></div><div><span>退市日期</span><strong>{{ instrument.delisting_date ?? '—' }}</strong></div><div><span>本地基础信息状态</span><strong>{{ instrument.status }}</strong></div>
    </section>
    <section class="panel"><h2>本地实时快照</h2>
      <el-alert v-if="realtimeError" :title="realtimeError" type="error" show-icon :closable="false" />
      <template v-else-if="realtime?.available && realtime.quote"><div class="quote-grid"><div><span>最新价</span><strong>{{ formatNumber(realtime.quote.price) }}</strong></div><div><span>涨跌幅</span><strong :class="changeClass(realtime.quote.change_pct)">{{ realtime.quote.change_pct === null ? '—' : `${realtime.quote.change_pct > 0 ? '+' : ''}${realtime.quote.change_pct.toFixed(2)}%` }}</strong></div><div><span>今开</span><strong>{{ formatNumber(realtime.quote.open) }}</strong></div><div><span>最高</span><strong>{{ formatNumber(realtime.quote.high) }}</strong></div><div><span>最低</span><strong>{{ formatNumber(realtime.quote.low) }}</strong></div><div><span>昨收</span><strong>{{ formatNumber(realtime.quote.prev_close) }}</strong></div><div><span>成交量</span><strong>{{ formatNumber(realtime.quote.volume) }}</strong></div><div><span>成交额</span><strong>{{ formatNumber(realtime.quote.amount) }}</strong></div></div><p class="provenance">数据源：{{ realtime.quote.source }} · 本地抓取时间：{{ formatLocalTime(realtime.quote.ingested_at) }} · 行情源时间：{{ realtime.quote.source_timestamp ? formatLocalTime(realtime.quote.source_timestamp) : '行情源时间不可用' }}</p></template>
      <el-alert v-else title="该股票暂无可用的本地实时快照。" type="info" :closable="false" />
    </section>
    <section class="panel"><h2>本地日线 K 线</h2><el-alert v-if="dailyError" :title="dailyError" type="error" show-icon :closable="false" /><StockDailyChart v-else :bars="daily?.items ?? []" /></section>
    <section class="panel"><h2>最近本地 DailyBar</h2><el-table v-if="!dailyError" :data="daily?.items ?? []"><el-table-column prop="trade_date" label="日期" /><el-table-column prop="open" label="开盘" /><el-table-column prop="high" label="最高" /><el-table-column prop="low" label="最低" /><el-table-column prop="close" label="收盘" /><el-table-column prop="volume" label="成交量" /><el-table-column prop="amount" label="成交额" /><el-table-column prop="adjustment" label="复权口径" /><el-table-column prop="source" label="数据源" /></el-table><EmptyState v-if="!dailyError && daily && daily.items.length === 0" title="暂无本地日线数据" description="股票基础信息存在，但尚未保存日线数据。" /></section>
    <section class="panel"><h2>已公开财务、估值与行业</h2>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="最新财报期">{{ financials?.items.at(-1)?.report_period ?? '暂无本地数据' }}</el-descriptions-item><el-descriptions-item label="公告 / 系统可用">{{ financials?.items.at(-1) ? `${financials.items.at(-1)?.announcement_date} / ${formatLocalTime(financials.items.at(-1)?.available_at ?? null)}` : '—' }}</el-descriptions-item>
        <el-descriptions-item label="ROE (%)">{{ formatNumber(financials?.items.at(-1)?.roe ?? null) }}</el-descriptions-item><el-descriptions-item label="净利润 (CNY)">{{ formatNumber(financials?.items.at(-1)?.net_profit ?? null) }}</el-descriptions-item>
        <el-descriptions-item label="估值 as_of">{{ formatLocalTime(valuation?.record?.as_of ?? null) }}</el-descriptions-item><el-descriptions-item label="PE / PB / PCF">{{ `${formatNumber(valuation?.record?.pe ?? null)} / ${formatNumber(valuation?.record?.pb ?? null)} / ${formatNumber(valuation?.record?.pcf ?? null)}` }}</el-descriptions-item>
        <el-descriptions-item label="行业">{{ industries?.items.at(-1)?.industry_name ?? '暂无可靠本地数据' }}</el-descriptions-item><el-descriptions-item label="有效区间">{{ industries?.items.at(-1) ? `${industries.items.at(-1)?.effective_from} 至 ${industries.items.at(-1)?.effective_to ?? '当前'}` : '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert title="报告期不等于市场可用时间；历史读取仅使用公告日 15:30 后已经公开的本地记录。" type="info" :closable="false" />
    </section>
  </template>
</template>
