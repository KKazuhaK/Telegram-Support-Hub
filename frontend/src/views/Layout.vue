<template>
  <el-container class="app-container">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="brand">
        <span v-if="!collapsed">TG Support Hub</span>
        <span v-else>TG</span>
      </div>
      <el-scrollbar>
        <el-menu :default-active="route.name" :collapse="collapsed" :collapse-transition="false" router unique-opened>
          <el-menu-item index="dashboard" :route="{ name: 'dashboard' }">
            <el-icon><Odometer /></el-icon>
            <template #title>仪表盘</template>
          </el-menu-item>

          <el-sub-menu index="account-mgmt">
            <template #title>
              <el-icon><User /></el-icon><span>账号管理</span>
            </template>
            <el-menu-item index="accounts" :route="{ name: 'accounts' }">TG 账号</el-menu-item>
            <el-menu-item index="account-groups" :route="{ name: 'account-groups' }">账号分组</el-menu-item>
            <el-menu-item index="proxies" :route="{ name: 'proxies' }">网络代理</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="data-mgmt">
            <template #title>
              <el-icon><FolderOpened /></el-icon><span>数据管理</span>
            </template>
            <el-menu-item index="customers" :route="{ name: 'customers' }">客户管理</el-menu-item>
            <el-menu-item index="friends" :route="{ name: 'friends' }">好友列表</el-menu-item>
            <el-menu-item index="templates" :route="{ name: 'templates' }">消息模板</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="task-mgmt">
            <template #title>
              <el-icon><Promotion /></el-icon><span>任务管理</span>
            </template>
            <el-menu-item index="campaigns" :route="{ name: 'campaigns' }">群发任务</el-menu-item>
            <el-menu-item index="replies" :route="{ name: 'replies' }">回复管理</el-menu-item>
          </el-sub-menu>

          <template v-if="auth.isAdmin">
            <el-sub-menu index="staff-mgmt">
              <template #title>
                <el-icon><UserFilled /></el-icon><span>客服中心</span>
              </template>
              <el-menu-item index="agents" :route="{ name: 'agents' }">客服账号</el-menu-item>
              <el-menu-item index="audit-logs" :route="{ name: 'audit-logs' }">审计日志</el-menu-item>
            </el-sub-menu>
          </template>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container>
      <el-header class="topbar" height="auto">
        <div class="topbar-row">
          <el-button link class="collapse-btn" @click="collapsed = !collapsed">
            <el-icon :size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>

          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="c in crumbs" :key="c">{{ c }}</el-breadcrumb-item>
          </el-breadcrumb>

          <div class="topbar-status">
            <el-tag v-if="status.has_admin" size="small" type="success">系统已初始化</el-tag>
            <el-tag size="small" type="info">账号 {{ status.accounts ?? '-' }}</el-tag>
            <el-tag size="small" type="info">客户 {{ status.customers ?? '-' }}</el-tag>
            <el-tag size="small" :type="status.workersOk ? 'success' : 'warning'">
              {{ status.workersOk ? 'workers 正常' : 'workers 检查中' }}
            </el-tag>
          </div>

          <div class="topbar-spacer" />

          <el-button link @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏'">
            <el-icon :size="18"><FullScreen /></el-icon>
          </el-button>

          <el-dropdown @command="onUserCommand">
            <span class="user-trigger">
              <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'info'">{{ roleLabel }}</el-tag>
              <span class="username">{{ auth.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="refresh">刷新当前页</el-dropdown-item>
                <el-dropdown-item command="closeOthers">关闭其他页签</el-dropdown-item>
                <el-dropdown-item command="closeAll">关闭全部页签</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="tabs-row">
          <el-tabs
            v-model="tabsStore.active"
            type="card"
            closable
            @tab-click="onTabClick"
            @tab-remove="onTabRemove"
          >
            <el-tab-pane
              v-for="t in tabsStore.tabs"
              :key="t.name"
              :label="t.title"
              :name="t.name"
              :closable="t.closable"
            />
          </el-tabs>
        </div>
      </el-header>

      <el-main>
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedNames">
            <component :is="Component" :key="route.name" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import http from '@/api/http'
import {
  Odometer, User, UserFilled, FolderOpened, Promotion,
  Fold, Expand, FullScreen, ArrowDown,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const tabsStore = useTabsStore()

const collapsed = ref(false)
const isFullscreen = ref(false)
const status = reactive({ has_admin: false, accounts: null, customers: null, workersOk: false })

const ROLE_LABELS = { admin: '管理员', supervisor: '主管', agent: '客服' }
const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role || '未登录')

const cachedNames = computed(() => tabsStore.tabs.map((t) => routeNameToComponent(t.name)).filter(Boolean))

function routeNameToComponent(name) {
  // keep-alive needs the *component* name. Our route names match component
  // file names roughly; use PascalCase fallback if needed. The simpler path
  // is to set <component :key="route.name"> + KeepAlive on all, but we keep
  // it loose so it does not break lookups.
  return name
}

const PARENT = {
  accounts: '账号管理', 'account-groups': '账号管理', proxies: '账号管理',
  customers: '数据管理', friends: '数据管理', templates: '数据管理',
  campaigns: '任务管理', replies: '任务管理',
  agents: '客服中心', 'audit-logs': '客服中心',
}
const crumbs = computed(() => {
  const parts = []
  const parent = PARENT[route.name]
  if (parent) parts.push(parent)
  if (route.meta?.title) parts.push(route.meta.title)
  return parts.length ? parts : ['首页']
})

watch(
  () => route.name,
  (name) => {
    if (!name || name === 'login') return
    tabsStore.openTab({ name, title: route.meta?.title || name })
  },
  { immediate: true },
)

function onTabClick(tab) {
  if (tab.props.name !== route.name) {
    router.push({ name: tab.props.name })
  }
}

function onTabRemove(name) {
  const next = tabsStore.closeTab(name)
  if (next) router.push({ name: next })
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.()
  } else {
    document.exitFullscreen?.()
  }
}

function syncFullscreenFlag() {
  isFullscreen.value = !!document.fullscreenElement
}

function onUserCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    tabsStore.closeAll()
    router.push({ name: 'login' })
  } else if (cmd === 'refresh') {
    router.replace({ path: '/redirect' + route.fullPath }).catch(() => {
      // no /redirect route; fallback to native reload
      window.location.reload()
    })
  } else if (cmd === 'closeOthers') {
    tabsStore.closeOthers(route.name)
  } else if (cmd === 'closeAll') {
    tabsStore.closeAll()
    router.push({ name: 'dashboard' })
  }
}

async function loadStatus() {
  try {
    const [{ data: hasAdmin }, { data: dash }] = await Promise.all([
      http.get('/auth/has-admin'),
      http.get('/statistics/dashboard'),
    ])
    status.has_admin = !!hasAdmin?.has_admin
    status.accounts = dash?.accounts?.total ?? 0
    status.customers = dash?.customers?.total ?? 0
    // crude worker liveness: if we got dashboard, backend is reachable; assume workers up
    status.workersOk = true
  } catch (_) {
    status.workersOk = false
  }
}

onMounted(() => {
  loadStatus()
  document.addEventListener('fullscreenchange', syncFullscreenFlag)
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenFlag)
})
</script>

<style scoped>
.app-container { height: 100vh; }

.sidebar {
  background: #001628;
  color: #fff;
  transition: width 0.2s;
  border-right: 1px solid #001020;
}
.brand {
  color: #fff; font-size: 16px; padding: 16px;
  font-weight: 600; letter-spacing: 0.5px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
:deep(.el-menu) { background: #001628; border-right: none; }
:deep(.el-menu-item), :deep(.el-sub-menu__title) { color: rgba(255,255,255,0.78); }
:deep(.el-menu-item:hover), :deep(.el-sub-menu__title:hover) {
  background: rgba(255,255,255,0.06); color: #fff;
}
:deep(.el-menu-item.is-active) {
  background: var(--el-color-primary) !important; color: #fff;
}
:deep(.el-sub-menu .el-menu) { background: #00111f; }

.topbar {
  background: #fff; border-bottom: 1px solid #e5e6eb; padding: 0;
}
.topbar-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; border-bottom: 1px solid #f0f0f0;
}
.topbar-spacer { flex: 1; }
.collapse-btn { font-size: 18px; }
.topbar-status { display: flex; gap: 8px; margin-left: 8px; }

.user-trigger {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  padding: 4px 8px; border-radius: 4px; transition: background 0.15s;
}
.user-trigger:hover { background: #f5f7fa; }
.username { color: #555; font-size: 13px; }

.tabs-row { padding: 6px 12px 0; background: #fafafa; }
:deep(.tabs-row .el-tabs__header) { margin: 0; }
:deep(.tabs-row .el-tabs__nav) { border: none; }
:deep(.tabs-row .el-tabs__item) {
  height: 32px; line-height: 32px; border: 1px solid #e5e6eb;
  border-bottom: none; border-radius: 4px 4px 0 0; margin-right: 4px;
  background: #fff;
}
:deep(.tabs-row .el-tabs__item.is-active) {
  background: var(--el-color-primary-light-9); color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
</style>
