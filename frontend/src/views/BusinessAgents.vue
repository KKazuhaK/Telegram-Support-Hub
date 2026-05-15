<template>
  <el-card class="page-card">
    <div class="page-header">
      <h2>商务代理</h2>
      <el-button type="primary" @click="openDialog()">+ 新建商务</el-button>
    </div>

    <div class="filter-row">
      <el-input v-model="filters.q" placeholder="请输入名称/昵称" clearable style="width: 240px" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
        <el-option label="启用" :value="true" />
        <el-option label="禁用" :value="false" />
      </el-select>
      <el-select v-model="filters.online_status" placeholder="是否在线" clearable style="width: 140px">
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
      </el-select>
      <el-button @click="reset">重置</el-button>
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="nickname" label="昵称" min-width="120" />
      <el-table-column prop="platform_name" label="平台" width="140" />
      <el-table-column prop="custom_image_url" label="自定义图片" width="140">
        <template #default="{ row }">
          <el-image v-if="row.custom_image_url" :src="row.custom_image_url" style="width: 40px; height: 40px" fit="cover" />
          <span v-else class="muted">无</span>
        </template>
      </el-table-column>
      <el-table-column prop="logo_url" label="Logo" width="120">
        <template #default="{ row }">
          <el-image v-if="row.logo_url" :src="row.logo_url" style="width: 40px; height: 40px" fit="cover" />
          <span v-else class="muted">未上传</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.status" @change="(v) => toggleStatus(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="online_status" label="是否在线" width="100">
        <template #default="{ row }">
          <el-tag :type="row.online_status === 'online' ? 'success' : 'info'" size="small">
            {{ row.online_status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column prop="last_login_at" label="上次登录时间" width="180" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">✏ 编辑</el-button>
          <el-popconfirm title="确定删除？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" link type="danger">🗑 删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑商务代理' : '新建商务代理'" width="540px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="名称" required><el-input v-model="form.name" :disabled="!!form.id" /></el-form-item>
      <el-form-item label="密码" :required="!form.id">
        <el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '留空则不修改' : ''" />
      </el-form-item>
      <el-form-item label="昵称" required><el-input v-model="form.nickname" /></el-form-item>
      <el-form-item label="平台名称" required><el-input v-model="form.platform_name" /></el-form-item>
      <el-form-item label="状态"><el-switch v-model="form.status" /></el-form-item>
      <el-form-item label="自定义图片"><el-input v-model="form.custom_image_url" placeholder="图片 URL（暂不支持上传）" /></el-form-item>
      <el-form-item label="Logo"><el-input v-model="form.logo_url" placeholder="Logo URL（暂不支持上传）" /></el-form-item>
      <el-form-item label="域名"><el-input v-model="form.domains" type="textarea" :rows="2" placeholder="多个域名用换行分隔" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const rows = ref([])
const loading = ref(false)
const filters = reactive({ q: '', status: null, online_status: '' })

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: null, name: '', password: '', nickname: '', platform_name: '',
  status: true, custom_image_url: '', logo_url: '', domains: '', remark: '',
})

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.q) params.q = filters.q
    if (filters.status !== null && filters.status !== '') params.status = filters.status
    if (filters.online_status) params.online_status = filters.online_status
    const { data } = await http.get('/business-agents', { params })
    rows.value = data
  } finally { loading.value = false }
}

function reset() {
  filters.q = ''
  filters.status = null
  filters.online_status = ''
  load()
}

function openDialog(row = null) {
  if (row) {
    Object.assign(form, {
      id: row.id, name: row.name, password: '', nickname: row.nickname || '',
      platform_name: row.platform_name || '', status: row.status,
      custom_image_url: row.custom_image_url || '', logo_url: row.logo_url || '',
      domains: row.domains || '', remark: row.remark || '',
    })
  } else {
    Object.assign(form, {
      id: null, name: '', password: '', nickname: '', platform_name: '',
      status: true, custom_image_url: '', logo_url: '', domains: '', remark: '',
    })
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.nickname || !form.platform_name) {
    ElMessage.warning('请填写名称 / 昵称 / 平台名称')
    return
  }
  if (!form.id && !form.password) {
    ElMessage.warning('请设置初始密码')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      const payload = {
        nickname: form.nickname, platform_name: form.platform_name, status: form.status,
        custom_image_url: form.custom_image_url, logo_url: form.logo_url,
        domains: form.domains, remark: form.remark,
      }
      if (form.password) payload.password = form.password
      await http.patch(`/business-agents/${form.id}`, payload)
    } else {
      await http.post('/business-agents', {
        name: form.name, password: form.password, nickname: form.nickname,
        platform_name: form.platform_name, status: form.status,
        custom_image_url: form.custom_image_url, logo_url: form.logo_url,
        domains: form.domains, remark: form.remark,
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } finally { saving.value = false }
}

async function toggleStatus(row, status) {
  await http.patch(`/business-agents/${row.id}`, { status })
  await load()
}

async function remove(row) {
  await http.delete(`/business-agents/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 16px; }
.filter-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
.muted { color: #c0c4cc; font-size: 12px; }
</style>
