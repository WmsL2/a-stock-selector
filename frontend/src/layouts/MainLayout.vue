<script setup lang="ts">
import {
  DataAnalysis,
  DataBoard,
  DocumentChecked,
  Histogram,
  Monitor,
  Setting,
  TrendCharts,
} from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import AppStatus from '@/components/AppStatus.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const { sidebarCollapsed } = storeToRefs(appStore)
const route = useRoute()
const activeMenu = computed(() => (route.path.startsWith('/stocks') ? '/stocks' : route.path))

onMounted(() => appStore.ensureStatus())
</script>

<template>
  <el-container class="application-shell">
    <el-aside :width="sidebarCollapsed ? '64px' : '216px'" class="navigation-aside">
      <div class="brand-mark" :title="sidebarCollapsed ? 'A股量化选股系统' : undefined">
        <span>A</span>
        <strong v-if="!sidebarCollapsed">A股量化选股</strong>
      </div>
      <el-menu router :collapse="sidebarCollapsed" :collapse-transition="false" :default-active="activeMenu">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>总览</span></el-menu-item>
        <el-menu-item index="/daily-selection"><el-icon><DocumentChecked /></el-icon><span>今日选股</span></el-menu-item>
        <el-menu-item index="/realtime-selection"><el-icon><TrendCharts /></el-icon><span>实时选股</span></el-menu-item>
        <el-menu-item index="/stocks"><el-icon><Histogram /></el-icon><span>股票中心</span></el-menu-item>
        <el-menu-item index="/factors"><el-icon><DataAnalysis /></el-icon><span>因子研究</span></el-menu-item>
        <el-menu-item index="/backtest"><el-icon><DataBoard /></el-icon><span>回测中心</span></el-menu-item>
        <el-menu-item index="/data-center"><el-icon><DataBoard /></el-icon><span>数据中心</span></el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="application-header">
        <el-button text @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '展开导航' : '收起导航' }}
        </el-button>
        <AppStatus />
      </el-header>
      <el-main class="application-main"><RouterView /></el-main>
    </el-container>
  </el-container>
</template>
