<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" v-if="auth.isAdmin" @click="openDialog">新建代理</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="protocol" label="协议" width="100" />
      <el-table-column prop="host" label="主机" />
      <el-table-column prop="port" label="端口" width="80" />
      <el-table-column prop="country" label="国家" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latency_ms" label="延迟(ms)" width="100" />
      <el-table-column prop="last_error" label="最近错误" show-overflow-tooltip />
      <el-table-column label="操作" width="160" v-if="auth.isAdmin">
        <template #default="{ row }">
          <el-button size="small" link @click="checkProxy(row)">检测</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
  <el-dialog v-model="dialogVisible" title="新建代理" width="480px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="协议">
        <el-select v-model="form.protocol">
          <el-option label="socks5" value="socks5" />
          <el-option label="http" value="http" />
          <el-option label="https" value="https" />
        </el-select>
      </el-form-item>
      <el-form-item label="主机"><el-input v-model="form.host" /></el-form-item>
      <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      <el-form-item label="国家"><el-input v-model="form.country" placeholder="如 CN / US" /></el-form-item>
      <el-form-item label="最大账号"><el-input-number v-model="form.max_accounts" :min="0" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive({ name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '', country: '', max_accounts: 5 })

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/proxies')
    rows.value = data
  } finally { loading.value = false }
}

function openDialog() {
  Object.assign(form, { name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '', country: '', max_accounts: 5 })
  dialogVisible.value = true
}

async function save() {
  await http.post('/proxies', form)
  ElMessage.success('已创建')
  dialogVisible.value = false
  await load()
}

async function checkProxy(row) {
  await http.post(`/proxies/${row.id}/check`)
  ElMessage.success('检测完成')
  await load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
