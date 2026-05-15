import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      { path: '', redirect: { name: 'dashboard' } },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'accounts', name: 'accounts', component: () => import('@/views/Accounts.vue'), meta: { title: 'TG 账号' } },
      { path: 'account-groups', name: 'account-groups', component: () => import('@/views/AccountGroups.vue'), meta: { title: '账号分组' } },
      { path: 'proxies', name: 'proxies', component: () => import('@/views/Proxies.vue'), meta: { title: '网络代理' } },
      { path: 'customers', name: 'customers', component: () => import('@/views/Customers.vue'), meta: { title: '客户管理' } },
      { path: 'friends', name: 'friends', component: () => import('@/views/Friends.vue'), meta: { title: '好友列表' } },
      { path: 'templates', name: 'templates', component: () => import('@/views/Templates.vue'), meta: { title: '消息模板' } },
      { path: 'campaigns', name: 'campaigns', component: () => import('@/views/Campaigns.vue'), meta: { title: '群发任务' } },
      { path: 'replies', name: 'replies', component: () => import('@/views/Replies.vue'), meta: { title: '回复管理' } },
      { path: 'agents', name: 'agents', component: () => import('@/views/Agents.vue'), meta: { title: '客服中心', adminOnly: true } },
      { path: 'audit-logs', name: 'audit-logs', component: () => import('@/views/AuditLogs.vue'), meta: { title: '审计日志', adminOnly: true } },
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
  if (to.meta.adminOnly && !auth.isAdmin) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
