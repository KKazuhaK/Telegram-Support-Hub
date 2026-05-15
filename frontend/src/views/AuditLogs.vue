<template>
  <el-card>
    <div class="toolbar">
      <el-input v-model="filters.action" placeholder="action" clearable style="width: 200px" />
      <el-input v-model="filters.actor_username" placeholder="actor_username" clearable style="width: 200px" />
      <el-input v-model="filters.target_type" placeholder="target_type" clearable style="width: 200px" />
      <el-button type="primary" @click="load">查询</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="created_at" label="时间" width="200" />
      <el-table-column prop="actor_username" label="操作人" width="160" />
      <el-table-column prop="actor_role" label="角色" width="100" />
      <el-table-column prop="action" label="动作" width="200" />
      <el-table-column prop="target_type" label="对象类型" width="160" />
      <el-table-column prop="target_id" label="对象 ID" width="100" />
      <el-table-column label="详情">
        <template #default="{ row }">
          <pre class="detail">{{ row.detail ? JSON.stringify(row.detail) : '' }}</pre>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import http from '@/api/http'

const rows = ref([])
const loading = ref(false)
const filters = reactive({ action: '', actor_username: '', target_type: '' })

async function load() {
  loading.value = true
  try {
    const params = {}
    for (const [k, v] of Object.entries(filters)) if (v) params[k] = v
    const { data } = await http.get('/audit-logs', { params })
    rows.value = data
  } finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
.detail { font-size: 12px; color: #555; margin: 0; white-space: pre-wrap; word-break: break-all; }
</style>
