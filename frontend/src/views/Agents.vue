<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新建客服</el-button>
      <el-button :disabled="!selectedIds.length" type="danger" @click="batchDelete">批量删除</el-button>
      <el-button @click="exportCsv">批量导出</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <span class="kpi-bar">
        <el-tag size="small" type="info">总接待 {{ totals.today_replied }}</el-tag>
        <el-tag size="small" type="primary">总读取 {{ totals.today_read }}</el-tag>
        <el-tag size="small" type="success">总发送 {{ totals.today_sent }}</el-tag>
        <el-tag size="small" type="warning">回复率 {{ totals.reply_rate }}%</el-tag>
      </span>
    </div>
    <el-table
      ref="tableRef" :data="rows" v-loading="loading" stripe size="small"
      row-key="id"
      @selection-change="(rs) => (selectedRows = rs)"
    >
      <el-table-column type="selection" width="44" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="nickname" label="昵称" min-width="120" />
      <el-table-column prop="role" label="角色" width="100" />
      <el-table-column prop="status" label="状态" width="80" />
      <el-table-column prop="online_status" label="在线" width="80">
        <template #default="{ row }">
          <el-tag :type="row.online_status === 'online' ? 'success' : 'info'" size="small">
            {{ row.online_status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="today_replied" label="今日接待" width="100" />
      <el-table-column prop="today_read" label="今日读取" width="100" />
      <el-table-column prop="today_sent" label="今日发送" width="100" />
      <el-table-column label="读取率" width="100">
        <template #default="{ row }">{{ ((row.today_read_rate ?? 0) * 100).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column label="回复率" width="100">
        <template #default="{ row }">{{ ((row.today_reply_rate ?? 0) * 100).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" width="180" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
          <el-button size="small" link @click="openPermDialog(row)">权限</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑客服' : '新建客服'" width="480px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="用户名" v-if="!form.id"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="昵称"><el-input v-model="form.nickname" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role">
          <el-option label="admin" value="admin" />
          <el-option label="supervisor" value="supervisor" />
          <el-option label="agent" value="agent" />
        </el-select>
      </el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" :placeholder="form.id ? '留空则不修改' : ''" /></el-form-item>
      <el-form-item label="状态" v-if="form.id"><el-select v-model="form.status"><el-option label="启用" value="enabled" /><el-option label="禁用" value="disabled" /></el-select></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="permDialog" :title="`配置 ${permTarget?.username} 的账号分组权限`" width="640px">
    <el-table :data="permRows" border size="small">
      <el-table-column label="账号分组" width="180">
        <template #default="{ row }">
          <el-select v-model="row.account_group_id" placeholder="选择分组">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="发送" width="80"><template #default="{ row }"><el-switch v-model="row.can_send_message" /></template></el-table-column>
      <el-table-column label="群发" width="80"><template #default="{ row }"><el-switch v-model="row.can_broadcast" /></template></el-table-column>
      <el-table-column label="导出" width="80"><template #default="{ row }"><el-switch v-model="row.can_export_data" /></template></el-table-column>
      <el-table-column label="看好友" width="80"><template #default="{ row }"><el-switch v-model="row.can_view_friends" /></template></el-table-column>
      <el-table-column label="看聊天" width="80"><template #default="{ row }"><el-switch v-model="row.can_view_chats" /></template></el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" @click="permRows.splice($index, 1)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button style="margin-top: 12px" @click="addPermRow">添加分组</el-button>
    <template #footer>
      <el-button @click="permDialog = false">取消</el-button>
      <el-button type="primary" @click="savePermissions">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

const tableRef = ref(null)
const rows = ref([])
const groups = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive({ id: null, username: '', nickname: '', role: 'agent', password: '', status: 'enabled' })

const permDialog = ref(false)
const permTarget = ref(null)
const permRows = ref([])

const selectedRows = ref([])
const selectedIds = computed(() => selectedRows.value.map((r) => r.id))

const totals = computed(() => {
  const sent = rows.value.reduce((s, r) => s + (r.today_sent || 0), 0)
  const read = rows.value.reduce((s, r) => s + (r.today_read || 0), 0)
  const replied = rows.value.reduce((s, r) => s + (r.today_replied || 0), 0)
  return {
    today_sent: sent, today_read: read, today_replied: replied,
    reply_rate: sent ? ((replied / sent) * 100).toFixed(1) : '0.0',
  }
})

async function load() {
  loading.value = true
  try {
    // /statistics/support-agents already returns the union of agent
    // metadata + today's KPIs, so the page only needs one request.
    const [{ data: r }, { data: g }] = await Promise.all([
      http.get('/statistics/support-agents'),
      http.get('/account-groups'),
    ])
    rows.value = r
    groups.value = g
  } finally { loading.value = false }
}

async function batchDelete() {
  await ElMessageBox.confirm(
    `确定删除选中的 ${selectedIds.value.length} 个客服？此操作不可撤销。`,
    '批量删除', { type: 'warning' },
  )
  const { data } = await http.delete('/support-agents/batch', {
    data: { ids: selectedIds.value },
  })
  ElMessage.success(`已删除 ${data.deleted} 个客服`)
  tableRef.value?.clearSelection?.()
  await load()
}

function exportCsv() {
  const headers = ['id', 'username', 'nickname', 'role', 'status', 'online_status',
                   'today_sent', 'today_read', 'today_replied',
                   'today_read_rate', 'today_reply_rate', 'last_login_at']
  const lines = [headers.join(',')]
  for (const r of rows.value) {
    lines.push(headers.map((h) => JSON.stringify(r[h] ?? '')).join(','))
  }
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `support-agents-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

function openDialog(row = null) {
  if (row) Object.assign(form, { id: row.id, username: row.username, nickname: row.nickname, role: row.role, password: '', status: row.status })
  else Object.assign(form, { id: null, username: '', nickname: '', role: 'agent', password: '', status: 'enabled' })
  dialogVisible.value = true
}

async function save() {
  if (form.id) {
    const payload = { nickname: form.nickname, role: form.role, status: form.status }
    if (form.password) payload.password = form.password
    await http.patch(`/support-agents/${form.id}`, payload)
  } else {
    await http.post('/support-agents', { username: form.username, nickname: form.nickname, role: form.role, password: form.password })
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  await load()
}

async function openPermDialog(row) {
  permTarget.value = row
  const { data } = await http.get(`/support-agents/${row.id}/account-group-permissions`)
  permRows.value = data.map((d) => ({ ...d }))
  permDialog.value = true
}

function addPermRow() {
  permRows.value.push({
    account_group_id: groups.value[0]?.id ?? null,
    can_view_friends: true, can_view_chats: true, can_send_message: true,
    can_broadcast: false, can_edit_profile: false, can_delete_friend: false,
    can_clear_chat: false, can_export_data: false, chat_scope: { all: true },
  })
}

async function savePermissions() {
  const payload = permRows.value.filter((r) => r.account_group_id)
  await http.put(`/support-agents/${permTarget.value.id}/account-group-permissions`, payload)
  ElMessage.success('权限已更新')
  permDialog.value = false
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.kpi-bar { display: inline-flex; gap: 6px; margin-left: auto; }
</style>
