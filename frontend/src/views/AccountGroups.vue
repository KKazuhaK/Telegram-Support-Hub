<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" v-if="auth.isAdmin" @click="openDialog()">新建分组</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="code" label="编码" />
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '禁用' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="daily_limit" label="日上限" width="100" />
      <el-table-column prop="sent_today" label="今日已发" width="100" />
      <el-table-column prop="remark" label="备注" />
      <el-table-column label="操作" width="120" v-if="auth.isAdmin">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑分组' : '新建分组'" width="480px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="编码" v-if="!form.id"><el-input v-model="form.code" /></el-form-item>
      <el-form-item label="日上限"><el-input-number v-model="form.daily_limit" :min="0" /></el-form-item>
      <el-form-item label="启用" v-if="form.id"><el-switch v-model="form.enabled" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
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
const form = reactive({ id: null, name: '', code: '', daily_limit: 1000, enabled: true, remark: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/account-groups')
    rows.value = data
  } finally { loading.value = false }
}

function openDialog(row = null) {
  if (row) {
    Object.assign(form, { id: row.id, name: row.name, code: row.code, daily_limit: row.daily_limit, enabled: row.enabled, remark: row.remark || '' })
  } else {
    Object.assign(form, { id: null, name: '', code: '', daily_limit: 1000, enabled: true, remark: '' })
  }
  dialogVisible.value = true
}

async function save() {
  if (form.id) {
    await http.patch(`/account-groups/${form.id}`, { name: form.name, daily_limit: form.daily_limit, enabled: form.enabled, remark: form.remark })
  } else {
    await http.post('/account-groups', { name: form.name, code: form.code || undefined, daily_limit: form.daily_limit, remark: form.remark })
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  await load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
