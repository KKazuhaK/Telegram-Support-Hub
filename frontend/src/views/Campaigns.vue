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
      <el-table-column label="操作" width="340">
        <template #default="{ row }">
          <el-button size="small" link @click="openRunsDialog(row)">详情</el-button>
          <el-button size="small" link @click="action(row, 'start')">启动</el-button>
          <el-button size="small" link @click="action(row, 'pause')">暂停</el-button>
          <el-button size="small" link @click="action(row, 'resume')">继续</el-button>
          <el-button size="small" link type="danger" @click="action(row, 'cancel')">取消</el-button>
          <el-button size="small" link @click="exportMessages(row)">导出</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="runsDialog"
             :title="runsTarget ? `任务 #${runsTarget.id} · ${runsTarget.name || runsTarget.target_type} · 发送明细` : '发送明细'"
             width="920px" top="6vh">
    <div v-if="runsTarget" class="runs-summary">
      <el-tag type="info">目标 {{ runsTarget.target_count ?? '—' }}</el-tag>
      <el-tag type="success">已发 {{ runsTarget.sent_count ?? 0 }}</el-tag>
      <el-tag>已读 {{ runsTarget.read_count ?? 0 }}</el-tag>
      <el-tag type="warning">回复 {{ runsTarget.reply_count ?? 0 }}</el-tag>
      <el-tag type="danger">失败 {{ runsTarget.failed_count ?? 0 }}</el-tag>
      <el-tag>状态 {{ runsTarget.status }}</el-tag>
    </div>
    <el-table :data="runs" v-loading="runsLoading" size="small" border stripe height="500"
              empty-text="还没有发送记录。任务可能尚未启动，或目标列表为空。">
      <el-table-column label="目标" min-width="200">
        <template #default="{ row }">
          <div>{{ row.phone || row.target_tg_user_id || '—' }}</div>
          <div v-if="row.target_tg_user_id && row.phone" class="muted">tg:{{ row.target_tg_user_id }}</div>
        </template>
      </el-table-column>
      <el-table-column label="发送号" width="160">
        <template #default="{ row }">{{ row.account_id ? `#${row.account_id}` : '—' }}</template>
      </el-table-column>
      <el-table-column label="结果" width="100">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.status] || 'info'" size="small">
            {{ STATUS_LABEL[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_code" label="错误码" width="160" />
      <el-table-column prop="error_message" label="错误信息" min-width="240" show-overflow-tooltip />
      <el-table-column label="下次重试" width="160">
        <template #default="{ row }">
          <span v-if="['queued', 'retry', 'sending'].includes(row.status) && row.next_run_at"
                :class="{ overdue: isOverdue(row.next_run_at) }">
            {{ formatRetry(row.next_run_at) }}
          </span>
          <span v-else style="color:#bbb">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="sent_at" label="发送时间" width="160" />
    </el-table>
    <template #footer>
      <el-button @click="loadRuns" :loading="runsLoading">刷新</el-button>
      <el-button :loading="requeuing"
                 :disabled="!hasRecoverableFailures"
                 @click="requeueFailed">
        重新入队失败号
      </el-button>
      <el-button @click="runsDialog = false">关闭</el-button>
    </template>
  </el-dialog>

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
        <el-form-item v-if="form.target_type === 'customer_broadcast'" label="强制重发">
          <el-checkbox v-model="form.force_resend">
            包含已 sent / read / replied 的客户（适合跟进 / 二次推送）
          </el-checkbox>
          <div class="form-hint">
            默认只发状态为 new/assigned/failed/queued 的客户，避免重复打扰。
            勾上后状态闸放开，但 <code>consent=false</code> 和未分配账号的客户仍会被跳过。
          </div>
        </el-form-item>
        <el-form-item v-if="form.target_type === 'imported_target_broadcast'" label="目标列表">
          <el-input
            v-model="importedTargetsText"
            type="textarea"
            :rows="4"
            placeholder="每行一条：&#10;+8613800000000,张三&#10;@alice,Alice"
          />
          <div class="form-hint">
            手机号可省略「+」号，但必须带国家码。例如美国号写 <code>13233930000</code>（1 + 10 位），中国号写 <code>8613800138000</code>（86 + 11 位）；只写本地号会发送失败。
          </div>
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

        <!-- Live pre-flight: estimates per-account load and warns when
             the planned broadcast risks tripping TG anti-spam. Polled
             on form change with a small debounce. -->
        <el-alert v-if="preflight && preflight.severity !== 'ok'"
                  :type="alertType(preflight.severity)"
                  :title="preflightTitle"
                  show-icon :closable="false"
                  style="margin-top: 8px;">
          <div style="font-size:12px;line-height:1.6;">
            目标 <b>{{ preflight.target_count }}</b> · 可用号
            <b>{{ preflight.eligible_accounts }}</b> · 平均
            <b>{{ preflight.per_account_avg ?? '—' }}</b> 条/号。
            <span v-if="preflight.severity === 'danger'">
              超过 25 条/号风险极高（PeerFloodError 概率大）。建议把号加到分组里、或拆成多次小批群发。
            </span>
            <span v-else-if="preflight.severity === 'warning'">
              15-25 条/号属于黄色区，新号慎用。建议确认目标号都是 warming up 过的老号。
            </span>
            <span v-else-if="preflight.severity === 'no_accounts'">
              所选分组里没有可用号（enabled + active/imported），任务会立即结束。
            </span>
          </div>
        </el-alert>
      </el-form>

      <div class="dialog-help">
        <el-card shadow="never" class="help-card">
          <div class="help-title"><el-icon><InfoFilled /></el-icon> 任务类型说明</div>
          <ul>
            <li><b>客户群发</b>：从「客户管理」中已分配账号、且 consent=true 的客户里发起。</li>
            <li><b>好友群发</b>：对所选账号分组下已同步的 TG 好友发起。</li>
            <li><b>导入目标</b>：临时贴一批手机号或 @username，按选中分组的账号轮询发出。</li>
          </ul>
          <p style="margin-top: 8px;">手机号可省略 <code>+</code>，但必须含国家码（美国 <code>1...</code>、中国 <code>86...</code>），否则发送会失败。</p>
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
import { ref, reactive, onMounted, computed, watch } from 'vue'
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
  force_resend: false,
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

const preflight = ref(null)
const alertType = (sev) => (
  sev === 'danger' ? 'error' :
  sev === 'warning' ? 'warning' :
  sev === 'no_accounts' ? 'info' : 'info'
)
const preflightTitle = computed(() => {
  const s = preflight.value?.severity
  if (s === 'danger') return '⚠️ 风险极高：人均派送过多，可能触发 PeerFloodError 导致账号被限'
  if (s === 'warning') return '建议确认：人均派送较高'
  if (s === 'no_accounts') return '没有可用账号'
  return ''
})

let _preflightTimer = null
async function runPreflight() {
  // Only the broadcast family has eligibility math worth showing.
  if (form.task_kind && form.task_kind !== 'broadcast') {
    preflight.value = null
    return
  }
  if (!form.account_group_ids.length) {
    preflight.value = null
    return
  }
  try {
    const { data } = await http.post('/campaigns/preflight', {
      task_kind: 'broadcast',
      target_type: form.target_type,
      account_group_ids: form.account_group_ids,
      imported_targets_count: form.target_type === 'imported_target_broadcast'
        ? importedTargetsText.value.split('\n').filter((l) => l.trim()).length
        : 0,
    })
    preflight.value = data
  } catch (_) { preflight.value = null }
}

watch([
  () => form.target_type,
  () => form.account_group_ids,
  () => importedTargetsText.value,
], () => {
  // Debounce so each keystroke in the targets textarea doesn't hammer
  // the backend. 300ms feels responsive without being noisy.
  if (_preflightTimer) clearTimeout(_preflightTimer)
  _preflightTimer = setTimeout(runPreflight, 300)
}, { deep: true })

async function load() {
  loading.value = true
  try {
    const [{ data: r }, { data: g }, { data: t }] = await Promise.all([
      http.get('/campaigns', { params: { task_kind: 'broadcast' } }),
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

const STATUS_LABEL = {
  pending: '待发', queued: '排队', sent: '已发', read: '已读',
  replied: '已回复', failed: '失败', failed_permanent: '失败(终)',
  cancelled: '已取消',
}
const STATUS_TYPE = {
  sent: 'success', read: 'success', replied: 'warning',
  failed: 'danger', failed_permanent: 'danger',
  cancelled: 'info', pending: 'info', queued: 'info',
}

const runsDialog = ref(false)
const runsTarget = ref(null)
const runs = ref([])
const runsLoading = ref(false)

async function openRunsDialog(row) {
  runsTarget.value = row
  runs.value = []
  runsDialog.value = true
  await loadRuns()
}

async function loadRuns() {
  if (!runsTarget.value) return
  runsLoading.value = true
  try {
    const { data } = await http.get(`/campaigns/${runsTarget.value.id}/messages`, {
      params: { limit: 500 },
    })
    runs.value = data || []
  } finally { runsLoading.value = false }
}

const RECOVERABLE_ERRORS = ['account_unavailable', 'flood_wait', 'no_target']
const hasRecoverableFailures = computed(() => runs.value.some((r) => (
  ['failed', 'failed_permanent'].includes(r.status)
  && RECOVERABLE_ERRORS.includes(r.error_code)
)))

const requeuing = ref(false)
async function requeueFailed() {
  if (!runsTarget.value) return
  requeuing.value = true
  try {
    const { data } = await http.post(
      `/campaigns/${runsTarget.value.id}/requeue-failed`,
    )
    ElMessage.success(`已重新入队 ${data.requeued} 条消息`)
    await loadRuns()
    await load()  // refresh list to show updated status / counters
  } finally { requeuing.value = false }
}

function formatRetry(iso) {
  // Compact "MM-DD HH:mm:ss" + relative "(还有 5 分钟)" — useful when
  // a wave of retries is queued so the operator sees the spacing.
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  const stamp = `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  const diffMs = d.getTime() - Date.now()
  if (diffMs <= 0) return `${stamp}（已到点）`
  const mins = Math.round(diffMs / 60000)
  if (mins < 1) return `${stamp}（<1 分钟）`
  if (mins < 60) return `${stamp}（还有 ${mins} 分钟）`
  const hrs = (mins / 60).toFixed(1)
  return `${stamp}（还有 ${hrs} 小时）`
}

function isOverdue(iso) {
  const d = new Date(iso)
  return !isNaN(d.getTime()) && d.getTime() <= Date.now()
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
.form-hint {
  font-size: 12px; color: #909399; line-height: 1.5; margin-top: 4px;
}
.form-hint code {
  background: #f0f0f0; padding: 1px 4px; border-radius: 2px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #d56565;
}
.runs-summary { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.muted { color: #909399; font-size: 12px; }
.overdue { color: #f56c6c; font-weight: 600; }
</style>
