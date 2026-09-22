import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'

import SelectionItemExplainability from '@/components/SelectionItemExplainability.vue'
import type { DailySelectionItemResponse } from '@/api/types'

const item: DailySelectionItemResponse = {
  rank: 2,
  symbol: '600519.SH',
  name: '贵州茅台',
  board: 'sh_main',
  industry_code: 'C15',
  industry_name: '饮料制造',
  base_score: 72.5,
  confidence_adjusted_score: 58,
  data_completeness: 0.75,
  confidence: 0.8,
  quality_score: 81,
  value_score: 70,
  growth_score: 68,
  momentum_score: null,
  low_volatility_score: null,
  evidence: [
    { code: 'z_second', message: '第二条依据', factor_name: null, value: null, percentile: null, contribution: null },
    { code: 'a_first', message: '第一条依据', factor_name: 'quality', value: 81, percentile: 90, contribution: 34 },
  ],
  risks: [
    { code: 'info_code', message: '信息限制', severity: 'info' },
    { code: 'high_code', message: '高优先级限制', severity: 'high' },
    { code: 'warning_code', message: '警告限制', severity: 'warning' },
  ],
}

function mountComponent(value: DailySelectionItemResponse = item) {
  return mount(SelectionItemExplainability, {
    props: { item: value },
    global: { plugins: [ElementPlus] },
  })
}

describe('SelectionItemExplainability', () => {
  it('renders official score context and fixed factor order without converting nulls to zero', () => {
    const wrapper = mountComponent()
    const text = wrapper.text()

    expect(text).toContain('排名：2')
    expect(text).toContain('BaseScore：72.5')
    expect(text).toContain('Confidence Adj.：58.0')
    expect(text).toContain('数据完整度：75%')
    expect(text).toContain('置信度：80%')
    expect(text).toContain('官方排名按 BaseScore；Confidence Adj. 仅供展示，不参与官方排序。')
    expect(text.indexOf('Quality')).toBeLessThan(text.indexOf('Value'))
    expect(text.indexOf('Value')).toBeLessThan(text.indexOf('Growth'))
    expect(text.indexOf('Growth')).toBeLessThan(text.indexOf('Momentum'))
    expect(text.indexOf('Momentum')).toBeLessThan(text.indexOf('LowVol'))
    expect(wrapper.get('[data-testid="factor-momentum"]').text()).toContain('—')
    expect(wrapper.get('[data-testid="factor-low-volatility"]').text()).toContain('—')
  })

  it('preserves structured evidence order and displays raw audit fields without synthetic values', () => {
    const wrapper = mountComponent()
    const first = wrapper.get('[data-testid="evidence-item-0"]').text()
    const second = wrapper.get('[data-testid="evidence-item-1"]').text()

    expect(first).toContain('z_second')
    expect(first).toContain('第二条依据')
    expect(first).toContain('因子：—')
    expect(first).toContain('值：—')
    expect(second).toContain('a_first')
    expect(second).toContain('第一条依据')
    expect(second).toContain('因子：quality')
    expect(second).toContain('值：81')
    expect(second).toContain('百分位：90')
    expect(second).toContain('贡献：34')
  })

  it('preserves risk order, raw codes and severities, plus explicit empty states and disclosure', () => {
    const wrapper = mountComponent()
    const text = wrapper.text()

    expect(text.indexOf('info_code')).toBeLessThan(text.indexOf('high_code'))
    expect(text.indexOf('high_code')).toBeLessThan(text.indexOf('warning_code'))
    expect(wrapper.get('[data-testid="risk-item-0"]').text()).toContain('info')
    expect(wrapper.get('[data-testid="risk-item-1"]').text()).toContain('高优先级限制')
    expect(text).toContain('不是买卖信号，也不构成投资建议。')

    const empty = mountComponent({ ...item, evidence: [], risks: [] })
    expect(empty.get('[data-testid="evidence-empty"]').text()).toContain('未提供结构化选股依据')
    expect(empty.get('[data-testid="risk-empty"]').text()).toContain('不代表证券无投资风险')
  })
})
