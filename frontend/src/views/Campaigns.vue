<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" @click="openDialog">新建任务</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="任务名" />
      <el-table-column prop="target_type" label="类型" width="160" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="target_count" label="目标" width="80" />
      <el-table-column prop="sent_count" label="已发" width="80" />
      <el-table-column prop="reply_count" label="回复" width="80" />
      <el-table-column prop="failed_count" label="失败" width="80" />
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" link @click="action(row, 'start')">启动</el-button>
          <el-button size="small" link @click="action(row, 'pause')">暂停</el-button>
          <el-button size="small" link @click="action(row, 'resume')">继续</el-button>
          <el-button size="small" link type="danger" @click="action(row, 'cancel')">取消</el-button>
          <el-button size="small" link @click="exportMessages(row)">导出</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" title="新建群发任务" width="640px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="任务名"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="模板">
        <el-select v-model="form.template_id" placeholder="请选择">
          <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" :disabled="!t.enabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="任务类型">
        <el-radio-group v-model="form.target_type">
          <el-radio value="customer_broadcast">客户群发</el-radio>
          <el-radio value="friend_broadcast">好友群发</el-radio>
          <el-radio value="imported_target_broadcast">导入目标</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="账号分组">
        <el-select v-model="form.account_group_ids" multiple>
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.target_type === 'imported_target_broadcast'" label="目标列表">
        <el-input v-model="importedTargetsText" type="textarea" :rows="4" placeholder="每行一条，格式：phone[,name] 或 @username[,name]" />
      </el-form-item>
      <el-divider>发送间隔</el-divider>
      <el-form-item label="成功间隔(秒)"><el-input-number v-model="form.send_settings.success_interval_seconds" :min="1" /></el-form-item>
      <el-form-item label="失败间隔(秒)"><el-input-number v-model="form.send_settings.failure_interval_seconds" :min="1" /></el-form-item>
      <el-form-item label="随机下限"><el-input-number v-model="form.send_settings.random_min_seconds" :min="0" /></el-form-item>
      <el-form-item label="随机上限"><el-input-number v-model="form.send_settings.random_max_seconds" :min="0" /></el-form-item>
      <el-form-item label="任务并发账号"><el-input-number v-model="form.send_settings.task_concurrency" :min="1" /></el-form-item>
      <el-form-item label="静默时段">
        <el-input v-model="form.send_settings.quiet_hours_start" placeholder="22:00" style="width: 110px" />
        <span style="margin: 0 8px">~</span>
        <el-input v-model="form.send_settings.quiet_hours_end" placeholder="09:00" style="width: 110px" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="create">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const rows = ref([])
const groups = ref([])
const templates = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const creating = ref(false)
const importedTargetsText = ref('')

const defaultForm = () => ({
  name: '',
  template_id: null,
  target_type: 'customer_broadcast',
  account_group_ids: [],
  send_settings: {
    success_interval_seconds: 60,
    failure_interval_seconds: 120,
    random_min_seconds: 5,
    random_max_seconds: 30,
    task_concurrency: 5,
    quiet_hours_start: '',
    quiet_hours_end: '',
  },
})
const form = reactive(defaultForm())

async function load() {
  loading.value = true
  try {
    const [{ data: r }, { data: g }, { data: t }] = await Promise.all([
      http.get('/campaigns'),
      http.get('/account-groups'),
      http.get('/message-templates'),
    ])
    rows.value = r
    groups.value = g
    templates.value = t
  } finally { loading.value = false }
}

function openDialog() {
  Object.assign(form, defaultForm())
  importedTargetsText.value = ''
  dialogVisible.value = true
}

function statusType(status) {
  return ({
    running: 'success', queued: 'info', paused: 'warning',
    completed: 'success', cancelled: 'info', partially_failed: 'danger',
  })[status] || 'info'
}

function parseImported() {
  return importedTargetsText.value
    .split('\n').map((l) => l.trim()).filter(Boolean)
    .map((line) => {
      const [first, name] = line.split(',').map((s) => s.trim())
      if (first.startsWith('@')) return { username: first, name }
      return { phone: first, name }
    })
}

async function create() {
  creating.value = true
  try {
    const payload = { ...form }
    // strip empty quiet hours so the backend keeps null
    if (!payload.send_settings.quiet_hours_start) payload.send_settings.quiet_hours_start = null
    if (!payload.send_settings.quiet_hours_end) payload.send_settings.quiet_hours_end = null
    if (payload.target_type === 'imported_target_broadcast') {
      payload.imported_targets = parseImported()
    }
    await http.post('/campaigns', payload)
    ElMessage.success('已创建')
    dialogVisible.value = false
    await load()
  } finally { creating.value = false }
}

async function action(row, name) {
  await http.post(`/campaigns/${row.id}/${name}`)
  ElMessage.success(`已${({ start: '启动', pause: '暂停', resume: '继续', cancel: '取消' })[name]}`)
  await load()
}

async function exportMessages(row) {
  const { data } = await http.get(`/export/campaigns/${row.id}/messages.csv`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `campaign-${row.id}-messages.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
