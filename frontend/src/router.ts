import { createRouter, createWebHistory } from 'vue-router'

import GuideView from './views/GuideView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import StatusView from './views/StatusView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'guide', component: GuideView },
    { path: '/knowledge', name: 'knowledge', component: KnowledgeView },
    { path: '/status', name: 'status', component: StatusView },
  ],
})

export default router

