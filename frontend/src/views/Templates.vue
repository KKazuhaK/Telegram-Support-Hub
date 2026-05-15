<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新建模板</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="body" label="内容" show-overflow-tooltip />
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="120" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }"><el-button size="small" link @click="openDialog(row)">编辑</el-button></template>
      </el-table-column>
    </el-table>
  </el-card>
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑模板' : '新建模板'" width="560px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="内容">
        <el-input v-model="form.body" type="textarea" :rows="6" placeholder="支持变量 {name} {phone} {source}" />
      </el-form-item>
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

const rows = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive({ id: null, name: '', body: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/message-templates')
    rows.value = data
  } finally { loading.value = false }
}

function openDialog(row = null) {
  if (row) Object.assign(form, { id: row.id, name: row.name, body: row.body })
  else Object.assign(form, { id: null, name: '', body: '' })
  dialogVisible.value = true
}

async function save() {
  if (form.id) await http.patch(`/message-templates/${form.id}`, { name: form.name, body: form.body })
  else await http.post('/message-templates', { name: form.name, body: form.body })
  ElMessage.success('已保存')
  dialogVisible.value = false
  await load()
}

async function toggleEnabled(row, enabled) {
  await http.patch(`/message-templates/${row.id}`, { enabled })
  await load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
