<script setup lang="ts">
import type { DailySelectionItemResponse } from '@/api/types'

defineProps<{ item: DailySelectionItemResponse }>()

function score(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

function percent(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

function riskTagType(
  severity: DailySelectionItemResponse['risks'][number]['severity'],
): 'danger' | 'warning' | 'info' {
  if (severity === 'high') return 'danger'
  return severity
}
</script>

<template>
  <section data-testid="selection-item-explainability" class="selection-explanation">
    <div>
      <h3>官方排名与评分</h3>
      <p>排名：{{ item.rank }}</p>
      <p>BaseScore：{{ score(item.base_score) }}</p>
      <p>Confidence Adj.：{{ score(item.confidence_adjusted_score) }}</p>
      <p>数据完整度：{{ percent(item.data_completeness) }}</p>
      <p>置信度：{{ percent(item.confidence) }}</p>
      <p class="provenance">官方排名按 BaseScore；Confidence Adj. 仅供展示，不参与官方排序。</p>
    </div>

    <div>
      <h3>五因子评分</h3>
      <p data-testid="factor-quality">Quality：{{ score(item.quality_score) }}</p>
      <p data-testid="factor-value">Value：{{ score(item.value_score) }}</p>
      <p data-testid="factor-growth">Growth：{{ score(item.growth_score) }}</p>
      <p data-testid="factor-momentum">Momentum：{{ score(item.momentum_score) }}</p>
      <p data-testid="factor-low-volatility">LowVol：{{ score(item.low_volatility_score) }}</p>
    </div>

    <div>
      <h3>结构化选股依据</h3>
      <template v-if="item.evidence.length">
        <article v-for="(evidence, index) in item.evidence" :key="evidence.code" :data-testid="`evidence-item-${index}`">
          <p>代码：{{ evidence.code }}</p>
          <p>{{ evidence.message }}</p>
          <p>因子：{{ evidence.factor_name ?? '—' }}</p>
          <p>值：{{ evidence.value ?? '—' }}</p>
          <p>百分位：{{ evidence.percentile ?? '—' }}</p>
          <p>贡献：{{ evidence.contribution ?? '—' }}</p>
        </article>
      </template>
      <p v-else data-testid="evidence-empty">未提供结构化选股依据；界面不会自行推断原因。</p>
    </div>

    <div>
      <h3>数据与模型限制</h3>
      <template v-if="item.risks.length">
        <article v-for="(risk, index) in item.risks" :key="risk.code" :data-testid="`risk-item-${index}`">
          <p>代码：{{ risk.code }}</p>
          <p><el-tag size="small" :type="riskTagType(risk.severity)">{{ risk.severity }}</el-tag></p>
          <p>{{ risk.message }}</p>
        </article>
      </template>
      <p v-else data-testid="risk-empty">未生成额外数据/模型限制标签；不代表证券无投资风险。</p>
    </div>

    <p class="provenance">本说明反映结构化选股依据和已知数据/模型限制，不是买卖信号，也不构成投资建议。</p>
  </section>
</template>
