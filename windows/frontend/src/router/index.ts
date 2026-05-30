import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import DeviceDetail from '@/views/DeviceDetail.vue'
import DataStream from '@/views/DataStream.vue'
import Settings from '@/views/Settings.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/device', name: 'device', component: DeviceDetail },
    { path: '/stream', name: 'stream', component: DataStream },
    { path: '/settings', name: 'settings', component: Settings },
  ],
})

export default router
