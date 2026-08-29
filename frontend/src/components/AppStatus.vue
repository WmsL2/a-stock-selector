<script setup lang="ts">
import { storeToRefs } from 'pinia'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const { apiOnline, loading } = storeToRefs(appStore)
</script>

<template>
  <div class="app-status" aria-live="polite">
    <el-tag v-if="loading" type="info" effect="dark">API：检查中</el-tag>
    <el-tag v-else-if="apiOnline" type="success" effect="dark">API：在线</el-tag>
    <el-tag v-else type="danger" effect="dark">API：离线</el-tag>
    <el-button link type="primary" :loading="loading" @click="appStore.refreshStatus">
      重新检查
    </el-button>
  </div>
</template>
