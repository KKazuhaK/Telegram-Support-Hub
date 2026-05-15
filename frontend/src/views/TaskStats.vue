<template>
  <el-card class="page-card">
    <el-tabs v-model="tab" class="status-tabs">
      <!-- 统计报表 -->
      <el-tab-pane label="统计报表" name="report">
        <div class="filter-row">
          <el-select v-model="report.bucket" style="width: 120px" @change="loadReport">
            <el-option label="按天" value="day" />
            <el-option label="按周" value="week" />
            <el-option label="按月" value="month" />
          </el-select>
          <el-date-picker
            v-model="report.range" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始日期" end-placeholder="结束日期"
            style="width: 280px"
            @change="loadReport"
          />
          <el-button type="primary" :loading="loading.report" @click="loadReport">查询</el-button>
        </div>

        <div class="summary-row">
          <div class="metric" v-for="m in metrics" :key="m.label" :style="{ borderTopColor: m.color }">
            <div class="metric-value" :style="{ color: m.color }">{{ m.value }}</div>
            <div class="metric-label">{{ m.label }}</div>
          </div>
        </div>

        <div class="chart-card">
          <h3 class="chart-title">消息统计</h3>
          <VChart v-if="reportData.buckets.length"
                  :option="chartOption" :autoresize="true"
                  style="height: 420px; width: 100%" />
          <el-empty v-else description="所选时段没有消息记录" />
        </div>
      </el-tab-pane>

      <!-- 统计详情 -->
      <el-tab-pane label="统计详情" name="details">
        <div class="filter-row">
          <el-select v-model="details.status" placeholder="状态" clearable style="width: 140px">
            <el-option v-for="s in MESSAGE_STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
          <el-input v-model.number="details.task_id" placeholder="任务 ID" clearable style="width: 140px" />
          <el-input v-model.number="details.account_id" placeholder="账号 ID" clearable style="width: 140px" />
          <el-date-picker
            v-model="details.range" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始日期" end-placeholder="结束日期"
            style="width: 280px"
          />
          <el-button type="primary" :loading="loading.details" @click="loadDetails">查询</el-button>
          <el-button @click="resetDetails">重置</el-button>
        </div>
        <el-table :data="detailRows" v-loading="loading.details" stripe size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="sent_at" label="发送时间" width="180" />
          <el-table-column prop="campaign_id" label="任务" width="80" />
          <el-table-column prop="account_id" label="账号" width="80" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="phone" label="目标手机号" width="160" />
          <el-table-column prop="body_snapshot" label="内容" show-overflow-tooltip />
          <el-table-column prop="error_message" label="错误" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>

      <!-- 维度对比 -->
      <el-tab-pane label="维度对比" name="dimensions">
        <el-tabs v-model="dim" class="inner-tabs">
          <el-tab-pane label="账号" name="accounts">
            <el-table :data="dims.accounts" v-loading="loading.accounts" stripe size="small">
              <el-table-column prop="account_id" label="账号 ID" width="80" />
              <el-table-column prop="tg_user_id" label="TG ID" min-width="120" />
              <el-table-column prop="phone" label="手机号" width="160" />
              <el-table-column prop="status" label="状态" width="100" />
              <el-table-column prop="daily_limit" label="日上限" width="90" />
              <el-table-column prop="sent_today" label="今日已发" width="100" />
              <el-table-column prop="total_sent" label="累计发送" width="100" />
              <el-table-column prop="total_replies" label="累计回复" width="100" />
              <el-table-column prop="reply_rate" label="回复率" width="100">
                <template #default="{ row }">{{ (row.reply_rate * 100).toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="账号分组" name="groups">
            <el-table :data="dims.groups" v-loading="loading.groups" stripe size="small">
              <el-table-column prop="group_id" label="ID" width="60" />
              <el-table-column prop="name" label="分组名" />
              <el-table-column prop="account_count" label="账号数" width="90" />
              <el-table-column prop="sent_today" label="今日已发" width="100" />
              <el-table-column prop="msg_sent" label="累计发" width="100" />
              <el-table-column prop="msg_replied" label="累计回" width="100" />
              <el-table-column prop="msg_failed" label="累计失" width="100" />
              <el-table-column prop="reply_rate" label="回复率" width="100">
                <template #default="{ row }">{{ (row.reply_rate * 100).toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="客服" name="agents">
            <el-table :data="dims.agents" v-loading="loading.agents" stripe size="small">
              <el-table-column prop="agent_id" label="ID" width="60" />
              <el-table-column prop="username" label="用户名" />
              <el-table-column prop="nickname" label="昵称" />
              <el-table-column prop="role" label="角色" width="100" />
              <el-table-column prop="online_status" label="在线" width="80" />
              <el-table-column prop="last_login_at" label="最近登录" />
              <el-table-column prop="active_last_7d" label="7 天内活跃" width="120">
                <template #default="{ row }">{{ row.active_last_7d ? '是' : '否' }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, GridComponent,
  LegendComponent, DataZoomComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import http from '@/api/http'

use([
  CanvasRenderer, LineChart, BarChart,
  TitleComponent, TooltipComponent, GridComponent,
  LegendComponent, DataZoomComponent,
])

const MESSAGE_STATUSES = ['queued', 'sending', 'sent', 'read', 'replied', 'failed', 'failed_permanent', 'retry', 'cancelled']

const tab = ref('report')
const dim = ref('accounts')
const loading = reactive({ report: false, details: false, accounts: false, groups: false, agents: false })

// 统计报表
const report = reactive({ bucket: 'day', range: [] })
const reportData = ref({ buckets: [], totals: { sent: 0, read: 0, replied: 0, failed: 0, read_rate: 0, reply_rate: 0 } })

const metrics = computed(() => {
  const t = reportData.value.totals
  return [
    { label: '总发送数', value: t.sent ?? 0, color: '#909399' },
    { label: '总已读数', value: t.read ?? 0, color: '#409eff' },
    { label: '总回复数', value: t.replied ?? 0, color: '#67c23a' },
    { label: '总已读率', value: `${((t.read_rate ?? 0) * 100).toFixed(1)}%`, color: '#e6a23c' },
    { label: '总回复率', value: `${((t.reply_rate ?? 0) * 100).toFixed(1)}%`, color: '#f56c6c' },
  ]
})

const chartOption = computed(() => {
  const buckets = reportData.value.buckets
  const dates = buckets.map((b) => b.date)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['发送', '已读', '回复', '失败', '已读率', '回复率'] },
    grid: { left: 50, right: 50, bottom: 50, top: 50 },
    xAxis: { type: 'category', data: dates },
    yAxis: [
      { type: 'value', name: '条数' },
      { type: 'value', name: '比率', min: 0, max: 1, axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` } },
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 10 }],
    series: [
      { name: '发送', type: 'bar', data: buckets.map((b) => b.sent), itemStyle: { color: '#909399' } },
      { name: '已读', type: 'bar', data: buckets.map((b) => b.read), itemStyle: { color: '#409eff' } },
      { name: '回复', type: 'bar', data: buckets.map((b) => b.replied), itemStyle: { color: '#67c23a' } },
      { name: '失败', type: 'bar', data: buckets.map((b) => b.failed), itemStyle: { color: '#f56c6c' } },
      {
        name: '已读率', type: 'line', yAxisIndex: 1, smooth: true,
        data: buckets.map((b) => (b.sent ? b.read / b.sent : 0)),
        itemStyle: { color: '#e6a23c' },
      },
      {
        name: '回复率', type: 'line', yAxisIndex: 1, smooth: true,
        data: buckets.map((b) => (b.sent ? b.replied / b.sent : 0)),
        itemStyle: { color: '#f56c6c' },
      },
    ],
  }
})

async function loadReport() {
  loading.report = true
  try {
    const params = { bucket: report.bucket }
    if (report.range?.length === 2) {
      params.from = report.range[0]
      params.to = report.range[1]
    }
    const { data } = await http.get('/statistics/timeseries', { params })
    reportData.value = data
  } finally { loading.report = false }
}

// 统计详情
const details = reactive({ status: '', task_id: null, account_id: null, range: [] })
const detailRows = ref([])

async function loadDetails() {
  loading.details = true
  try {
    const params = {}
    if (details.status) params.status = details.status
    if (details.task_id) params.task_id = details.task_id
    if (details.account_id) params.account_id = details.account_id
    if (details.range?.length === 2) {
      params.from = details.range[0]
      params.to = details.range[1]
    }
    const { data } = await http.get('/statistics/message-details', { params })
    detailRows.value = data
  } finally { loading.details = false }
}

function resetDetails() {
  details.status = ''
  details.task_id = null
  details.account_id = null
  details.range = []
  loadDetails()
}

function statusTag(s) {
  return ({
    sent: 'success', replied: 'success', read: 'primary',
    queued: 'info', retry: 'warning', sending: 'warning',
    failed: 'danger', failed_permanent: 'danger', cancelled: 'info',
  })[s] || 'info'
}

// 维度对比
const dims = reactive({ accounts: [], groups: [], agents: [] })

async function loadAccounts() {
  loading.accounts = true
  try {
    const { data } = await http.get('/statistics/accounts')
    dims.accounts = data
  } finally { loading.accounts = false }
}
async function loadGroups() {
  loading.groups = true
  try {
    const { data } = await http.get('/statistics/account-groups')
    dims.groups = data
  } finally { loading.groups = false }
}
async function loadAgents() {
  loading.agents = true
  try {
    const { data } = await http.get('/statistics/support-agents')
    dims.agents = data
  } finally { loading.agents = false }
}

watch(tab, (v) => {
  if (v === 'report' && !reportData.value.buckets.length) loadReport()
  if (v === 'details' && !detailRows.value.length) loadDetails()
  if (v === 'dimensions' && !dims.accounts.length) loadAccounts()
})

watch(dim, (v) => {
  if (v === 'accounts' && !dims.accounts.length) loadAccounts()
  if (v === 'groups' && !dims.groups.length) loadGroups()
  if (v === 'agents' && !dims.agents.length) loadAgents()
})

onMounted(loadReport)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.status-tabs { margin-bottom: 8px; }
.inner-tabs { margin-top: 8px; }
.filter-row {
  display: flex; gap: 8px; align-items: center;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 16px;
}

.summary-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.metric {
  background: #fff; border: 1px solid #ebeef5; border-top: 3px solid #ccc;
  border-radius: 4px; padding: 14px 16px; text-align: center;
}
.metric-value { font-size: 26px; font-weight: 600; }
.metric-label { color: #909399; font-size: 12px; margin-top: 4px; }

.chart-card {
  background: #fff; border: 1px solid #ebeef5; border-radius: 4px; padding: 14px 16px;
}
.chart-title { margin: 0 0 12px 0; font-size: 14px; font-weight: 600; color: #303133; }
</style>
