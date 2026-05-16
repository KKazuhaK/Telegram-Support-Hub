<template>
  <!-- Stripped-down workspace for support_agent (role=agent) actors.
       The full admin Layout (sidebar of 20+ menu items, breadcrumbs,
       tabs) is the wrong tool when the only job is to chat with
       customers. This is a focused two-pane shell: chat takes the
       whole viewport; a small right rail offers translate panel and
       a way back to /. -->
  <div class="console-shell">
    <header class="console-bar">
      <div class="brand">
        <el-icon :size="20"><ChatDotRound /></el-icon>
        <span>TG 客服工作台</span>
      </div>
      <div class="spacer" />
      <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'info'">{{ roleLabel }}</el-tag>
      <span class="username">{{ auth.username }}</span>
      <el-dropdown @command="onCmd">
        <el-icon style="cursor: pointer;"><ArrowDown /></el-icon>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-if="auth.isAdmin" command="admin">返回管理后台</el-dropdown-item>
            <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>

    <main class="console-main">
      <Replies />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import Replies from '@/views/Replies.vue'

const auth = useAuthStore()
const router = useRouter()

const roleLabel = computed(() => {
  if (auth.actorKind === 'business_agent') return '商务代理'
  if (auth.actorKind === 'merchant') return '商家'
  return { admin: '管理员', supervisor: '主管', agent: '客服' }[auth.role] || auth.role
})

function onCmd(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push({ name: 'login' })
  } else if (cmd === 'admin') {
    router.push({ name: 'dashboard' })
  }
}
</script>

<style scoped>
.console-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--tg-bg, #f5f7fa);
}
.console-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--tg-surface, #fff);
  border-bottom: 1px solid var(--tg-border, #e5e6eb);
  height: 48px;
  flex: 0 0 auto;
}
.console-bar .brand {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; color: #2aabee;
}
.console-bar .spacer { flex: 1; }
.console-bar .username { font-size: 13px; color: #555; }
.console-main {
  flex: 1;
  padding: 12px;
  min-height: 0;
  overflow: hidden;
}
/* Replies.vue computes its own height from `calc(100vh - 160px)` —
   override here so it fills the console body since we've removed the
   admin Layout's breadcrumbs and tab strip. */
:deep(.chat-shell) {
  height: 100% !important;
}
</style>
