<template>
  <el-card class="page-card">
    <div class="filter-row">
      <el-select v-model="filters.group_id" placeholder="账号分组" clearable style="width: 160px">
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-select v-model="filters.account_id" placeholder="所属账号" clearable filterable style="width: 200px">
        <el-option v-for="a in accounts" :key="a.id" :label="`${a.tg_user_id}${a.phone ? ' · ' + a.phone : ''}`" :value="a.id" />
      </el-select>
      <el-input v-model="filters.username" placeholder="username/昵称" clearable style="width: 180px" />
      <el-input v-model="filters.phone" placeholder="手机号" clearable style="width: 160px" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="reset">重置</el-button>
      <el-button @click="exportCsv">导出 CSV</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="account_id" label="账号" width="80" />
      <el-table-column prop="username" label="用户名" width="160" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="phone" label="手机号" width="160" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_reply_at" label="最近回复" width="180" />
      <el-table-column prop="last_message_at" label="最近消息" width="180" />
      <el-table-column prop="opted_out" label="退订" width="80">
        <template #default="{ row }">
          <el-tag :type="row.opted_out ? 'danger' : 'info'" size="small">{{ row.opted_out ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-divider v-if="auth.isAdmin" content-position="left">手动同步</el-divider>
    <div v-if="auth.isAdmin" class="sync-row">
      <el-select v-model="syncAccountId" placeholder="选择要同步的账号" filterable style="width: 280px">
        <el-option v-for="a in accounts" :key="a.id" :label="`${a.tg_user_id}${a.phone ? ' · ' + a.phone : ''}`" :value="a.id" />
      </el-select>
      <el-button type="primary" :disabled="!syncAccountId" :loading="syncing" @click="triggerSync">触发好友同步</el-button>
      <span class="hint">需要 worker-account 在运行；任务在后台异步执行，完成后刷新即可看到。</span>
    </div>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const accounts = ref([])
const groups = ref([])
const loading = ref(false)
const syncing = ref(false)
const syncAccountId = ref(null)

const statuses = ['new', 'contacted', 'read', 'replied', 'blocked', 'opted_out']
const filters = reactive({ group_id: null, account_id: null, username: '', phone: '', status: '' })

const STATUS_TYPE = { new: 'info', contacted: 'warning', read: 'primary', replied: 'success', blocked: 'danger', opted_out: 'info' }
function statusType(s) { return STATUS_TYPE[s] || 'info' }

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.account_id) params.account_id = filters.account_id
    if (filters.status) params.status = filters.status
    const { data } = await http.get('/customers/friends', { params })
    // Frontend-side filter for fields the backend doesn't expose yet.
    rows.value = data.filter((r) => {
      if (filters.username && !`${r.username || ''} ${r.nickname || ''}`.toLowerCase().includes(filters.username.toLowerCase())) return false
      if (filters.phone && !(r.phone || '').includes(filters.phone)) return false
      if (filters.group_id && r.account_group_id !== filters.group_id) return false
      return true
    })
    if (!accounts.value.length) {
      const { data: a } = await http.get('/accounts', { params: { limit: 500 } })
      accounts.value = a
    }
    if (!groups.value.length) {
      const { data: g } = await http.get('/account-groups')
      groups.value = g
    }
  } finally { loading.value = false }
}

function reset() {
  filters.group_id = null
  filters.account_id = null
  filters.username = ''
  filters.phone = ''
  filters.status = ''
  load()
}

async function triggerSync() {
  syncing.value = true
  try {
    const { data } = await http.post(`/customers/friends/sync?account_id=${syncAccountId.value}`)
    ElMessage.success(`已派发同步任务 (task ${data.task_id})`)
  } finally { syncing.value = false }
}

function exportCsv() {
  // Backend does not have a friends CSV export endpoint yet; fall back to
  // client-side serialisation so the user still gets a file.
  const headers = ['id', 'account_id', 'username', 'nickname', 'phone', 'status', 'last_reply_at', 'opted_out']
  const lines = [headers.join(',')]
  for (const r of rows.value) {
    lines.push(headers.map((h) => JSON.stringify(r[h] ?? '')).join(','))
  }
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'friends.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.filter-row {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 12px;
}
.sync-row {
  display: flex; gap: 12px; align-items: center; padding: 8px 0;
}
.hint { color: #999; font-size: 12px; }
</style>
