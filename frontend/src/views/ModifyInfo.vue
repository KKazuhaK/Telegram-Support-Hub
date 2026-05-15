<template>
  <el-card class="page-card">
    <div class="toolbar">
      <el-input v-model="search" placeholder="任务 ID / 名字" clearable style="width: 240px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button type="primary" @click="openDialog">+ 新增</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <span class="hint">已支持执行：修改昵称 / 用户名 / 签名。点「启动」即下发到 worker；改密码 / 改头像仍待实现。</span>
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
      <el-table-column label="参数预览" min-width="200">
        <template #default="{ row }">{{ row.extra_params ? JSON.stringify(row.extra_params) : '—' }}</template>
      </el-table-column>
      <el-table-column prop="target_count" label="账号数" width="100" />
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

  <el-dialog v-model="dialogVisible" title="新增修改资料任务" width="780px" top="6vh">
    <div class="dialog-grid">
      <el-form :model="form" label-width="110px" class="dialog-form">
        <el-divider content-position="left">基础设置</el-divider>
        <el-form-item label="任务名字" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="操作对象" required>
          <el-select v-model="form.operation_target" style="width: 100%" @change="onOpChange">
            <el-option v-for="op in OPERATIONS" :key="op.value" :label="op.label" :value="op.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号分组" required>
          <el-select v-model="form.account_group_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>

        <!-- Extra params per operation -->
        <template v-if="['modify_nickname', 'modify_username', 'modify_signature'].includes(form.operation_target)">
          <el-form-item :label="newValueLabel" required>
            <el-input v-model="form.extra_params.new_value" />
          </el-form-item>
        </template>
        <template v-if="form.operation_target === 'modify_password'">
          <el-form-item label="旧密码">
            <el-input v-model="form.extra_params.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="form.extra_params.new_password" type="password" show-password />
          </el-form-item>
        </template>
        <template v-if="form.operation_target === 'modify_avatar'">
          <el-form-item label="文件分组" required>
            <el-input v-model="form.extra_params.file_group" placeholder="待 R11 文件分组上线后改为下拉" />
          </el-form-item>
        </template>

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
            <li><b>修改密码</b>：批量为账号设置新两步验证密码</li>
            <li><b>修改头像</b>：使用资料分组中的图片轮换设置</li>
            <li><b>修改昵称 / 用户名 / 签名</b>：批量改文本字段</li>
          </ul>
        </el-card>
        <el-card shadow="never" class="help-card">
          <div class="help-title">必填参数</div>
          <ul>
            <li>修改昵称/用户名/签名：<code>new_value</code> 文本</li>
            <li>修改头像：<code>file_group</code> 资料分组</li>
            <li>修改密码：<code>old_password</code>（可选）+ <code>new_password</code></li>
          </ul>
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
  { value: "modify_password", label: "修改密码" },
  { value: "modify_avatar", label: "修改头像" },
  { value: "modify_nickname", label: "修改昵称" },
  { value: "modify_username", label: "修改用户名" },
  { value: "modify_signature", label: "修改签名" },
]
const OP_LABEL = Object.fromEntries(OPERATIONS.map((o) => [o.value, o.label]))

const rows = ref([])
const groups = ref([])
const loading = ref(false)
const search = ref('')
const dialogVisible = ref(false)
const creating = ref(false)

const defaultForm = () => ({
  name: `修改资料 - ${new Date().toLocaleString()}`,
  operation_target: 'modify_nickname',
  account_group_ids: [],
  extra_params: {},
  send_settings: {
    max_per_account: 3,
    failure_interval_seconds: 120,
    random_max_seconds: 30,
    task_concurrency: 100,
  },
})
const form = reactive(defaultForm())

const newValueLabel = computed(() => {
  return ({
    modify_nickname: '新昵称',
    modify_username: '新用户名',
    modify_signature: '新签名',
  })[form.operation_target] || '新值'
})

const filteredRows = computed(() => {
  if (!search.value) return rows.value
  const kw = search.value.toLowerCase()
  return rows.value.filter((r) => `${r.id} ${r.name}`.toLowerCase().includes(kw))
})

function onOpChange() {
  // Reset extra_params on op switch so stale fields don't get serialised.
  form.extra_params = {}
}

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
      http.get('/campaigns', { params: { task_kind: 'modify_info' } }),
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
      task_kind: 'modify_info',
      operation_target: form.operation_target,
      account_group_ids: form.account_group_ids,
      send_settings: form.send_settings,
      extra_params: form.extra_params,
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
.help-card code { background: #f0f0f0; padding: 1px 4px; border-radius: 2px; color: #d56565; font-size: 11px; }
</style>
