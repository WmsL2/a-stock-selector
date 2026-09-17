<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getSelectionResearchLatest, selectionResearchDownloadUrl } from '@/api/selection'
import type { SelectionResearchLatestResponse } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'

const loading = ref(false)
const error = ref<string | null>(null)
const response = ref<SelectionResearchLatestResponse | null>(null)
const snapshot = computed(() => response.value?.snapshot ?? null)

function score(value: number | null): string { return value === null ? '—' : value.toFixed(1) }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%` }
async function load(): Promise<void> {
  loading.value = true; error.value = null
  try { response.value = await getSelectionResearchLatest() }
  catch { response.value = null; error.value = '无法读取已导出的选股研究快照。' }
  finally { loading.value = false }
}
function download(format: 'json' | 'csv'): void { window.open(selectionResearchDownloadUrl(format), '_blank') }
onMounted(() => void load())
</script>

<template>
  <section class="page-heading">
    <div><p class="eyebrow">SELECTION RESEARCH</p><h1>选股研究</h1><p>最新持久化的官方选股快照，不会随本地数据变化自动更新。</p></div>
    <div><el-button :loading="loading" @click="load">读取快照</el-button><el-button :disabled="!snapshot" type="primary" @click="download('json')">下载 JSON</el-button><el-button :disabled="!snapshot" @click="download('csv')">下载 CSV</el-button></div>
  </section>
  <p v-if="loading" role="status" class="provenance">正在读取已导出的研究快照…</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
  <section v-else-if="!snapshot" class="panel"><EmptyState title="尚无官方导出快照" description="请运行 python -m stock_selector selection daily 创建官方日选股研究快照。浏览器不会创建或刷新该快照。" /></section>
  <template v-else>
    <el-alert v-if="snapshot.refresh_had_collection_failures" title="官方结果已导出，但本次刷新包含嵌套采集失败。" type="warning" :closable="false" show-icon />
    <section class="metrics-grid">
      <article class="metric-card"><span class="metric-card__label">快照时间</span><strong class="metric-card__value">{{ snapshot.as_of }}</strong><span class="metric-card__description">{{ snapshot.strategy_name }}</span></article>
      <article class="metric-card"><span class="metric-card__label">官方选股状态</span><strong class="metric-card__value">{{ snapshot.selection_ready ? '已就绪' : '已阻断' }}</strong><span class="metric-card__description">{{ snapshot.blockers.join(', ') || 'none' }}</span></article>
      <article class="metric-card"><span class="metric-card__label">刷新采集</span><strong class="metric-card__value">{{ snapshot.refresh_had_collection_failures ? '包含失败' : '无嵌套失败' }}</strong><span class="metric-card__description">仅记录该次刷新采集的已知结果</span></article>
      <article class="metric-card"><span class="metric-card__label">结构股票池</span><strong class="metric-card__value">{{ snapshot.diagnostics.structural_members }}</strong><span class="metric-card__description">风险合格 {{ snapshot.diagnostics.risk_eligible_members }}</span></article>
      <article class="metric-card"><span class="metric-card__label">因子输入 / 可评分</span><strong class="metric-card__value">{{ snapshot.diagnostics.factor_input_members }} / {{ snapshot.diagnostics.scoreable_members }}</strong><span class="metric-card__description">返回 {{ snapshot.diagnostics.returned_items }}</span></article>
    </section>
    <section class="panel">
      <p class="provenance">这是持久化的官方选股快照；同日重新运行 selection daily 可以替换它。排名保持官方原始 BaseScore 顺序，confidence-adjusted score 仅供展示，不构成投资建议。</p>
      <el-table :data="snapshot.items" class="instrument-table">
        <el-table-column type="expand"><template #default="scope"><div class="selection-explanation"><div><h3>主要依据</h3><ul><li v-for="item in scope.row.evidence" :key="item.code">{{ item.message }}</li></ul></div><div><h3>风险</h3><ul><li v-for="item in scope.row.risks" :key="item.code">{{ item.message }}</li></ul></div></div></template></el-table-column>
        <el-table-column prop="rank" label="排名" width="66" /><el-table-column prop="symbol" label="代码" min-width="112" /><el-table-column prop="name" label="名称" min-width="112" /><el-table-column prop="board" label="板块" width="90" /><el-table-column label="行业" min-width="130"><template #default="scope">{{ scope.row.industry_name ?? '—' }}</template></el-table-column>
        <el-table-column label="BaseScore" width="100"><template #default="scope">{{ score(scope.row.base_score) }}</template></el-table-column><el-table-column label="Confidence Adj." width="126"><template #default="scope">{{ score(scope.row.confidence_adjusted_score) }}</template></el-table-column><el-table-column label="完整度" width="85"><template #default="scope">{{ percent(scope.row.data_completeness) }}</template></el-table-column><el-table-column label="置信度" width="85"><template #default="scope">{{ percent(scope.row.confidence) }}</template></el-table-column><el-table-column label="Quality" width="85"><template #default="scope">{{ score(scope.row.quality_score) }}</template></el-table-column><el-table-column label="Value" width="80"><template #default="scope">{{ score(scope.row.value_score) }}</template></el-table-column><el-table-column label="Growth" width="84"><template #default="scope">{{ score(scope.row.growth_score) }}</template></el-table-column><el-table-column label="Momentum" width="95"><template #default="scope">{{ score(scope.row.momentum_score) }}</template></el-table-column><el-table-column label="LowVol" width="84"><template #default="scope">{{ score(scope.row.low_volatility_score) }}</template></el-table-column>
      </el-table>
    </section>
  </template>
</template>
