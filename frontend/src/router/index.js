import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      { path: '', redirect: { name: 'dashboard' } },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'accounts', name: 'accounts', component: () => import('@/views/Accounts.vue') },
      { path: 'account-groups', name: 'account-groups', component: () => import('@/views/AccountGroups.vue') },
      { path: 'proxies', name: 'proxies', component: () => import('@/views/Proxies.vue') },
      { path: 'customers', name: 'customers', component: () => import('@/views/Customers.vue') },
      { path: 'templates', name: 'templates', component: () => import('@/views/Templates.vue') },
      { path: 'campaigns', name: 'campaigns', component: () => import('@/views/Campaigns.vue') },
      { path: 'replies', name: 'replies', component: () => import('@/views/Replies.vue') },
      { path: 'agents', name: 'agents', component: () => import('@/views/Agents.vue') },
      { path: 'audit-logs', name: 'audit-logs', component: () => import('@/views/AuditLogs.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
]

const router = createRouter({
  history: createWebHistory('/'),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
