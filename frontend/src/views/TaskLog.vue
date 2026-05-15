<template>
  <el-card class="page-card">
    <div class="filter-row">
      <el-input v-model.number="filters.task_id" placeholder="任务 ID" clearable style="width: 140px" />
      <el-input v-model.number="filters.account_id" placeholder="账号 ID" clearable style="width: 140px" />
      <el-input v-model="filters.phone" placeholder="目标手机号/数据" clearable style="width: 200px" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
        <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
      </el-select>
      <el-date-picker
        v-model="filters.range" type="daterange" value-format="YYYY-MM-DD"
        start-placeholder="开始日期" end-placeholder="结束日期" style="width: 280px"
      />
      <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      <el-button @click="reset">重置</el-button>
      <el-button @click="exportCsv">导出</el-button>
    </div>

    <el-table :data="filteredRows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="sent_at" label="日期" width="180" />
      <el-table-column prop="campaign_id" label="任务" width="80" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">{{ campaignKindLabel(row.campaign_id) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="account_id" label="账号" width="80" />
      <el-table-column label="来源" width="80">
        <template #default="{ row }">{{ row.customer_id ? '客户' : row.friend_id ? '好友' : '导入' }}</template>
      </el-table-column>
      <el-table-column prop="phone" label="数据" width="160" />
      <el-table-column prop="body_snapshot" label="内容" show-overflow-tooltip />
      <el-table-column prop="error_message" label="描述" show-overflow-tooltip />
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import http from '@/api/http'

const STATUSES = ['queued', 'sending', 'sent', 'read', 'replied', 'failed', 'failed_permanent', 'retry', 'cancelled']

const rows = ref([])
const campaigns = ref([])
const loading = ref(false)
const filters = reactive({ task_id: null, account_id: null, phone: '', status: '', range: [] })

const filteredRows = computed(() => {
  if (!filters.phone) return rows.value
  const kw = filters.phone.toLowerCase()
  return rows.value.filter((r) => (r.phone || '').toLowerCase().includes(kw))
})

function campaignKindLabel(id) {
  if (!id) return '—'
  const c = campaigns.value.find((x) => x.id === id)
  return c ? c.task_kind : ''
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.task_id) params.task_id = filters.task_id
    if (filters.account_id) params.account_id = filters.account_id
    if (filters.status) params.status = filters.status
    if (filters.range?.length === 2) {
      params.from = filters.range[0]
      params.to = filters.range[1]
    }
    params.limit = 500
    const [{ data: r }, { data: c }] = await Promise.all([
      http.get('/statistics/message-details', { params }),
      campaigns.value.length ? Promise.resolve({ data: campaigns.value }) : http.get('/campaigns'),
    ])
    rows.value = r
    campaigns.value = c
  } finally { loading.value = false }
}

function reset() {
  filters.task_id = null
  filters.account_id = null
  filters.phone = ''
  filters.status = ''
  filters.range = []
  load()
}

function statusTag(s) {
  return ({
    sent: 'success', replied: 'success', read: 'primary',
    queued: 'info', retry: 'warning', sending: 'warning',
    failed: 'danger', failed_permanent: 'danger', cancelled: 'info',
  })[s] || 'info'
}

function exportCsv() {
  // Client-side serialisation. Backend CSV export hits R16.
  const headers = ['id', 'sent_at', 'campaign_id', 'account_id', 'phone', 'status', 'body_snapshot', 'error_message']
  const lines = [headers.join(',')]
  for (const r of filteredRows.value) {
    lines.push(headers.map((h) => JSON.stringify(r[h] ?? '')).join(','))
  }
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `task-log-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.filter-row {
  display: flex; gap: 8px; align-items: center;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 12px;
  flex-wrap: wrap;
}
</style>
