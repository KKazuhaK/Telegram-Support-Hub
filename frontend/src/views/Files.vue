<template>
  <el-card class="page-card">
    <div class="toolbar">
      <el-upload
        :http-request="upload"
        :show-file-list="false"
        :before-upload="beforeUpload"
        multiple
      >
        <el-button type="primary">上传文件</el-button>
      </el-upload>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <span class="hint">所有文件存储在服务器 SESSION_DIR 同级的 uploads 目录，模板中通过 [file:文件名] 引用（计划中）。</span>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="name" label="文件名" min-width="240" />
      <el-table-column prop="size" label="大小" width="120">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="modified_at" label="修改时间" width="200" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-popconfirm title="确定删除？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" link type="danger">删除</el-button>
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

const rows = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/files')
    rows.value = data
  } finally { loading.value = false }
}

function beforeUpload(file) {
  const max = 20 * 1024 * 1024
  if (file.size > max) {
    ElMessage.warning(`${file.name} 超过 20MB 上限`)
    return false
  }
  return true
}

async function upload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await http.post('/files', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success(`已上传：${data.name}`)
  await load()
}

async function remove(row) {
  await http.delete(`/files/${encodeURIComponent(row.name)}`)
  ElMessage.success(`已删除 ${row.name}`)
  await load()
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.hint { color: #999; font-size: 12px; }
</style>
