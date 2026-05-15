<template>
  <el-card>
    <div class="toolbar">
      <el-upload
        :http-request="uploadZip"
        :show-file-list="false"
        accept=".zip"
        v-if="auth.isAdmin"
      >
        <el-button type="primary">导入 session ZIP</el-button>
      </el-upload>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="tg_user_id" label="TG ID" />
      <el-table-column prop="phone" label="手机号" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
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
      <el-table-column prop="daily_limit" label="日上限" width="100" />
      <el-table-column prop="sent_today" label="今日已发" width="100" />
      <el-table-column prop="proxy_id" label="代理" width="100">
        <template #default="{ row }">{{ row.proxy_id || '未绑定' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" v-if="auth.isAdmin">
        <template #default="{ row }">
          <el-button size="small" link @click="autoBindProxy(row)">自动分配代理</el-button>
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
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/accounts')
    rows.value = data
  } finally {
    loading.value = false
  }
}

function statusType(status) {
  return ({
    active: 'success',
    imported: 'info',
    paused: 'warning',
    limited: 'warning',
    error: 'danger',
  })[status] || 'info'
}

async function uploadZip({ file }) {
  const fd = new FormData()
  fd.append('sessions', file)
  const { data } = await http.post('/accounts/import-zip', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success(`导入 ${data.imported.length} 个账号，跳过 ${data.skipped.length} 个`)
  await load()
}

async function toggleEnabled(row, enabled) {
  await http.patch(`/accounts/${row.id}`, { enabled })
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
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
