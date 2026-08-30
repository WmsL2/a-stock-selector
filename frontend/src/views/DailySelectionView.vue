<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getDailySelection } from '@/api/selection'
import type { DailySelectionItemResponse, DailySelectionResponse } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const loading = ref(false)
const error = ref<string | null>(null)
const selection = ref<DailySelectionResponse | null>(null)
const diagnostics = computed(() => selection.value?.diagnostics ?? null)

function score(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

function percent(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

function openInstrument(row: DailySelectionItemResponse): void {
  void router.push({ name: 'instrument-detail', params: { symbol: row.symbol } })
}

async function loadSelection(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    selection.value = await getDailySelection()
  } catch {
    selection.value = null
    error.value = '无法读取本地今日选股状态。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadSelection())
</script>

<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">DAILY SELECTION</p>
      <h1>今日选股</h1>
      <p>结构股票池 → 精确日期风险过滤 → PIT 因子 → BaseScore 排名。本页不触发采集或写入。</p>
    </div>
    <el-button type="primary" :loading="loading" @click="loadSelection">刷新本地结果</el-button>
  </section>

  <p v-if="loading" role="status" class="provenance">正在读取本地今日选股状态…</p>

  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
  <template v-else-if="diagnostics">
    <section class="metrics-grid">
      <article class="metric-card"><span class="metric-card__label">选股状态</span><strong class="metric-card__value">{{ selection?.selection_ready ? '已就绪' : '尚未就绪' }}</strong><span class="metric-card__description">as-of {{ selection?.as_of }}</span></article>
      <article class="metric-card"><span class="metric-card__label">结构股票池</span><strong class="metric-card__value">{{ diagnostics.structural_members }}</strong><span class="metric-card__description">输入 {{ diagnostics.input_instruments }}</span></article>
      <article class="metric-card"><span class="metric-card__label">风险完整覆盖</span><strong class="metric-card__value">{{ diagnostics.risk_complete_members }}</strong><span class="metric-card__description">{{ percent(diagnostics.risk_coverage_ratio) }}</span></article>
      <article class="metric-card"><span class="metric-card__label">风险合格</span><strong class="metric-card__value">{{ diagnostics.risk_eligible_members }}</strong><span class="metric-card__description">仅精确日期、完整风险状态</span></article>
      <article class="metric-card"><span class="metric-card__label">可评分</span><strong class="metric-card__value">{{ diagnostics.scoreable_members }}</strong><span class="metric-card__description">无最低完整度阈值</span></article>
      <article class="metric-card"><span class="metric-card__label">返回数量</span><strong class="metric-card__value">{{ diagnostics.returned_items }}/{{ diagnostics.requested_top_n }}</strong><span class="metric-card__description">按 BaseScore 排名</span></article>
    </section>

    <section v-if="!selection?.selection_ready" class="panel">
      <EmptyState title="今日选股尚未就绪" :description="selection?.blockers.includes('risk_state_coverage_incomplete') ? '风险状态覆盖不足；未知或缺失风险状态不会被当作安全，官方候选为空。' : '当前本地数据不足以形成可评分的官方候选。'" />
    </section>
    <section v-else-if="selection?.items.length === 0" class="panel">
      <EmptyState title="暂无可评分股票" description="风险过滤已通过，但当前可用因子无法形成 BaseScore。" />
    </section>
    <section v-else class="panel">
      <h2>BaseScore Top {{ diagnostics.returned_items }}</h2>
      <p class="provenance">完整度和置信度显示为百分比；Momentum / LowVol 缺失时显示“—”，不会被显示为 0 分。</p>
      <el-table v-loading="loading" :data="selection?.items ?? []" class="instrument-table" @row-click="openInstrument">
        <el-table-column prop="rank" label="排名" width="66" />
        <el-table-column prop="symbol" label="代码" min-width="112" />
        <el-table-column prop="name" label="名称" min-width="112" />
        <el-table-column label="BaseScore" width="102"><template #default="scope">{{ score(scope.row.base_score) }}</template></el-table-column>
        <el-table-column label="Confidence Adj." width="126"><template #default="scope">{{ score(scope.row.confidence_adjusted_score) }}</template></el-table-column>
        <el-table-column label="完整度" width="86"><template #default="scope">{{ percent(scope.row.data_completeness) }}</template></el-table-column>
        <el-table-column label="置信度" width="86"><template #default="scope">{{ percent(scope.row.confidence) }}</template></el-table-column>
        <el-table-column label="Quality" width="88"><template #default="scope">{{ score(scope.row.quality_score) }}</template></el-table-column>
        <el-table-column label="Value" width="80"><template #default="scope">{{ score(scope.row.value_score) }}</template></el-table-column>
        <el-table-column label="Growth" width="84"><template #default="scope">{{ score(scope.row.growth_score) }}</template></el-table-column>
        <el-table-column label="Momentum" width="98"><template #default="scope">{{ score(scope.row.momentum_score) }}</template></el-table-column>
        <el-table-column label="LowVol" width="84"><template #default="scope">{{ score(scope.row.low_volatility_score) }}</template></el-table-column>
      </el-table>
    </section>
  </template>
</template>
