<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listInstruments } from '@/api/instruments'
import type { InstrumentResponse } from '@/api/types'

const router = useRouter()
const search = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const items = ref<InstrumentResponse[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

async function loadInstruments(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const response = await listInstruments({
      q: search.value.trim() || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = response.items
    total.value = response.total
  } catch {
    items.value = []
    total.value = 0
    error.value = '无法读取本地股票基础信息。'
  } finally {
    loading.value = false
  }
}

function submitSearch(): void {
  page.value = 1
  void loadInstruments()
}

function openInstrument(row: InstrumentResponse): void {
  void router.push({ name: 'instrument-detail', params: { symbol: row.symbol } })
}

onMounted(() => void loadInstruments())
</script>

<template>
  <section class="page-heading"><div><p class="eyebrow">LOCAL INSTRUMENT MASTER</p><h1>股票中心</h1><p>本地基础信息状态，不代表实时交易状态。</p></div></section>
  <section class="panel">
    <el-form inline @submit.prevent="submitSearch">
      <el-form-item label="代码或名称">
        <el-input v-model="search" placeholder="例如 600519 或 贵州茅台" clearable @keyup.enter="submitSearch" />
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="submitSearch">搜索</el-button>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-table v-else v-loading="loading" :data="items" class="instrument-table" @row-click="openInstrument">
      <el-table-column prop="symbol" label="代码" min-width="118" />
      <el-table-column prop="name" label="名称" min-width="130" />
      <el-table-column prop="exchange" label="交易所" width="88" />
      <el-table-column prop="board" label="板块" min-width="100" />
      <el-table-column prop="listing_date" label="上市日期" min-width="112" />
      <el-table-column prop="status" label="本地基础信息状态" min-width="140" />
    </el-table>
    <el-empty v-if="!loading && !error && items.length === 0" description="未找到符合条件的本地股票信息" />
    <div class="pagination-row">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next" @current-change="loadInstruments" @size-change="submitSearch" />
    </div>
  </section>
</template>
