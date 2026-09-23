<script setup lang="ts">
import { ref } from 'vue'

import { getSelectionResearchCompare, getSelectionResearchItems, selectionResearchItemsDownloadUrl } from '@/api/selection'
import type { SelectionResearchComparisonResponse, SelectionResearchItemQueryResponse } from '@/api/types'
import SelectionItemExplainability from '@/components/SelectionItemExplainability.vue'

const startDate = ref('')
const endDate = ref('')
const strategyName = ref('')
const query = ref('')
const board = ref('')
const industryCode = ref('')
const maxRank = ref<number | undefined>()
const itemsLoading = ref(false)
const itemsError = ref<string | null>(null)
const itemsResponse = ref<SelectionResearchItemQueryResponse | null>(null)
const appliedItemsParams = ref<Parameters<typeof getSelectionResearchItems>[0] | null>(null)
const previousDate = ref('')
const currentDate = ref('')
const compareLoading = ref(false)
const compareError = ref<string | null>(null)
const compareResponse = ref<SelectionResearchComparisonResponse | null>(null)

function textParam(value: string): string | undefined {
  return value.trim() || undefined
}

function itemParams(): Parameters<typeof getSelectionResearchItems>[0] {
  const start_date = textParam(startDate.value)
  const end_date = textParam(endDate.value)
  const strategy_name = textParam(strategyName.value)
  const q = textParam(query.value)
  const item_board = textParam(board.value)
  const industry_code = textParam(industryCode.value)
  return {
    ...(start_date ? { start_date } : {}),
    ...(end_date ? { end_date } : {}),
    ...(strategy_name ? { strategy_name } : {}),
    ...(q ? { q } : {}),
    ...(item_board ? { board: item_board } : {}),
    ...(industry_code ? { industry_code } : {}),
    ...(maxRank.value === undefined ? {} : { max_rank: maxRank.value }),
  }
}

async function loadItems(): Promise<void> {
  const params = itemParams()
  itemsLoading.value = true
  itemsError.value = null
  try {
    itemsResponse.value = await getSelectionResearchItems(params)
    appliedItemsParams.value = params
  } catch {
    itemsError.value = '无法读取筛选后的选股研究项。'
  } finally {
    itemsLoading.value = false
  }
}

function download(format: 'json' | 'csv'): void {
  if (appliedItemsParams.value !== null) {
    window.open(selectionResearchItemsDownloadUrl(format, appliedItemsParams.value), '_blank')
  }
}

async function loadComparison(): Promise<void> {
  compareLoading.value = true
  compareError.value = null
  try {
    compareResponse.value = await getSelectionResearchCompare({
      previous_date: previousDate.value,
      current_date: currentDate.value,
    })
  } catch {
    compareError.value = '无法读取指定选股研究快照比较；请确认两个日期均存在且前一期早于当前期。'
  } finally {
    compareLoading.value = false
  }
}

function score(value: number | null): string { return value === null ? '—' : value.toFixed(1) }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%` }
function stabilityPercent(value: number | null): string { return value === null ? '—' : `${(value * 100).toFixed(2)}%` }
function rankChange(value: number | null): string { return value === null ? '—' : value > 0 ? `+${value}` : String(value) }
</script>

<template>
  <section class="panel" data-testid="research-explorer">
    <h2>选股研究筛选与导出</h2>
    <el-form label-position="top">
      <el-form-item label="开始日期"><el-input v-model="startDate" data-testid="research-start-date-input" /></el-form-item>
      <el-form-item label="结束日期"><el-input v-model="endDate" data-testid="research-end-date-input" /></el-form-item>
      <el-form-item label="策略名称"><el-input v-model="strategyName" data-testid="research-strategy-input" /></el-form-item>
      <el-form-item label="代码或名称"><el-input v-model="query" data-testid="research-query-input" /></el-form-item>
      <el-form-item label="板块"><el-input v-model="board" data-testid="research-board-input" /></el-form-item>
      <el-form-item label="行业代码"><el-input v-model="industryCode" data-testid="research-industry-input" /></el-form-item>
      <el-form-item label="最大排名"><el-input-number v-model="maxRank" :min="1" data-testid="research-max-rank-input" /></el-form-item>
      <el-button type="primary" :loading="itemsLoading" data-testid="load-research-items" @click="loadItems">读取筛选结果</el-button>
      <el-button :disabled="appliedItemsParams === null" data-testid="research-export-json" @click="download('json')">导出 JSON</el-button>
      <el-button :disabled="appliedItemsParams === null" data-testid="research-export-csv" @click="download('csv')">导出 CSV</el-button>
    </el-form>
    <el-alert v-if="itemsError" :title="itemsError" type="error" :closable="false" />
    <template v-if="itemsResponse">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="快照数">{{ itemsResponse.snapshot_count }}</el-descriptions-item>
        <el-descriptions-item label="匹配快照数">{{ itemsResponse.matching_snapshot_count }}</el-descriptions-item>
        <el-descriptions-item label="选股项观测数">{{ itemsResponse.item_observation_count }}</el-descriptions-item>
      </el-descriptions>
      <p v-if="itemsResponse.snapshot_count === 0" data-testid="research-items-no-snapshots">所选快照条件下没有持久化的选股研究快照。</p>
      <p v-else-if="itemsResponse.item_observation_count === 0" data-testid="research-items-empty">范围内存在持久化快照，但没有符合当前项目过滤条件的选股项；阻断快照本身也不会生成选股项。</p>
      <el-table :data="itemsResponse.observations" class="instrument-table">
        <el-table-column type="expand"><template #default="scope"><SelectionItemExplainability :item="scope.row.item" /></template></el-table-column>
        <el-table-column prop="snapshot_as_of" label="快照时间" /><el-table-column prop="strategy_name" label="策略" />
        <el-table-column label="排名"><template #default="scope">{{ scope.row.item.rank }}</template></el-table-column>
        <el-table-column label="代码"><template #default="scope">{{ scope.row.item.symbol }}</template></el-table-column>
        <el-table-column label="名称"><template #default="scope">{{ scope.row.item.name }}</template></el-table-column>
        <el-table-column label="板块"><template #default="scope">{{ scope.row.item.board }}</template></el-table-column>
        <el-table-column label="行业"><template #default="scope">{{ scope.row.item.industry_name ?? '—' }}</template></el-table-column>
        <el-table-column label="BaseScore"><template #default="scope">{{ score(scope.row.item.base_score) }}</template></el-table-column>
        <el-table-column label="Confidence Adj."><template #default="scope">{{ score(scope.row.item.confidence_adjusted_score) }}</template></el-table-column>
        <el-table-column label="完整度"><template #default="scope">{{ percent(scope.row.item.data_completeness) }}</template></el-table-column>
        <el-table-column label="置信度"><template #default="scope">{{ percent(scope.row.item.confidence) }}</template></el-table-column>
      </el-table>
    </template>
  </section>

  <section class="panel" data-testid="research-comparison">
    <h2>指定快照比较</h2>
    <el-input v-model="previousDate" data-testid="compare-previous-date-input" placeholder="前一期日期" />
    <el-input v-model="currentDate" data-testid="compare-current-date-input" placeholder="当前期日期" />
    <el-button :loading="compareLoading" data-testid="load-research-comparison" @click="loadComparison">读取比较</el-button>
    <el-alert v-if="compareError" :title="compareError" type="error" :closable="false" />
    <template v-if="compareResponse">
      <p>{{ compareResponse.previous_snapshot.as_of }} → {{ compareResponse.current_snapshot.as_of }}</p>
      <p>策略：{{ compareResponse.previous_snapshot.strategy_name }} → {{ compareResponse.current_snapshot.strategy_name }}</p>
      <p>前期状态：{{ compareResponse.previous_snapshot.selection_ready ? '已就绪' : '已阻断' }}；阻断：{{ compareResponse.previous_snapshot.blockers.join(', ') || 'none' }}；刷新采集：{{ compareResponse.previous_snapshot.refresh_had_collection_failures ? '包含失败' : '无嵌套失败' }}</p>
      <p>当前状态：{{ compareResponse.current_snapshot.selection_ready ? '已就绪' : '已阻断' }}；阻断：{{ compareResponse.current_snapshot.blockers.join(', ') || 'none' }}；刷新采集：{{ compareResponse.current_snapshot.refresh_had_collection_failures ? '包含失败' : '无嵌套失败' }}</p>
      <el-table :data="compareResponse.previous_snapshot.items" data-testid="compare-previous-items"><el-table-column prop="rank" label="排名" /><el-table-column prop="symbol" label="代码" /><el-table-column prop="name" label="名称" /></el-table>
      <el-table :data="compareResponse.current_snapshot.items" data-testid="compare-current-items"><el-table-column prop="rank" label="排名" /><el-table-column prop="symbol" label="代码" /><el-table-column prop="name" label="名称" /></el-table>
      <article data-testid="comparison-transition">
        <p>可比较：{{ compareResponse.transition.comparable ? '是' : '否' }}</p>
        <p>比较阻断：{{ compareResponse.transition.comparison_blockers.join(', ') || 'none' }}</p>
        <p>前期 / 当前选股项：{{ compareResponse.transition.previous_item_count }} / {{ compareResponse.transition.current_item_count }}</p>
        <template v-if="compareResponse.transition.comparable">
          <p>保留 / 新进入选股名单 / 退出选股名单：{{ compareResponse.transition.retained_count }} / {{ compareResponse.transition.entered_count }} / {{ compareResponse.transition.exited_count }}</p>
          <p>保留率：{{ stabilityPercent(compareResponse.transition.retention_rate) }}；重叠率：{{ stabilityPercent(compareResponse.transition.overlap_rate) }}</p>
          <el-table :data="compareResponse.transition.movements"><el-table-column label="状态"><template #default="scope"><span :data-testid="`comparison-movement-${scope.$index}`">{{ scope.row.status }}</span></template></el-table-column><el-table-column prop="symbol" label="代码" /><el-table-column prop="name" label="名称" /><el-table-column label="前期排名"><template #default="scope">{{ scope.row.previous_rank ?? '—' }}</template></el-table-column><el-table-column label="当前排名"><template #default="scope">{{ scope.row.current_rank ?? '—' }}</template></el-table-column><el-table-column label="排名变化"><template #default="scope">{{ rankChange(scope.row.rank_change) }}</template></el-table-column></el-table>
        </template>
        <p v-else>指定快照可以并列查看，但由于选股阻断或策略变化，不进行排名稳定性比较。</p>
      </article>
    </template>
  </section>
</template>
