<template>
  <el-card class="page-card">
    <el-tabs v-model="tab" class="status-tabs">
      <el-tab-pane label="账号维度" name="accounts">
        <div class="filter-row">
          <el-input v-model="accountSearch" placeholder="按 TG ID / 手机号过滤" clearable style="width: 240px" />
          <el-button :loading="loading.accounts" @click="loadAccounts">刷新</el-button>
        </div>
        <el-table :data="filteredAccounts" v-loading="loading.accounts" stripe size="small">
          <el-table-column prop="account_id" label="账号 ID" width="80" />
          <el-table-column prop="tg_user_id" label="TG ID" min-width="120" />
          <el-table-column prop="phone" label="手机号" width="160" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="enabled" label="启用" width="80">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="daily_limit" label="日上限" width="90" />
          <el-table-column prop="sent_today" label="今日已发" width="100" />
          <el-table-column prop="total_sent" label="累计发送" width="100" />
          <el-table-column prop="total_replies" label="累计回复" width="100" />
          <el-table-column prop="msg_sent" label="消息记录(发)" width="120" />
          <el-table-column prop="msg_replied" label="消息记录(回)" width="120" />
          <el-table-column prop="msg_failed" label="消息记录(失)" width="120" />
          <el-table-column prop="reply_rate" label="回复率" width="100">
            <template #default="{ row }">{{ (row.reply_rate * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="账号分组维度" name="groups">
        <div class="filter-row"><el-button :loading="loading.groups" @click="loadGroups">刷新</el-button></div>
        <el-table :data="groupRows" v-loading="loading.groups" stripe size="small">
          <el-table-column prop="group_id" label="ID" width="60" />
          <el-table-column prop="name" label="分组名" />
          <el-table-column prop="code" label="编码" width="120" />
          <el-table-column prop="enabled" label="启用" width="80">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="account_count" label="账号数" width="90" />
          <el-table-column prop="daily_limit" label="日上限" width="90" />
          <el-table-column prop="sent_today" label="今日已发" width="100" />
          <el-table-column prop="msg_sent" label="累计发" width="100" />
          <el-table-column prop="msg_replied" label="累计回" width="100" />
          <el-table-column prop="msg_failed" label="累计失" width="100" />
          <el-table-column prop="reply_rate" label="回复率" width="100">
            <template #default="{ row }">{{ (row.reply_rate * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="客服维度" name="agents">
        <div class="filter-row"><el-button :loading="loading.agents" @click="loadAgents">刷新</el-button></div>
        <el-table :data="agentRows" v-loading="loading.agents" stripe size="small">
          <el-table-column prop="agent_id" label="ID" width="60" />
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="nickname" label="昵称" />
          <el-table-column prop="role" label="角色" width="100" />
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column prop="online_status" label="在线" width="90" />
          <el-table-column prop="last_login_at" label="最近登录" />
          <el-table-column prop="active_last_7d" label="7 天内活跃" width="120">
            <template #default="{ row }">
              <el-tag :type="row.active_last_7d ? 'success' : 'info'" size="small">{{ row.active_last_7d ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import http from '@/api/http'

const tab = ref('accounts')
const loading = reactive({ accounts: false, groups: false, agents: false })

const accountRows = ref([])
const groupRows = ref([])
const agentRows = ref([])
const accountSearch = ref('')

const filteredAccounts = computed(() => {
  if (!accountSearch.value) return accountRows.value
  const kw = accountSearch.value.toLowerCase()
  return accountRows.value.filter((r) =>
    `${r.tg_user_id || ''} ${r.phone || ''}`.toLowerCase().includes(kw),
  )
})

const STATUS_TYPE = {
  imported: 'info', active: 'success', paused: 'warning',
  limited: 'warning', error: 'danger', archived: '',
}
function statusType(s) { return STATUS_TYPE[s] || 'info' }

async function loadAccounts() {
  loading.accounts = true
  try {
    const { data } = await http.get('/statistics/accounts')
    accountRows.value = data
  } finally { loading.accounts = false }
}

async function loadGroups() {
  loading.groups = true
  try {
    const { data } = await http.get('/statistics/account-groups')
    groupRows.value = data
  } finally { loading.groups = false }
}

async function loadAgents() {
  loading.agents = true
  try {
    const { data } = await http.get('/statistics/support-agents')
    agentRows.value = data
  } finally { loading.agents = false }
}

watch(tab, (v) => {
  if (v === 'accounts' && !accountRows.value.length) loadAccounts()
  if (v === 'groups' && !groupRows.value.length) loadGroups()
  if (v === 'agents' && !agentRows.value.length) loadAgents()
})

onMounted(loadAccounts)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.filter-row {
  display: flex; gap: 8px; align-items: center;
  padding: 8px 0 12px;
}
</style>
