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

  <el-dialog v-model="dialogVisible" title="新建群发任务" width="900px" top="6vh">
    <div class="dialog-grid">
      <el-form :model="form" label-width="110px" class="dialog-form">
        <el-divider content-position="left">基础设置</el-divider>
        <el-form-item label="任务名" required><el-input v-model="form.name" placeholder="留空则自动按时间生成" /></el-form-item>
        <el-form-item label="任务类型">
          <el-radio-group v-model="form.target_type">
            <el-radio value="customer_broadcast">客户群发</el-radio>
            <el-radio value="friend_broadcast">好友群发</el-radio>
            <el-radio value="imported_target_broadcast">导入目标</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模板">
          <el-select v-model="form.template_id" placeholder="请选择" style="width: 100%">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" :disabled="!t.enabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号分组">
          <el-select v-model="form.account_group_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.target_type === 'imported_target_broadcast'" label="目标列表">
          <el-input
            v-model="importedTargetsText"
            type="textarea"
            :rows="4"
            placeholder="每行一条：&#10;+8613800000000,张三&#10;@alice,Alice"
          />
        </el-form-item>

        <el-divider content-position="left">账号执行设置</el-divider>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="成功间隔(秒)"><el-input-number v-model="form.send_settings.success_interval_seconds" :min="1" controls-position="right" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="失败间隔(秒)"><el-input-number v-model="form.send_settings.failure_interval_seconds" :min="1" controls-position="right" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="随机下限"><el-input-number v-model="form.send_settings.random_min_seconds" :min="0" controls-position="right" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="随机上限"><el-input-number v-model="form.send_settings.random_max_seconds" :min="0" controls-position="right" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="并发账号数"><el-input-number v-model="form.send_settings.task_concurrency" :min="1" controls-position="right" style="width: 100%" /></el-form-item></el-col>
        </el-row>

        <el-divider content-position="left">附加设置</el-divider>
        <el-form-item label="静默时段">
          <el-input v-model="form.send_settings.quiet_hours_start" placeholder="22:00" style="width: 110px" />
          <span style="margin: 0 8px">~</span>
          <el-input v-model="form.send_settings.quiet_hours_end" placeholder="09:00" style="width: 110px" />
        </el-form-item>
      </el-form>

      <div class="dialog-help">
        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><InfoFilled /></el-icon> 任务类型说明</div>
          <ul>
            <li><b>客户群发</b>：从「客户管理」中已分配账号、且 consent=true 的客户里发起。</li>
            <li><b>好友群发</b>：对所选账号分组下已同步的 TG 好友发起。</li>
            <li><b>导入目标</b>：临时贴一批手机号或 @username，按选中分组的账号轮询发出。</li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><Timer /></el-icon> 间隔规则</div>
          <p><code>nextRunAt = now + 成功/失败间隔 + random(下限,上限)</code></p>
          <p>同一账号同时只发一条（Redis 锁）。任务暂停时锁释放，恢复后按当前间隔重排。</p>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><Histogram /></el-icon> 静默时段</div>
          <p>填 <code>22:00</code> ~ <code>09:00</code> 表示晚 10 点到早 9 点不发。跨午夜会自动识别。</p>
          <p>留空 = 全天可发。</p>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><Warning /></el-icon> 模板变量</div>
          <p>在模板正文里支持：</p>
          <ul>
            <li><code>{name}</code> 客户姓名（缺省 → 客户）</li>
            <li><code>{phone}</code> 手机号</li>
            <li><code>{source}</code> 来源（导入目标 → "imported"）</li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><CircleCheck /></el-icon> 账号要求</div>
          <p>所选账号分组里至少要有 <b>启用</b> 且状态为 <code>active</code> 或 <code>imported</code> 的账号，否则会报「没有满足条件的目标」。</p>
        </el-card>
      </div>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="create">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  InfoFilled, Timer, Histogram, Warning, CircleCheck,
} from '@element-plus/icons-vue'
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

.dialog-grid {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
}
.dialog-form { min-width: 0; }
.dialog-help {
  display: flex; flex-direction: column; gap: 12px;
  max-height: 70vh; overflow-y: auto;
}
.help-card { background: #fafafa; border: 1px solid #f0f0f0; }
:deep(.help-card .el-card__body) { padding: 12px; }
.help-title {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; color: #303133; margin-bottom: 6px; font-size: 13px;
}
.help-card p, .help-card ul { margin: 4px 0; font-size: 12px; color: #606266; line-height: 1.6; }
.help-card ul { padding-left: 18px; }
.help-card code {
  background: #f0f0f0; padding: 1px 4px; border-radius: 2px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #d56565;
}
</style>
