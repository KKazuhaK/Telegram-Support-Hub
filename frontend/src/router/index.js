import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Roles that should be sent to the focused agent workspace instead of
// the full admin Layout on login. Admins/supervisors keep the full
// view; merchant/business_agent get the admin Layout with their menu
// items hidden by adminOnly checks (they still need the management
// pages to administer their own scope).
const CONSOLE_ROLES = new Set(['agent'])

function landingRouteFor(auth) {
  if (auth.actorKind === 'support_agent' && CONSOLE_ROLES.has(auth.role)) {
    return { name: 'console' }
  }
  return { name: 'dashboard' }
}

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    // Focused workspace for support_agent (role=agent). Admins and
    // supervisors can also reach it via the user menu if they want to
    // pinch-hit on chat; their main entry point remains '/'.
    path: '/console',
    name: 'console',
    component: () => import('@/views/ConsoleLayout.vue'),
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      { path: '', redirect: { name: 'dashboard' } },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'accounts', name: 'accounts', component: () => import('@/views/Accounts.vue'), meta: { title: '账号管理' } },
      { path: 'account-groups', name: 'account-groups', component: () => import('@/views/AccountGroups.vue'), meta: { title: '账号分组' } },
      { path: 'friends', name: 'friends', component: () => import('@/views/Friends.vue'), meta: { title: '好友列表' } },
      { path: 'business-agents', name: 'business-agents', component: () => import('@/views/BusinessAgents.vue'), meta: { title: '商务代理', adminOnly: true } },
      { path: 'merchants', name: 'merchants', component: () => import('@/views/Merchants.vue'), meta: { title: '商家账号', adminOnly: true } },

      // 任务管理
      { path: 'batch-operations', name: 'batch-operations', component: () => import('@/views/BatchOperations.vue'), meta: { title: '批量操作' } },
      { path: 'modify-info', name: 'modify-info', component: () => import('@/views/ModifyInfo.vue'), meta: { title: '修改资料' } },
      { path: 'campaigns', name: 'campaigns', component: () => import('@/views/Campaigns.vue'), meta: { title: '批量群发' } },
      { path: 'templates', name: 'templates', component: () => import('@/views/Templates.vue'), meta: { title: '消息模板' } },
      { path: 'replies', name: 'replies', component: () => import('@/views/Replies.vue'), meta: { title: '回复管理' } },

      // 任务统计
      { path: 'task-stats', name: 'task-stats', component: () => import('@/views/TaskStats.vue'), meta: { title: '任务统计' } },

      // 日志记录
      { path: 'task-log', name: 'task-log', component: () => import('@/views/TaskLog.vue'), meta: { title: '任务日志', adminOnly: true } },
      { path: 'io-log', name: 'io-log', component: () => import('@/views/ImportExportLog.vue'), meta: { title: '导入导出', adminOnly: true } },
      { path: 'audit-logs', name: 'audit-logs', component: () => import('@/views/AuditLogs.vue'), meta: { title: '审计日志', adminOnly: true } },

      // 客服中心
      { path: 'agents', name: 'agents', component: () => import('@/views/Agents.vue'), meta: { title: '客服列表', adminOnly: true } },

      // 数据管理
      { path: 'customers', name: 'customers', component: () => import('@/views/Customers.vue'), meta: { title: '客户管理' } },
      { path: 'phones', name: 'phones', component: () => import('@/views/Phones.vue'), meta: { title: '号码数据' } },
      { path: 'materials', name: 'materials', component: () => import('@/views/Materials.vue'), meta: { title: '文本数据' } },
      { path: 'files', name: 'files', component: () => import('@/views/Files.vue'), meta: { title: '文件管理', adminOnly: true } },
      { path: 'proxies', name: 'proxies', component: () => import('@/views/Proxies.vue'), meta: { title: '代理IP管理', adminOnly: true } },
      { path: 'settings', name: 'settings', component: () => import('@/views/Settings.vue'), meta: { title: '系统设置', adminOnly: true } },
    ],
  },
  // Catch-all: send to the right landing based on actor role.
  { path: '/:pathMatch(.*)*', redirect: (_to) => {
      const auth = useAuthStore()
      return auth.isAuthenticated ? landingRouteFor(auth) : { name: 'login' }
    }
  },
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
    return landingRouteFor(auth)
  }
  if (to.meta.adminOnly && !auth.isAdmin) {
    return landingRouteFor(auth)
  }
  // Plain support_agents shouldn't see the admin dashboard; route them
  // to the console even if they hit '/' directly.
  if (auth.actorKind === 'support_agent' && CONSOLE_ROLES.has(auth.role)
      && to.path !== '/console' && to.name !== 'login') {
    return { name: 'console' }
  }
  return true
})

export default router
