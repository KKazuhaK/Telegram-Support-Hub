<template>
  <el-card class="page-card">
    <el-tabs v-model="statusTab" @tab-change="onStatusTabChange" class="status-tabs">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="启用" name="enabled" />
      <el-tab-pane label="待验证" name="imported" />
      <el-tab-pane label="正常" name="active" />
      <el-tab-pane label="受限" name="limited" />
      <el-tab-pane label="异常" name="error" />
      <el-tab-pane label="归档" name="archived" />
    </el-tabs>

    <div class="filter-row">
      <el-select v-model="filters.group_id" placeholder="账号分组" clearable style="width: 160px">
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-input v-model="filters.phone" placeholder="手机号关键字" clearable style="width: 180px" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="resetFilters">重置</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="action-row">
      <el-upload
        v-if="auth.isAdmin"
        :http-request="uploadZip"
        :show-file-list="false"
        accept=".zip"
      >
        <el-button type="primary">上传 session ZIP</el-button>
      </el-upload>
      <el-button-group v-if="auth.isAdmin">
        <el-button :disabled="!selectedIds.length" @click="batchEnabled(true)">上线</el-button>
        <el-button :disabled="!selectedIds.length" @click="batchEnabled(false)">下线</el-button>
        <el-button :disabled="!selectedIds.length" @click="batchStatus('archived')">归档</el-button>
        <el-button :disabled="!selectedIds.length" type="danger" @click="batchDelete">批量删除</el-button>
      </el-button-group>
      <span class="hint">已选 {{ selectedIds.length }} 个</span>
    </div>

    <el-table
      ref="tableRef"
      :data="rows"
      v-loading="loading"
      stripe
      size="small"
      row-key="id"
      @selection-change="(rows) => (selectedRows = rows)"
    >
      <el-table-column type="selection" width="44" reserve-selection />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="tg_user_id" label="TG ID" min-width="120" />
      <el-table-column prop="phone" label="手机号" width="160" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :disabled="!auth.isAdmin"
            @change="(v) => toggleEnabled(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="daily_limit" label="日上限" width="90" />
      <el-table-column prop="sent_today" label="今日已发" width="100" />
      <el-table-column prop="total_sent" label="累计发送" width="100" />
      <el-table-column prop="total_replies" label="累计回复" width="100" />
      <el-table-column prop="proxy_id" label="代理" width="80">
        <template #default="{ row }">{{ row.proxy_id || '未绑定' }}</template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" width="170" />
      <el-table-column label="操作" width="180" v-if="auth.isAdmin">
        <template #default="{ row }">
          <el-button size="small" link @click="autoBindProxy(row)">自动代理</el-button>
          <el-popconfirm title="确认解绑代理？" @confirm="unbindProxy(row)">
            <template #reference>
              <el-button size="small" link type="danger" :disabled="!row.proxy_id">解绑</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const groups = ref([])
const loading = ref(false)
const statusTab = ref('all')
const filters = reactive({ group_id: null, phone: '' })

const tableRef = ref(null)
const selectedRows = ref([])
const selectedIds = computed(() => selectedRows.value.map((r) => r.id))

const STATUS_LABEL = {
  imported: '待验证', active: '正常', paused: '暂停',
  limited: '受限', error: '异常', archived: '归档',
}
const STATUS_TYPE = {
  imported: 'info', active: 'success', paused: 'warning',
  limited: 'warning', error: 'danger', archived: '',
}
function statusLabel(s) { return STATUS_LABEL[s] || s }
function statusType(s) { return STATUS_TYPE[s] || 'info' }

function buildParams() {
  const params = {}
  if (statusTab.value === 'enabled') params.enabled = true
  else if (statusTab.value !== 'all') params.status = statusTab.value
  if (filters.group_id) params.group_id = filters.group_id
  if (filters.phone) params.phone = filters.phone
  return params
}

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/accounts', { params: buildParams() })
    rows.value = data
    if (groups.value.length === 0) {
      const { data: g } = await http.get('/account-groups')
      groups.value = g
    }
  } finally { loading.value = false }
}

function resetFilters() {
  filters.group_id = null
  filters.phone = ''
  statusTab.value = 'all'
  load()
}

function onStatusTabChange() {
  load()
}

async function uploadZip({ file }) {
  const fd = new FormData()
  fd.append('sessions', file)
  const { data } = await http.post('/accounts/import-zip', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success(`导入 ${data.imported.length} 个，跳过 ${data.skipped.length} 个`)
  await load()
}

async function toggleEnabled(row, enabled) {
  await http.patch(`/accounts/${row.id}`, { enabled })
  await load()
}

async function batchEnabled(enabled) {
  await http.post('/accounts/batch', { ids: selectedIds.value, enabled })
  ElMessage.success(`已${enabled ? '上线' : '下线'} ${selectedIds.value.length} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function batchStatus(status) {
  await http.post('/accounts/batch', { ids: selectedIds.value, status })
  ElMessage.success(`已设为「${statusLabel(status)}」 ${selectedIds.value.length} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function batchDelete() {
  await ElMessageBox.confirm(
    `确定删除选中的 ${selectedIds.value.length} 个账号？此操作不可撤销。`,
    '批量删除',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
  const { data } = await http.delete('/accounts/batch', { data: { ids: selectedIds.value } })
  ElMessage.success(`已删除 ${data.deleted} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function autoBindProxy(row) {
  await http.post(`/accounts/${row.id}/proxy/auto`)
  ElMessage.success('代理已自动绑定')
  await load()
}

async function unbindProxy(row) {
  await http.delete(`/accounts/${row.id}/proxy`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.status-tabs { margin-bottom: 8px; }
:deep(.status-tabs .el-tabs__header) { margin-bottom: 12px; }

.filter-row {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 12px;
}
.action-row {
  display: flex; gap: 12px; align-items: center; margin-bottom: 12px;
}
.hint { color: #999; font-size: 12px; }
</style>
