<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getRealtimeSelection } from '@/api/selection'
import type { RealtimeFreshness, RealtimeSelectionItemResponse, RealtimeSelectionResponse } from '@/api/types'
import EmptyState from '@/components/EmptyState.vue'
import { formatLocalTime, formatNumber } from '@/utils/format'

const router = useRouter()
const loading = ref(false)
const hasRun = ref(false)
const error = ref<string | null>(null)
const selection = ref<RealtimeSelectionResponse | null>(null)

const freshnessLabel = computed(() => {
  const labels: Record<RealtimeFreshness, string> = { fresh: '正常', warning: '警告', stale: '过期', unavailable: '不可用' }
  return selection.value ? labels[selection.value.diagnostics.freshness] : '—'
})

const stages = computed(() => {
  const diagnostics = selection.value?.diagnostics
  if (!diagnostics) return []
  return [
    ['Candidate', diagnostics.candidate_ready, diagnostics.candidate_blockers],
    ['Snapshot', diagnostics.snapshot_ready, diagnostics.snapshot_blockers],
    ['Light Scan', diagnostics.scan_ready, diagnostics.scan_blockers],
    ['Normalization', diagnostics.normalization_ready, diagnostics.normalization_blockers],
    ['Intraday Factors', diagnostics.factor_ready, diagnostics.factor_blockers],
    ['IntradayScore', diagnostics.intraday_score_ready, diagnostics.intraday_score_blockers],
    ['RealTimeScore', diagnostics.realtime_score_ready, diagnostics.realtime_score_blockers],
    ['Top100 Selection', diagnostics.selection_ready, diagnostics.selection_blockers],
  ] as const
})

function score(value: number | null): string { return value === null ? '—' : value.toFixed(1) }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%` }
function quotePercent(value: number | null): string { return value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%` }
function ratio(value: number | null): string { return value === null ? '—' : `${value.toFixed(2)}x` }
function changeClass(value: number | null): string { return value === null || value === 0 ? 'quote-neutral' : value > 0 ? 'quote-up' : 'quote-down' }
function openInstrument(row: RealtimeSelectionItemResponse): void { void router.push({ name: 'instrument-detail', params: { symbol: row.symbol } }) }

async function runSelection(): Promise<void> {
  hasRun.value = true
  loading.value = true
  error.value = null
  selection.value = null
  try {
    selection.value = await getRealtimeSelection()
  } catch {
    selection.value = null
    error.value = '实时选股请求失败，本次结果未生成。请稍后手动重试。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="page-heading">
    <div><p class="eyebrow">REALTIME SELECTION</p><h1>实时选股</h1><p>点击运行后会执行一次全市场实时行情采集和实时选股；行情不会持久化，页面不会自动轮询。</p></div>
    <el-button type="primary" :loading="loading" :disabled="loading" @click="runSelection">{{ hasRun ? '重新运行' : '运行一次实时选股' }}</el-button>
  </section>

  <p v-if="loading" role="status" class="provenance">正在执行一次实时选股，请等待本次全市场行情采集完成…</p>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
  <section v-if="!hasRun && !loading && !error" class="panel"><EmptyState title="尚未运行实时选股" description="点击“运行一次实时选股”后，系统会抓取一次全市场实时行情并执行当前 Top100 流水线；不会自动轮询或持久化本次行情。" /></section>

  <template v-else-if="selection">
    <section class="metrics-grid">
      <article class="metric-card"><span class="metric-card__label">实时选股状态</span><strong class="metric-card__value">{{ selection.selection_ready ? '已就绪' : '尚未就绪' }}</strong><span class="metric-card__description">Top100 流水线</span></article>
      <article class="metric-card"><span class="metric-card__label">Top100 返回</span><strong class="metric-card__value">{{ selection.diagnostics.selected_items }}/{{ selection.policy.top_n }}</strong><span class="metric-card__description">Task22 官方顺序</span></article>
      <article class="metric-card"><span class="metric-card__label">候选池</span><strong class="metric-card__value">{{ selection.diagnostics.candidate_members }}</strong><span class="metric-card__description">后端候选结果</span></article>
      <article class="metric-card"><span class="metric-card__label">排名池</span><strong class="metric-card__value">{{ selection.diagnostics.ranking_universe_items }}</strong><span class="metric-card__description">阈值后的排名池</span></article>
      <article class="metric-card"><span class="metric-card__label">风险覆盖</span><strong class="metric-card__value">{{ percent(selection.diagnostics.risk_coverage_ratio) }}</strong><span class="metric-card__description">{{ selection.diagnostics.risk_complete_members }}/{{ selection.diagnostics.structural_members }}</span></article>
      <article class="metric-card"><span class="metric-card__label">行情新鲜度</span><strong class="metric-card__value">{{ freshnessLabel }}</strong><span class="metric-card__description">{{ selection.diagnostics.age_seconds === null ? '—' : `${selection.diagnostics.age_seconds.toFixed(1)}s` }}</span></article>
    </section>

    <section class="panel"><h2>本次运行时间</h2><el-descriptions :column="3" border><el-descriptions-item label="慢层 PIT 时点">{{ formatLocalTime(selection.as_of) }}</el-descriptions-item><el-descriptions-item label="实时流水线计算时点">{{ formatLocalTime(selection.calculation_at) }}</el-descriptions-item><el-descriptions-item label="行情进入 provider boundary">{{ formatLocalTime(selection.diagnostics.capture_ingested_at) }}</el-descriptions-item></el-descriptions></section>
    <section class="panel"><h2>行情采集与新鲜度</h2><el-descriptions :column="3" border><el-descriptions-item label="采集范围">{{ selection.diagnostics.capture_scope ?? '—' }}</el-descriptions-item><el-descriptions-item label="采集来源">{{ selection.diagnostics.capture_source ?? '—' }}</el-descriptions-item><el-descriptions-item label="收到行情">{{ selection.diagnostics.received_quotes }}</el-descriptions-item><el-descriptions-item label="可用源时间戳">{{ selection.diagnostics.source_timestamp_available_quotes }}</el-descriptions-item><el-descriptions-item label="持久化行情">{{ selection.diagnostics.persisted_quotes }}</el-descriptions-item><el-descriptions-item label="新鲜度允许">{{ selection.diagnostics.freshness_allowed ? '是' : '否' }}</el-descriptions-item></el-descriptions><p class="provenance">新鲜度由 API 判定为“{{ freshnessLabel }}”；age_seconds 仅作信息展示，不参与前端计算。</p><p class="provenance">persisted_quotes = {{ selection.diagnostics.persisted_quotes }}，本次全市场采集未持久化。</p></section>
    <section class="panel"><h2>流水线阶段</h2><div class="stage-grid"><article v-for="stage in stages" :key="stage[0]" class="stage-card"><strong>{{ stage[0] }}</strong><el-tag :type="stage[1] ? 'success' : 'warning'">{{ stage[1] ? '已就绪' : '已阻塞' }}</el-tag><p v-if="stage[2].length" class="provenance">{{ stage[2].join(', ') }}</p><p v-else class="provenance">无 blocker</p></article></div><p v-if="selection.blockers.length" class="provenance">Top100 根 blocker：{{ selection.blockers.join(', ') }}</p></section>
    <section class="panel"><el-collapse><el-collapse-item title="只读策略审计" name="policy"><el-descriptions :column="3" border><el-descriptions-item label="Candidate 最低 BaseScore">{{ score(selection.policy.candidate_min_base_score) }}</el-descriptions-item><el-descriptions-item label="Candidate top fraction">{{ percent(selection.policy.candidate_top_fraction) }}</el-descriptions-item><el-descriptions-item label="新鲜度 normal / warning">{{ selection.policy.freshness_normal_max_seconds }}s / {{ selection.policy.freshness_warning_max_seconds }}s</el-descriptions-item><el-descriptions-item label="强变动 / 换手 / 量比">{{ selection.policy.strong_move_pct }}% / {{ selection.policy.high_turnover_rate_pct }}% / {{ selection.policy.high_volume_ratio }}x</el-descriptions-item><el-descriptions-item label="RealTimeScore 权重">Base {{ percent(selection.policy.realtime_base_weight) }} / Intraday {{ percent(selection.policy.realtime_intraday_weight) }}</el-descriptions-item><el-descriptions-item label="选择门槛 / TopN">{{ score(selection.policy.min_intraday_score) }} / {{ selection.policy.top_n }}</el-descriptions-item><el-descriptions-item label="RS / Activity">{{ percent(selection.policy.relative_strength.weight) }} / {{ percent(selection.policy.activity_liquidity.weight) }}</el-descriptions-item><el-descriptions-item label="VWAP / Short Momentum">{{ percent(selection.policy.vwap_trend.weight) }} / {{ percent(selection.policy.short_momentum.weight) }}</el-descriptions-item><el-descriptions-item label="Risk Stability">{{ percent(selection.policy.risk_stability.weight) }}</el-descriptions-item></el-descriptions></el-collapse-item></el-collapse></section>

    <section v-if="!selection.selection_ready" class="panel"><EmptyState title="实时选股尚未就绪" description="本次 HTTP 请求成功，但实时流水线未满足官方就绪条件；请查看上方保留的 blocker 与阶段诊断。" /></section>
    <section v-else-if="selection.items.length === 0" class="panel"><EmptyState title="当前规则下暂无 Top100 入选股票" description="实时流水线已完成，但当前候选 / IntradayScore 门槛下没有最终入选项。" /></section>
    <section v-else class="panel">
      <h2>RealtimeScore Top {{ selection.diagnostics.selected_items }}</h2><p class="provenance">官方顺序由后端 Task22 提供；页面不重新评分、过滤、排序或改变排名。</p><p class="provenance">“—”表示当前证据不可用，不等于 0 分。实时评分和排序用于量化研究，不构成投资建议；行情由当前 provider 获取，本页并不代表交易所直连行情。</p>
      <el-table :data="selection.items" class="instrument-table" @row-click="openInstrument">
        <el-table-column type="expand"><template #default="scope"><div class="realtime-audit"><div><h3>实时行情</h3><div class="quote-grid"><div><span>最新价</span><strong>{{ formatNumber(scope.row.quote.price) }}</strong></div><div><span>开 / 高 / 低</span><strong>{{ formatNumber(scope.row.quote.open) }} / {{ formatNumber(scope.row.quote.high) }} / {{ formatNumber(scope.row.quote.low) }}</strong></div><div><span>昨收 / 涨跌幅</span><strong :class="changeClass(scope.row.quote.change_pct)">{{ formatNumber(scope.row.quote.prev_close) }} / {{ quotePercent(scope.row.quote.change_pct) }}</strong></div><div><span>换手 / 量比</span><strong>{{ quotePercent(scope.row.quote.turnover_rate) }} / {{ ratio(scope.row.quote.volume_ratio) }}</strong></div></div><p class="provenance">来源：{{ scope.row.quote.source }} · 源时间：{{ formatLocalTime(scope.row.quote.source_timestamp) }} · 进入时间：{{ formatLocalTime(scope.row.quote.ingested_at) }}</p></div><div><h3>日内因子</h3><el-descriptions :column="3" border><el-descriptions-item label="Relative Strength">{{ score(scope.row.relative_strength_score) }}</el-descriptions-item><el-descriptions-item label="Activity / Liquidity">{{ score(scope.row.activity_liquidity_score) }}</el-descriptions-item><el-descriptions-item label="VWAP / Trend">{{ score(scope.row.vwap_trend_score) }}</el-descriptions-item><el-descriptions-item label="Short Momentum">{{ score(scope.row.short_momentum_score) }}</el-descriptions-item><el-descriptions-item label="Risk / Stability">{{ score(scope.row.risk_stability_score) }}</el-descriptions-item></el-descriptions></div><div><h3>评分证据质量</h3><el-descriptions :column="3" border><el-descriptions-item label="Base 完整度 / 置信度">{{ percent(scope.row.base_data_completeness) }} / {{ percent(scope.row.base_confidence) }}</el-descriptions-item><el-descriptions-item label="Intraday 完整度 / 置信度">{{ percent(scope.row.intraday_data_completeness) }} / {{ percent(scope.row.intraday_confidence) }}</el-descriptions-item><el-descriptions-item label="Intraday confidence-adjusted">{{ score(scope.row.intraday_confidence_adjusted_score) }}</el-descriptions-item><el-descriptions-item label="Realtime 完整度 / 置信度">{{ percent(scope.row.realtime_data_completeness) }} / {{ percent(scope.row.realtime_confidence) }}</el-descriptions-item><el-descriptions-item label="Realtime confidence-adjusted">{{ score(scope.row.realtime_confidence_adjusted_score) }}</el-descriptions-item></el-descriptions></div><div><h3>元数据</h3><p class="provenance">board：{{ scope.row.board }} · industry_key：{{ scope.row.industry_key ?? '—' }} · market_rank：{{ scope.row.market_rank }} · realtime_rank：{{ scope.row.realtime_rank }}</p></div></div></template></el-table-column>
        <el-table-column prop="realtime_rank" label="实时排名" width="86" /><el-table-column prop="market_rank" label="市场候选排名" width="112" /><el-table-column prop="symbol" label="代码" min-width="108" /><el-table-column prop="name" label="名称" min-width="104" /><el-table-column label="最新价" width="88"><template #default="scope">{{ formatNumber(scope.row.quote.price) }}</template></el-table-column><el-table-column label="涨跌幅" width="92"><template #default="scope"><span :class="changeClass(scope.row.quote.change_pct)">{{ quotePercent(scope.row.quote.change_pct) }}</span></template></el-table-column><el-table-column label="BaseScore" width="92"><template #default="scope">{{ score(scope.row.base_score) }}</template></el-table-column><el-table-column label="IntradayScore" width="112"><template #default="scope">{{ score(scope.row.intraday_score) }}</template></el-table-column><el-table-column label="RealTimeScore" width="114"><template #default="scope">{{ score(scope.row.realtime_score) }}</template></el-table-column><el-table-column label="行业" min-width="146"><template #default="scope">{{ scope.row.industry_key ?? '—' }}</template></el-table-column>
      </el-table>
    </section>
  </template>
</template>

<style scoped>
.stage-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.stage-card { display:flex; min-height:96px; flex-direction:column; gap:8px; padding:13px; border:1px solid var(--border); border-radius:8px; }
.stage-card .provenance { margin:0; overflow-wrap:anywhere; }
.realtime-audit { display:grid; gap:18px; padding:8px 18px 18px; }
.realtime-audit h3 { margin:0 0 10px; font-size:14px; }
@media (max-width:1440px) { .stage-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
