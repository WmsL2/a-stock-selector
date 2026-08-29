import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '@/layouts/MainLayout.vue'
import BacktestView from '@/views/BacktestView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DataCenterView from '@/views/DataCenterView.vue'
import DailySelectionView from '@/views/DailySelectionView.vue'
import FactorResearchView from '@/views/FactorResearchView.vue'
import InstrumentDetailView from '@/views/InstrumentDetailView.vue'
import InstrumentsView from '@/views/InstrumentsView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import RealtimeSelectionView from '@/views/RealtimeSelectionView.vue'
import SettingsView from '@/views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', name: 'dashboard', component: DashboardView },
        { path: 'daily-selection', name: 'daily-selection', component: DailySelectionView },
        { path: 'realtime-selection', name: 'realtime-selection', component: RealtimeSelectionView },
        { path: 'stocks', name: 'instruments', component: InstrumentsView },
        { path: 'stocks/:symbol', name: 'instrument-detail', component: InstrumentDetailView },
        { path: 'factors', name: 'factors', component: FactorResearchView },
        { path: 'backtest', name: 'backtest', component: BacktestView },
        { path: 'data-center', name: 'data-center', component: DataCenterView },
        { path: 'settings', name: 'settings', component: SettingsView },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
  ],
})

export default router
