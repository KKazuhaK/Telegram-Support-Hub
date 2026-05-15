<template>
  <el-container class="app-container">
    <el-aside width="220px" class="sidebar">
      <div class="brand">TG Support Hub</div>
      <el-menu :default-active="route.name" router :unique-opened="true">
        <el-menu-item :index="'dashboard'" :route="{ name: 'dashboard' }">
          <el-icon><Odometer /></el-icon><span>总览看板</span>
        </el-menu-item>
        <el-sub-menu index="account-mgmt">
          <template #title><el-icon><User /></el-icon><span>账号管理</span></template>
          <el-menu-item :index="'accounts'" :route="{ name: 'accounts' }">TG 账号</el-menu-item>
          <el-menu-item :index="'account-groups'" :route="{ name: 'account-groups' }">账号分组</el-menu-item>
          <el-menu-item :index="'proxies'" :route="{ name: 'proxies' }">网络代理</el-menu-item>
        </el-sub-menu>
        <el-menu-item :index="'customers'" :route="{ name: 'customers' }">
          <el-icon><Avatar /></el-icon><span>客户管理</span>
        </el-menu-item>
        <el-menu-item :index="'templates'" :route="{ name: 'templates' }">
          <el-icon><Document /></el-icon><span>消息模板</span>
        </el-menu-item>
        <el-menu-item :index="'campaigns'" :route="{ name: 'campaigns' }">
          <el-icon><Promotion /></el-icon><span>群发任务</span>
        </el-menu-item>
        <el-menu-item :index="'replies'" :route="{ name: 'replies' }">
          <el-icon><ChatDotRound /></el-icon><span>回复管理</span>
        </el-menu-item>
        <template v-if="auth.isAdmin">
          <el-menu-item :index="'agents'" :route="{ name: 'agents' }">
            <el-icon><UserFilled /></el-icon><span>客服中心</span>
          </el-menu-item>
          <el-menu-item :index="'audit-logs'" :route="{ name: 'audit-logs' }">
            <el-icon><Notebook /></el-icon><span>审计日志</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <span class="page-title">{{ pageTitle }}</span>
        <div class="topbar-right">
          <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'info'">{{ auth.role || 'guest' }}</el-tag>
          <span class="username">{{ auth.username }}</span>
          <el-button link type="primary" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main>
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer, User, UserFilled, Avatar, Document, Promotion, ChatDotRound, Notebook,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const TITLES = {
  dashboard: '总览看板',
  accounts: 'TG 账号',
  'account-groups': '账号分组',
  proxies: '网络代理',
  customers: '客户管理',
  templates: '消息模板',
  campaigns: '群发任务',
  replies: '回复管理',
  agents: '客服中心',
  'audit-logs': '审计日志',
}
const pageTitle = computed(() => TITLES[route.name] || '')

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<style scoped>
.app-container { height: 100vh; }
.sidebar { background: #001529; color: #fff; }
.brand { color: #fff; font-size: 16px; padding: 16px; font-weight: bold; }
:deep(.el-menu) { background: #001529; border-right: none; }
:deep(.el-menu-item), :deep(.el-sub-menu__title) { color: rgba(255,255,255,0.85); }
:deep(.el-menu-item.is-active) { background-color: #1890ff !important; color: #fff; }
.topbar {
  background: #fff; display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #e5e6eb;
}
.page-title { font-size: 16px; font-weight: 500; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.username { color: #555; font-size: 13px; }
</style>
