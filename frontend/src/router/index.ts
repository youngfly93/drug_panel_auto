import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/',
      component: () => import('@/components/common/AppLayout.vue'),
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },
        {
          path: 'generate',
          name: 'generate',
          component: () => import('@/views/ReportGenerateView.vue'),
        },
        {
          path: 'patients',
          name: 'patients',
          component: () => import('@/views/PatientInfoView.vue'),
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/KnowledgeBaseView.vue'),
        },
        {
          path: 'config',
          name: 'config',
          component: () => import('@/views/ConfigEditorView.vue'),
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: () => import('@/views/TaskQueueView.vue'),
        },
      ],
    },
  ],
})

export default router
