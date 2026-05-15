<template>
  <el-card class="page-card">
    <div class="filter-row">
      <el-select v-model="filters.kind" placeholder="类型" clearable style="width: 140px" @change="load">
        <el-option label="导入" value="import" />
        <el-option label="导出" value="export" />
        <el-option label="导入 + 导出" value="both" />
      </el-select>
      <el-input v-model="filters.actor" placeholder="操作人" clearable style="width: 180px" />
      <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      <el-button @click="reset">重置</el-button>
    </div>

    <el-table :data="filteredRows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="created_at" label="时间" width="200" />
      <el-table-column prop="action" label="动作" width="220">
        <template #default="{ row }">
          <el-tag :type="actionTag(row.action)" size="small">{{ ACTION_LABEL[row.action] || row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="actor_username" label="操作人" width="160" />
      <el-table-column prop="actor_role" label="角色" width="100" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import http from '@/api/http'

const ACTION_LABEL = {
  'customer.import': '客户导入',
  'account.import_zip': 'session ZIP 导入',
  'phone.batch_add': '号码批量导入',
  'material.batch_add': '文本批量导入',
  'export.customers': '客户 CSV 导出',
  'export.campaign_messages': '任务消息 CSV 导出',
}

const rows = ref([])
const loading = ref(false)
const filters = reactive({ kind: 'both', actor: '' })

const filteredRows = computed(() => {
  if (!filters.actor) return rows.value
  const kw = filters.actor.toLowerCase()
  return rows.value.filter((r) => (r.actor_username || '').toLowerCase().includes(kw))
})

async function load() {
  loading.value = true
  try {
    let prefix
    if (filters.kind === 'import') {
      prefix = 'customer.import|account.import_zip|phone.batch_add|material.batch_add'
    } else if (filters.kind === 'export') {
      prefix = 'export.'
    } else {
      // both
      prefix = 'customer.import|account.import_zip|phone.batch_add|material.batch_add|export.'
    }
    const { data } = await http.get('/audit-logs', {
      params: { action_prefix: prefix, limit: 200 },
    })
    rows.value = data
  } finally { loading.value = false }
}

function reset() {
  filters.kind = 'both'
  filters.actor = ''
  load()
}

function actionTag(action) {
  if (action.startsWith('export.')) return 'warning'
  if (action.includes('import')) return 'success'
  return 'info'
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.filter-row {
  display: flex; gap: 8px; align-items: center;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 12px;
}
.detail { font-size: 12px; color: #555; margin: 0; white-space: pre-wrap; word-break: break-all; }
</style>
