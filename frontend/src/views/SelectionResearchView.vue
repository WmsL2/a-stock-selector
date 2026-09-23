<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getSelectionResearchEffectiveness, getSelectionResearchHistory, getSelectionResearchLatest, getSelectionResearchStability, selectionResearchDownloadUrl } from '@/api/selection'
import type { SelectionResearchEffectivenessResponse, SelectionResearchHistoryResponse, SelectionResearchLatestResponse, SelectionResearchStabilityResponse } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'
import SelectionItemExplainability from '@/components/SelectionItemExplainability.vue'
import SelectionResearchExplorer from '@/components/SelectionResearchExplorer.vue'

const loading = ref(false)
const error = ref<string | null>(null)
const response = ref<SelectionResearchLatestResponse | null>(null)
const snapshot = computed(() => response.value?.snapshot ?? null)
const evaluatedAt = ref('')
const startDate = ref('')
const endDate = ref('')
const effectivenessLoading = ref(false)
const effectivenessError = ref<string | null>(null)
const effectiveness = ref<SelectionResearchEffectivenessResponse | null>(null)
const historyStartDate = ref('')
const historyEndDate = ref('')
const historyLoading = ref(false)
const historyError = ref<string | null>(null)
const historyResponse = ref<SelectionResearchHistoryResponse | null>(null)
const stabilityStartDate = ref('')
const stabilityEndDate = ref('')
const stabilityLoading = ref(false)
const stabilityError = ref<string | null>(null)
const stabilityResponse = ref<SelectionResearchStabilityResponse | null>(null)
const canLoadEffectiveness = computed(() => evaluatedAt.value.trim().length > 0)

function score(value: number | null): string { return value === null ? '—' : value.toFixed(1) }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%` }
function researchPercent(value: number | null): string { return value === null ? '—' : `${(value * 100).toFixed(2)}%` }
function metric(value: number | null): string { return value === null ? '—' : `${(value * 100).toFixed(2)}%` }
function stabilityPercent(value: number | null): string { return value === null ? '—' : `${(value * 100).toFixed(2)}%` }
function rankChange(value: number | null): string { return value === null ? '—' : value > 0 ? `+${value}` : String(value) }
function rankRows() {
  return effectiveness.value?.ranks.flatMap(item => item.horizons.map(horizon => ({ ...horizon, rank: item.rank, observation_count: item.observation_count }))) ?? []
}
function cutoffRows() {
  return effectiveness.value?.cutoffs.flatMap(item => item.horizons.map(horizon => ({ ...horizon, cutoff_rank: item.cutoff_rank, included_ranks: item.included_ranks, observation_count: item.observation_count }))) ?? []
}
async function loadEffectiveness(): Promise<void> {
  const evaluated_at = evaluatedAt.value.trim()
  if (!evaluated_at) return
  const start_date = startDate.value.trim()
  const end_date = endDate.value.trim()
  effectivenessLoading.value = true; effectivenessError.value = null; effectiveness.value = null
  try { effectiveness.value = await getSelectionResearchEffectiveness({ evaluated_at, ...(start_date ? { start_date } : {}), ...(end_date ? { end_date } : {}) }) }
  catch { effectivenessError.value = '无法读取选股研究有效性；请确认评估时点包含时区且日期范围有效。' }
  finally { effectivenessLoading.value = false }
}
async function loadHistory(): Promise<void> {
  const start_date = historyStartDate.value.trim()
  const end_date = historyEndDate.value.trim()
  historyLoading.value = true
  historyError.value = null
  historyResponse.value = null
  try {
    historyResponse.value = await getSelectionResearchHistory({
      ...(start_date ? { start_date } : {}),
      ...(end_date ? { end_date } : {}),
    })
  } catch {
    historyError.value = '无法读取历史选股研究快照。'
  } finally {
    historyLoading.value = false
  }
}
async function loadStability(): Promise<void> {
  const start_date = stabilityStartDate.value.trim()
  const end_date = stabilityEndDate.value.trim()
  stabilityLoading.value = true
  stabilityError.value = null
  stabilityResponse.value = null
  try {
    stabilityResponse.value = await getSelectionResearchStability({
      ...(start_date ? { start_date } : {}),
      ...(end_date ? { end_date } : {}),
    })
  } catch {
    stabilityError.value = '无法读取选股稳定性分析。'
  } finally {
    stabilityLoading.value = false
  }
}
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
        <el-table-column type="expand"><template #default="scope"><SelectionItemExplainability :item="scope.row" /></template></el-table-column>
        <el-table-column prop="rank" label="排名" width="66" /><el-table-column prop="symbol" label="代码" min-width="112" /><el-table-column prop="name" label="名称" min-width="112" /><el-table-column prop="board" label="板块" width="90" /><el-table-column label="行业" min-width="130"><template #default="scope">{{ scope.row.industry_name ?? '—' }}</template></el-table-column>
        <el-table-column label="BaseScore" width="100"><template #default="scope">{{ score(scope.row.base_score) }}</template></el-table-column><el-table-column label="Confidence Adj." width="126"><template #default="scope">{{ score(scope.row.confidence_adjusted_score) }}</template></el-table-column><el-table-column label="完整度" width="85"><template #default="scope">{{ percent(scope.row.data_completeness) }}</template></el-table-column><el-table-column label="置信度" width="85"><template #default="scope">{{ percent(scope.row.confidence) }}</template></el-table-column><el-table-column label="Quality" width="85"><template #default="scope">{{ score(scope.row.quality_score) }}</template></el-table-column><el-table-column label="Value" width="80"><template #default="scope">{{ score(scope.row.value_score) }}</template></el-table-column><el-table-column label="Growth" width="84"><template #default="scope">{{ score(scope.row.growth_score) }}</template></el-table-column><el-table-column label="Momentum" width="95"><template #default="scope">{{ score(scope.row.momentum_score) }}</template></el-table-column><el-table-column label="LowVol" width="84"><template #default="scope">{{ score(scope.row.low_volatility_score) }}</template></el-table-column>
      </el-table>
    </section>
  </template>
  <SelectionResearchExplorer />
  <section class="panel" data-testid="effectiveness-panel">
    <h2>历史选股有效性</h2>
    <p class="provenance">评估时点是显式的点时证据截止；必须包含时区，浏览器不会自动填入当前时间。统计按历史选股 item-observation 汇总，不是按交易日等权，也不是组合收益；仅为描述性研究，不代表组合收益、NAV、PnL、回测或交易建议。</p>
    <el-form label-position="top"><el-form-item label="评估时点（含时区 ISO 8601）"><el-input v-model="evaluatedAt" data-testid="evaluated-at-input" placeholder="2026-09-20T16:00:00+08:00" /></el-form-item><el-form-item label="开始日期（可选）"><el-input v-model="startDate" data-testid="start-date-input" placeholder="YYYY-MM-DD" /></el-form-item><el-form-item label="结束日期（可选）"><el-input v-model="endDate" data-testid="end-date-input" placeholder="YYYY-MM-DD" /></el-form-item><el-button data-testid="load-effectiveness" type="primary" :disabled="!canLoadEffectiveness" :loading="effectivenessLoading" @click="loadEffectiveness">读取有效性</el-button></el-form>
    <el-alert v-if="effectivenessError" :title="effectivenessError" type="error" :closable="false" show-icon />
    <template v-if="effectiveness">
      <el-descriptions :column="3" border><el-descriptions-item label="评估时点">{{ effectiveness.evaluated_at }}</el-descriptions-item><el-descriptions-item label="开始日期">{{ effectiveness.start_date ?? '—' }}</el-descriptions-item><el-descriptions-item label="结束日期">{{ effectiveness.end_date ?? '—' }}</el-descriptions-item><el-descriptions-item label="快照数">{{ effectiveness.snapshot_count }}</el-descriptions-item><el-descriptions-item label="空快照数">{{ effectiveness.empty_snapshot_count }}</el-descriptions-item><el-descriptions-item label="选股项观测数">{{ effectiveness.item_observation_count }}</el-descriptions-item></el-descriptions>
      <p v-if="effectiveness.snapshot_count === 0" data-testid="effectiveness-empty">所选评估时点和日期范围内没有持久化的选股研究快照。</p><p v-else-if="effectiveness.item_observation_count === 0" data-testid="effectiveness-blocked">范围内存在持久化快照，但没有可用于收益标签统计的选股项；快照可能为阻断或空结果。</p>
      <h3>整体期限</h3><el-table :data="effectiveness.overall_horizons" data-testid="overall-horizons"><el-table-column prop="horizon_sessions" label="期限" /><el-table-column prop="total_labels" label="标签数" /><el-table-column prop="available_labels" label="可用" /><el-table-column prop="anchor_unavailable_labels" label="锚点不可用" /><el-table-column prop="insufficient_future_returns_labels" label="未来不足" /><el-table-column prop="non_contiguous_return_evidence_labels" label="不连续" /><el-table-column prop="positive_return_labels" label="正" /><el-table-column prop="zero_return_labels" label="零" /><el-table-column prop="negative_return_labels" label="负" /><el-table-column label="可用率"><template #default="scope">{{ researchPercent(scope.row.availability_rate) }}</template></el-table-column><el-table-column label="正收益率"><template #default="scope">{{ researchPercent(scope.row.positive_return_rate) }}</template></el-table-column><el-table-column label="均值"><template #default="scope">{{ metric(scope.row.mean_return_fraction) }}</template></el-table-column><el-table-column label="中位数"><template #default="scope">{{ metric(scope.row.median_return_fraction) }}</template></el-table-column></el-table>
      <el-tabs><el-tab-pane label="精确排名"><el-table :data="rankRows()" data-testid="exact-ranks"><el-table-column label="排名"><template #default="scope"><span :data-testid="`effectiveness-rank-${scope.row.rank}`">{{ scope.row.rank }}</span></template></el-table-column><el-table-column prop="observation_count" label="观测数" /><el-table-column prop="horizon_sessions" label="期限" /><el-table-column prop="available_labels" label="可用" /><el-table-column prop="total_labels" label="标签数" /><el-table-column label="可用率"><template #default="scope">{{ researchPercent(scope.row.availability_rate) }}</template></el-table-column><el-table-column label="正收益率"><template #default="scope">{{ researchPercent(scope.row.positive_return_rate) }}</template></el-table-column><el-table-column label="均值"><template #default="scope">{{ metric(scope.row.mean_return_fraction) }}</template></el-table-column><el-table-column label="中位数"><template #default="scope">{{ metric(scope.row.median_return_fraction) }}</template></el-table-column></el-table></el-tab-pane><el-tab-pane label="观测排名截止"><el-table :data="cutoffRows()" data-testid="rank-cutoffs"><el-table-column label="截止排名"><template #default="scope"><span :data-testid="`effectiveness-cutoff-${scope.row.cutoff_rank}`">{{ scope.row.cutoff_rank }}</span></template></el-table-column><el-table-column label="包含排名"><template #default="scope">{{ scope.row.included_ranks.join(', ') }}</template></el-table-column><el-table-column prop="observation_count" label="观测数" /><el-table-column prop="horizon_sessions" label="期限" /><el-table-column prop="available_labels" label="可用" /><el-table-column prop="total_labels" label="标签数" /><el-table-column label="可用率"><template #default="scope">{{ researchPercent(scope.row.availability_rate) }}</template></el-table-column><el-table-column label="正收益率"><template #default="scope">{{ researchPercent(scope.row.positive_return_rate) }}</template></el-table-column><el-table-column label="均值"><template #default="scope">{{ metric(scope.row.mean_return_fraction) }}</template></el-table-column><el-table-column label="中位数"><template #default="scope">{{ metric(scope.row.median_return_fraction) }}</template></el-table-column></el-table></el-tab-pane></el-tabs>
    </template>
  </section>
  <section class="panel" data-testid="stability-panel">
    <h2>选股稳定性 / 排名变化</h2>
    <p class="provenance">稳定性分析比较所选日期范围内相邻的持久化官方快照。排名变化 = 前一期排名 - 当前排名；正数表示排名上升。阻断快照或策略名称变化不会被当作可比较的选股变动。这是描述性选股研究，不是组合换手或交易活动。</p>
    <el-input v-model="stabilityStartDate" data-testid="stability-start-date-input" placeholder="开始日期" />
    <el-input v-model="stabilityEndDate" data-testid="stability-end-date-input" placeholder="结束日期" />
    <el-button data-testid="load-stability" :loading="stabilityLoading" @click="loadStability">读取稳定性</el-button>
    <el-alert v-if="stabilityError" :title="stabilityError" type="error" :closable="false" />
    <template v-if="stabilityResponse">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="快照数">{{ stabilityResponse.snapshot_count }}</el-descriptions-item>
        <el-descriptions-item label="相邻区间数">{{ stabilityResponse.transition_count }}</el-descriptions-item>
        <el-descriptions-item label="可比较区间数">{{ stabilityResponse.comparable_transition_count }}</el-descriptions-item>
      </el-descriptions>
      <p v-if="stabilityResponse.snapshot_count === 0" data-testid="stability-empty">所选日期范围内没有持久化的选股研究快照。</p>
      <p v-else-if="stabilityResponse.snapshot_count === 1" data-testid="stability-single-snapshot">所选日期范围内只有一个持久化快照，没有相邻快照可比较。</p>
      <p v-else-if="stabilityResponse.comparable_transition_count === 0" data-testid="stability-no-comparable">存在相邻快照，但由于选股阻断或策略变化，没有可比较的稳定性区间。</p>
      <article v-for="(transition, transitionIndex) in stabilityResponse.transitions" :key="transition.current_as_of" class="panel" :data-testid="`stability-transition-${transitionIndex}`">
        <h3>{{ transition.previous_as_of }} → {{ transition.current_as_of }}</h3>
        <p>策略：{{ transition.previous_strategy_name }} → {{ transition.current_strategy_name }}</p>
        <p>可比较：{{ transition.comparable ? '是' : '否' }}</p>
        <p>比较阻断：{{ transition.comparison_blockers.join(', ') || 'none' }}</p>
        <p>前期官方阻断：{{ transition.previous_blockers.join(', ') || 'none' }}</p>
        <p>当前官方阻断：{{ transition.current_blockers.join(', ') || 'none' }}</p>
        <p>前期 / 当前选股项：{{ transition.previous_item_count }} / {{ transition.current_item_count }}</p>
        <template v-if="transition.comparable">
          <p>保留 / 新进入选股名单 / 退出选股名单：{{ transition.retained_count }} / {{ transition.entered_count }} / {{ transition.exited_count }}</p>
          <p>保留率：{{ stabilityPercent(transition.retention_rate) }}；重叠率：{{ stabilityPercent(transition.overlap_rate) }}</p>
          <el-table :data="transition.movements" class="instrument-table">
            <el-table-column label="状态"><template #default="scope"><span :data-testid="`stability-movement-${scope.$index}`">{{ scope.row.status }}</span></template></el-table-column>
            <el-table-column prop="symbol" label="代码" /><el-table-column prop="name" label="名称" />
            <el-table-column label="前期排名"><template #default="scope">{{ scope.row.previous_rank ?? '—' }}</template></el-table-column>
            <el-table-column label="当前排名"><template #default="scope">{{ scope.row.current_rank ?? '—' }}</template></el-table-column>
            <el-table-column label="排名变化"><template #default="scope">{{ rankChange(scope.row.rank_change) }}</template></el-table-column>
          </el-table>
        </template>
        <p v-else data-testid="stability-unavailable">该相邻快照不可进行排名稳定性比较。</p>
      </article>
    </template>
  </section>
  <section class="panel" data-testid="history-panel">
    <h2>历史选股快照</h2>
    <p class="provenance">仅浏览持久化的官方快照；不会重新选股、访问行情或写入数据。</p>
    <el-input v-model="historyStartDate" data-testid="history-start-date-input" placeholder="开始日期" />
    <el-input v-model="historyEndDate" data-testid="history-end-date-input" placeholder="结束日期" />
    <el-button data-testid="load-history" :loading="historyLoading" @click="loadHistory">读取历史</el-button>
    <el-alert v-if="historyError" :title="historyError" type="error" :closable="false" />
    <p v-if="historyResponse?.snapshot_count === 0" data-testid="history-empty">所选日期范围内没有持久化的选股研究快照。</p>
    <article
      v-for="(historySnapshot, snapshotIndex) in historyResponse?.snapshots ?? []"
      :key="historySnapshot.as_of"
      class="panel"
      :data-testid="`history-snapshot-${snapshotIndex}`"
    >
      <h3>{{ historySnapshot.as_of }} · {{ historySnapshot.strategy_name }}</h3>
      <p>官方选股状态：{{ historySnapshot.selection_ready ? '已就绪' : '已阻断' }}</p>
      <p>阻断：{{ historySnapshot.blockers.join(', ') || 'none' }}</p>
      <p>刷新采集：{{ historySnapshot.refresh_had_collection_failures ? '包含失败' : '无嵌套失败' }}</p>
      <p>返回选股项：{{ historySnapshot.diagnostics.returned_items }}</p>
      <el-table :data="historySnapshot.items" class="instrument-table">
        <el-table-column type="expand"><template #default="scope"><SelectionItemExplainability :item="scope.row" /></template></el-table-column>
        <el-table-column prop="rank" label="排名" width="66" />
        <el-table-column prop="symbol" label="代码" min-width="112" />
        <el-table-column prop="name" label="名称" min-width="112" />
        <el-table-column label="BaseScore" width="100"><template #default="scope">{{ score(scope.row.base_score) }}</template></el-table-column>
        <el-table-column label="Confidence Adj." width="126"><template #default="scope">{{ score(scope.row.confidence_adjusted_score) }}</template></el-table-column>
        <el-table-column label="完整度" width="85"><template #default="scope">{{ percent(scope.row.data_completeness) }}</template></el-table-column>
        <el-table-column label="置信度" width="85"><template #default="scope">{{ percent(scope.row.confidence) }}</template></el-table-column>
      </el-table>
    </article>
  </section>
</template>
