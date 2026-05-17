<template>
  <el-container class="app-container">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="brand">
        <el-icon class="brand-icon" :size="22"><ChatDotRound /></el-icon>
        <span v-if="!collapsed">TG Support Hub</span>
      </div>
      <el-scrollbar>
        <el-menu :default-active="route.name" :collapse="collapsed" :collapse-transition="false" router unique-opened>
          <el-menu-item index="dashboard" :route="{ name: 'dashboard' }">
            <el-icon><Odometer /></el-icon>
            <template #title>{{ t('menu.dashboard') }}</template>
          </el-menu-item>

          <el-menu-item index="accounts" :route="{ name: 'accounts' }">
            <el-icon><User /></el-icon>
            <template #title>{{ t('menu.accounts') }}</template>
          </el-menu-item>

          <el-menu-item index="friends" :route="{ name: 'friends' }">
            <el-icon><Avatar /></el-icon>
            <template #title>{{ t('menu.friends') }}</template>
          </el-menu-item>

          <el-menu-item v-if="auth.isAdmin" index="business-agents" :route="{ name: 'business-agents' }">
            <el-icon><Briefcase /></el-icon>
            <template #title>{{ t('menu.business_agents') }}</template>
          </el-menu-item>

          <el-menu-item
            v-if="auth.isAdmin || auth.isBusinessAgent"
            index="merchants"
            :route="{ name: 'merchants' }"
          >
            <el-icon><Shop /></el-icon>
            <template #title>{{ t('menu.merchants') }}</template>
          </el-menu-item>

          <el-menu-item index="account-groups" :route="{ name: 'account-groups' }">
            <el-icon><Collection /></el-icon>
            <template #title>{{ t('menu.account_groups') }}</template>
          </el-menu-item>

          <el-sub-menu index="task-mgmt">
            <template #title>
              <el-icon><Promotion /></el-icon><span>{{ t('menu.task_mgmt') }}</span>
            </template>
            <el-menu-item index="batch-operations" :route="{ name: 'batch-operations' }">{{ t('menu.batch_operations') }}</el-menu-item>
            <el-menu-item index="modify-info" :route="{ name: 'modify-info' }">{{ t('menu.modify_info') }}</el-menu-item>
            <el-menu-item index="campaigns" :route="{ name: 'campaigns' }">{{ t('menu.campaigns') }}</el-menu-item>
            <el-menu-item index="templates" :route="{ name: 'templates' }">{{ t('menu.templates') }}</el-menu-item>
            <el-menu-item index="replies" :route="{ name: 'replies' }">{{ t('menu.replies') }}</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="task-stats" :route="{ name: 'task-stats' }">
            <el-icon><PieChart /></el-icon>
            <template #title>{{ t('menu.task_stats') }}</template>
          </el-menu-item>

          <template v-if="auth.isAdmin">
            <el-sub-menu index="log-mgmt">
              <template #title>
                <el-icon><Notebook /></el-icon><span>{{ t('menu.log_records') }}</span>
              </template>
              <el-menu-item index="task-log" :route="{ name: 'task-log' }">{{ t('menu.task_log') }}</el-menu-item>
              <el-menu-item index="io-log" :route="{ name: 'io-log' }">{{ t('menu.io_log') }}</el-menu-item>
              <el-menu-item index="audit-logs" :route="{ name: 'audit-logs' }">{{ t('menu.audit_logs') }}</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="staff-mgmt">
              <template #title>
                <el-icon><UserFilled /></el-icon><span>{{ t('menu.staff_center') }}</span>
              </template>
              <el-menu-item index="agents" :route="{ name: 'agents' }">{{ t('menu.agents') }}</el-menu-item>
            </el-sub-menu>
          </template>

          <el-sub-menu index="data-mgmt">
            <template #title>
              <el-icon><FolderOpened /></el-icon><span>{{ t('menu.data_mgmt') }}</span>
            </template>
            <el-menu-item v-if="auth.isAdmin" index="files" :route="{ name: 'files' }">{{ t('menu.files') }}</el-menu-item>
            <el-menu-item index="phones" :route="{ name: 'phones' }">{{ t('menu.phones') }}</el-menu-item>
            <el-menu-item index="materials" :route="{ name: 'materials' }">{{ t('menu.materials') }}</el-menu-item>
            <el-menu-item v-if="auth.isAdmin" index="proxies" :route="{ name: 'proxies' }">{{ t('menu.proxies') }}</el-menu-item>
            <el-menu-item index="customers" :route="{ name: 'customers' }">{{ t('menu.customers') }}</el-menu-item>
          </el-sub-menu>

          <el-menu-item v-if="auth.isAdmin" index="settings" :route="{ name: 'settings' }">
            <el-icon><Setting /></el-icon>
            <template #title>系统设置</template>
          </el-menu-item>
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
            <el-tag v-if="status.has_admin" size="small" type="success">{{ t('common.workers_ok').includes('workers') ? '✓' : '' }}</el-tag>
            <el-tag size="small" type="info">{{ t('menu.accounts') }} {{ status.accounts ?? '-' }}</el-tag>
            <el-tag size="small" type="info">{{ t('menu.customers') }} {{ status.customers ?? '-' }}</el-tag>
            <el-tag size="small" :type="status.workersOk ? 'success' : 'warning'">
              {{ status.workersOk ? t('common.workers_ok') : t('common.workers_check') }}
            </el-tag>
          </div>

          <div class="topbar-spacer" />

          <el-button link @click="theme.toggle()" :title="theme.theme === 'dark' ? 'Light' : 'Dark'">
            <el-icon :size="18"><Sunny v-if="theme.theme === 'dark'" /><Moon v-else /></el-icon>
          </el-button>

          <el-dropdown @command="onLocaleCommand">
            <el-button link>
              <el-icon :size="18"><ChatLineRound /></el-icon>
              <span class="locale-label">{{ locale === 'zh-CN' ? '中' : 'EN' }}</span>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="zh-CN" :disabled="locale === 'zh-CN'">中文</el-dropdown-item>
                <el-dropdown-item command="en-US" :disabled="locale === 'en-US'">English</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-button link @click="toggleFullscreen" :title="isFullscreen ? t('common.exit_fullscreen') : t('common.fullscreen')">
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
                <el-dropdown-item command="console">客服工作台</el-dropdown-item>
                <el-dropdown-item divided command="refresh">{{ t('common.refresh_page') }}</el-dropdown-item>
                <el-dropdown-item command="closeOthers">{{ t('common.close_others') }}</el-dropdown-item>
                <el-dropdown-item command="closeAll">{{ t('common.close_all') }}</el-dropdown-item>
                <el-dropdown-item divided command="logout">{{ t('common.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="tabs-row">
          <el-button link class="tab-scroll" :disabled="!canScrollLeft" @click="scrollTabs(-1)">
            <el-icon><ArrowLeft /></el-icon>
          </el-button>
          <div class="tabs-scroll" ref="tabsScrollEl">
            <el-tabs
              v-model="tabsStore.active"
              type="card"
              closable
              @tab-click="onTabClick"
              @tab-remove="onTabRemove"
            >
              <el-tab-pane
                v-for="tab in tabsStore.tabs"
                :key="tab.name"
                :label="tab.title"
                :name="tab.name"
                :closable="tab.closable"
              />
            </el-tabs>
          </div>
          <el-button link class="tab-scroll" :disabled="!canScrollRight" @click="scrollTabs(1)">
            <el-icon><ArrowRight /></el-icon>
          </el-button>
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
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { useThemeStore } from '@/stores/theme'
import { saveLocale } from '@/i18n'
import http from '@/api/http'
import {
  Odometer, User, UserFilled, FolderOpened, Promotion,
  Fold, Expand, FullScreen, ArrowDown,
  Collection, Avatar, PieChart, Notebook,
  Briefcase, Shop, ChatDotRound, ChatLineRound,
  Sunny, Moon, ArrowLeft, ArrowRight, Setting,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const tabsStore = useTabsStore()
const theme = useThemeStore()
const { t, locale } = useI18n()

const collapsed = ref(false)
const isFullscreen = ref(false)
const status = reactive({ has_admin: false, accounts: null, customers: null, workersOk: false })

const roleLabel = computed(() => {
  if (auth.actorKind === 'business_agent') return '商务代理'
  if (auth.actorKind === 'merchant') return '商家'
  if (!auth.role) return ''
  return t(`common.role_${auth.role}`)
})

const cachedNames = computed(() => tabsStore.tabs.map((t) => routeNameToComponent(t.name)).filter(Boolean))

function routeNameToComponent(name) {
  // keep-alive needs the *component* name. Our route names match component
  // file names roughly; use PascalCase fallback if needed. The simpler path
  // is to set <component :key="route.name"> + KeepAlive on all, but we keep
  // it loose so it does not break lookups.
  return name
}

const PARENT = {
  'batch-operations': '任务管理', 'modify-info': '任务管理',
  campaigns: '任务管理', templates: '任务管理', replies: '任务管理',
  'task-log': '日志记录', 'io-log': '日志记录', 'audit-logs': '日志记录',
  agents: '客服中心',
  customers: '数据管理', files: '数据管理', proxies: '数据管理',
  phones: '数据管理', materials: '数据管理',
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

function onLocaleCommand(cmd) {
  if (cmd === locale.value) return
  locale.value = cmd
  saveLocale(cmd)
  ElMessage.success(cmd === 'en-US' ? 'Locale switched. Reload for full effect.' : '语言已切换，部分组件需要刷新页面生效')
}

const tabsScrollEl = ref(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
function refreshScrollState() {
  const el = tabsScrollEl.value
  if (!el) { canScrollLeft.value = false; canScrollRight.value = false; return }
  canScrollLeft.value = el.scrollLeft > 2
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
}
function scrollTabs(dir) {
  const el = tabsScrollEl.value
  if (!el) return
  el.scrollBy({ left: dir * 200, behavior: 'smooth' })
  setTimeout(refreshScrollState, 250)
}

function onUserCommand(cmd) {
  if (cmd === 'console') {
    router.push({ name: 'console' })
  } else if (cmd === 'logout') {
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
  // Cheap, never-fails endpoint = backend reachability. Dashboard
  // aggregation is slow + heavy; failing it shouldn't flip the worker
  // health badge to '检查中'. Fetch them independently.
  try {
    const { data: hasAdmin } = await http.get('/auth/has-admin')
    status.has_admin = !!hasAdmin?.has_admin
    status.workersOk = true
  } catch (_) {
    status.workersOk = false
    return
  }
  try {
    const { data: dash } = await http.get('/statistics/dashboard')
    // Tenants don't get an accounts section (TG inventory is back-office
    // only) — fall back to '-' display in those views.
    status.accounts = dash?.accounts?.total ?? null
    status.customers = dash?.customers?.total ?? 0
  } catch (_) {
    // Dashboard failure is non-fatal for the badge — leave counts as
    // whatever they were and don't toggle workersOk off.
  }
}

onMounted(() => {
  loadStatus()
  document.addEventListener('fullscreenchange', syncFullscreenFlag)
  nextTick(refreshScrollState)
  window.addEventListener('resize', refreshScrollState)
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenFlag)
  window.removeEventListener('resize', refreshScrollState)
})

watch(() => tabsStore.tabs.length, () => nextTick(refreshScrollState))
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
  display: flex; align-items: center; gap: 10px;
}
.brand-icon { color: #2aabee; }
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

.tabs-row {
  padding: 6px 12px 0; background: #fafafa;
  display: flex; align-items: center; gap: 4px;
}
.tabs-scroll {
  flex: 1; min-width: 0; overflow-x: auto; overflow-y: hidden;
  scrollbar-width: none;
}
.tabs-scroll::-webkit-scrollbar { display: none; }
.tab-scroll { flex: 0 0 auto; height: 32px; padding: 0 4px; }
.locale-label { margin-left: 4px; font-size: 12px; }
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
