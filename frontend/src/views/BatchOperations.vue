<template>
  <el-card class="page-card">
    <div class="toolbar">
      <el-input v-model="search" placeholder="任务 ID / 名字" clearable style="width: 240px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button type="primary" @click="openDialog">+ 新增</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <span class="hint">已支持执行：删除好友 / 退出群聊 / 检测双向 / 退出其他设备。仅申诉解双向待实现（Telegram 无公开 RPC）。</span>
    </div>

    <el-table :data="filteredRows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="任务名字" min-width="200" />
      <el-table-column label="账号组" min-width="160">
        <template #default="{ row }">{{ formatGroups(row.account_group_ids) }}</template>
      </el-table-column>
      <el-table-column prop="operation_target" label="操作对象" width="140">
        <template #default="{ row }">{{ OP_LABEL[row.operation_target] || row.operation_target }}</template>
      </el-table-column>
      <el-table-column prop="task_kind" label="类型" width="100" />
      <el-table-column prop="target_count" label="总数" width="80" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" link @click="action(row, 'start')">启动</el-button>
          <el-button size="small" link @click="action(row, 'pause')">暂停</el-button>
          <el-button size="small" link type="danger" @click="action(row, 'cancel')">取消</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" title="新增批量操作任务" width="780px" top="6vh">
    <div class="dialog-grid">
      <el-form :model="form" label-width="110px" class="dialog-form">
        <el-divider content-position="left">基础设置</el-divider>
        <el-form-item label="任务名字" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="操作对象" required>
          <el-select v-model="form.operation_target" style="width: 100%">
            <el-option v-for="op in OPERATIONS" :key="op.value" :label="op.label" :value="op.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号分组" required>
          <el-select v-model="form.account_group_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">账号执行设置</el-divider>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="失败次数"><el-input-number v-model="form.send_settings.max_per_account" :min="1" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="失败间隔(秒)"><el-input-number v-model="form.send_settings.failure_interval_seconds" :min="1" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="随机上限(秒)"><el-input-number v-model="form.send_settings.random_max_seconds" :min="0" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="线程数"><el-input-number v-model="form.send_settings.task_concurrency" :min="1" style="width: 100%" /></el-form-item></el-col>
        </el-row>
      </el-form>

      <div class="dialog-help">
        <el-card shadow="never" class="help-card">
          <div class="help-title">操作对象说明</div>
          <ul>
            <li><b>删除好友</b>：清空当前账号好友列表</li>
            <li><b>退出群聊</b>：让账号退出所有非业务群</li>
            <li><b>检测双向</b>：扫描互加好友（用于召回）</li>
            <li><b>退出其他设备</b>：踢掉账号在其他设备上的会话</li>
            <li><b>申诉解双向</b>：批量提交解除好友关系的申诉</li>
          </ul>
        </el-card>
        <el-card shadow="never" class="help-card">
          <div class="help-title">线程数 / 间隔</div>
          <p>线程数 = 同时操作多少个账号；间隔同样靠失败 + 随机叠加。</p>
          <p>同一账号失败累计达到上限会自动暂停该账号。</p>
        </el-card>
      </div>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="create">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const OPERATIONS = [
  { value: "delete_friend", label: "删除好友" },
  { value: "leave_group", label: "退出群聊" },
  { value: "detect_mutual", label: "检测双向" },
  { value: "leave_other_devices", label: "退出其他设备" },
  { value: "appeal_mutual", label: "申诉解双向" },
]
const OP_LABEL = Object.fromEntries(OPERATIONS.map((o) => [o.value, o.label]))

const rows = ref([])
const groups = ref([])
const loading = ref(false)
const search = ref('')
const dialogVisible = ref(false)
const creating = ref(false)

const defaultForm = () => ({
  name: `批量操作 - ${new Date().toLocaleString()}`,
  operation_target: 'delete_friend',
  account_group_ids: [],
  send_settings: {
    max_per_account: 3,
    failure_interval_seconds: 120,
    random_max_seconds: 30,
    task_concurrency: 100,
  },
})
const form = reactive(defaultForm())

const filteredRows = computed(() => {
  if (!search.value) return rows.value
  const kw = search.value.toLowerCase()
  return rows.value.filter((r) => `${r.id} ${r.name}`.toLowerCase().includes(kw))
})

function formatGroups(ids) {
  if (!ids?.length) return '—'
  return ids.map((id) => {
    const g = groups.value.find((x) => x.id === id)
    return g ? g.name : `#${id}`
  }).join(', ')
}

async function load() {
  loading.value = true
  try {
    const [{ data: r }, { data: g }] = await Promise.all([
      http.get('/campaigns', { params: { task_kind: 'batch_op' } }),
      groups.value.length ? Promise.resolve({ data: groups.value }) : http.get('/account-groups'),
    ])
    rows.value = r
    groups.value = g
  } finally { loading.value = false }
}

function openDialog() {
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

async function create() {
  if (!form.name || !form.operation_target || !form.account_group_ids.length) {
    ElMessage.warning('请填写任务名、操作对象和账号分组')
    return
  }
  creating.value = true
  try {
    await http.post('/campaigns', {
      name: form.name,
      task_kind: 'batch_op',
      operation_target: form.operation_target,
      account_group_ids: form.account_group_ids,
      send_settings: form.send_settings,
    })
    ElMessage.success('已创建')
    dialogVisible.value = false
    await load()
  } finally { creating.value = false }
}

async function action(row, name) {
  await http.post(`/campaigns/${row.id}/${name}`)
  ElMessage.success(`已${({ start: '启动', pause: '暂停', cancel: '取消' })[name]}`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #e6a23c; font-size: 12px; }
.dialog-grid { display: grid; grid-template-columns: 1fr 260px; gap: 16px; }
.dialog-form { min-width: 0; }
.dialog-help { display: flex; flex-direction: column; gap: 10px; max-height: 70vh; overflow-y: auto; }
.help-card { background: #fafafa; border: 1px solid #f0f0f0; }
:deep(.help-card .el-card__body) { padding: 10px 12px; }
.help-title { font-weight: 600; color: #303133; margin-bottom: 6px; font-size: 13px; }
.help-card ul { margin: 4px 0; padding-left: 18px; font-size: 12px; color: #606266; line-height: 1.7; }
.help-card p { margin: 4px 0; font-size: 12px; color: #606266; line-height: 1.6; }
</style>
