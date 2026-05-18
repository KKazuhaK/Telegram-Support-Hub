<template>
  <el-card class="page-card">
    <el-tabs v-model="statusTab" @tab-change="onStatusTabChange" class="status-tabs">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="启用" name="enabled" />
      <el-tab-pane label="待验证" name="imported" />
      <el-tab-pane label="正常" name="active" />
      <el-tab-pane label="受限" name="limited" />
      <el-tab-pane label="异常" name="error" />
      <el-tab-pane label="归档" name="archived" />
    </el-tabs>

    <div class="filter-row">
      <el-select v-model="filters.group_id" placeholder="账号分组" clearable style="width: 160px">
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-input v-model="filters.phone" placeholder="手机号关键字" clearable style="width: 180px" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button type="warning" @click="advancedDrawer = true">高级筛选</el-button>
      <el-button @click="resetFilters">重置</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="action-row">
      <el-button v-if="auth.isAdmin" type="primary" @click="openImportDialog">
        上传 session ZIP
      </el-button>
      <el-button-group v-if="auth.isAdmin">
        <el-button :disabled="!selectedIds.length" @click="batchEnabled(true)">上线</el-button>
        <el-button :disabled="!selectedIds.length" @click="batchEnabled(false)">下线</el-button>
        <el-button :disabled="!selectedIds.length" @click="batchStatus('archived')">归档</el-button>
        <el-button :disabled="!selectedIds.length" type="danger" @click="batchDelete">批量删除</el-button>
      </el-button-group>
      <el-button v-if="auth.isAdmin" :loading="validateAllBusy" @click="validateAll">立即验证全部</el-button>
      <el-dropdown v-if="auth.isAdmin" :disabled="!selectedIds.length" @command="onMoreCommand">
        <el-button :disabled="!selectedIds.length">
          更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="move-group">转移到分组</el-dropdown-item>
            <el-dropdown-item command="bind-proxy">分配代理</el-dropdown-item>
            <el-dropdown-item command="unbind-proxy">解绑代理</el-dropdown-item>
            <el-dropdown-item command="modify-info" divided>跳转『修改资料』</el-dropdown-item>
            <el-dropdown-item command="batch-op">跳转『批量操作』</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="hint">已选 {{ selectedIds.length }} 个</span>
    </div>

    <el-drawer v-model="advancedDrawer" title="高级筛选" size="380px" direction="rtl">
      <el-form :model="filters" label-width="100px">
        <el-form-item label="账号昵称">
          <el-input v-model="filters.nickname" clearable />
        </el-form-item>
        <el-form-item label="国家代码">
          <el-input v-model="filters.country" clearable placeholder="如 CN / US" />
        </el-form-item>
        <el-form-item label="头像状态">
          <el-select v-model="filters.avatar_status" clearable style="width: 100%">
            <el-option label="已上传" value="set" />
            <el-option label="未上传" value="empty" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否绑代理">
          <el-select v-model="filters.has_proxy" clearable style="width: 100%">
            <el-option label="已绑定" :value="true" />
            <el-option label="未绑定" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注关键字">
          <el-input v-model="filters.remark" clearable />
        </el-form-item>
        <el-form-item label="最近登录">
          <el-date-picker
            v-model="filters.range" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始日期" end-placeholder="结束日期" style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetAdvanced">重置高级</el-button>
        <el-button type="primary" @click="applyAdvanced">查询</el-button>
      </template>
    </el-drawer>

    <el-dialog v-model="moveGroupDialog" title="转移到分组" width="420px">
      <el-form :model="moveGroupForm" label-width="100px">
        <el-form-item label="目标分组">
          <el-select v-model="moveGroupForm.group_id" style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <p class="hint" style="margin-left: 100px">将清空所选账号现有主分组，并加入目标分组。</p>
      </el-form>
      <template #footer>
        <el-button @click="moveGroupDialog = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="doMoveGroup">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="limitsDialog" title="账号发送限额" width="420px">
      <el-form v-if="limitsTarget" label-width="100px">
        <el-form-item label="账号">
          <el-input :model-value="limitsTarget.phone || limitsTarget.tg_user_id" disabled />
        </el-form-item>
        <el-form-item label="日上限">
          <el-input-number v-model="limitsForm.daily_limit" :min="0" :max="500"
                           controls-position="right" style="width: 100%" />
          <div class="muted" style="font-size:12px;">
            新号建议 20，warming up 后可拉到 60-100。0 = 关闭限制（不推荐）。
          </div>
        </el-form-item>
        <el-form-item label="时上限">
          <el-input-number v-model="limitsForm.hourly_limit" :min="0" :max="200"
                           controls-position="right" style="width: 100%"
                           placeholder="不限" />
          <div class="muted" style="font-size:12px;">
            可选。留空 / 0 = 不限。建议 10-20 防止短时间集中发送。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="limitsDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingLimits" @click="saveLimits">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialog" title="上传 session ZIP" width="520px">
      <el-form label-width="100px">
        <el-form-item label="目标分组" required>
          <el-select v-model="importGroupId" placeholder="必选 —— 新号会归入该分组"
                     style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动分配代理">
          <el-select v-model="importProxyGroupId" placeholder="不分配代理"
                     clearable style="width: 100%"
                     @change="loadProxyGroups">
            <el-option v-for="g in proxyGroups" :key="g.id"
                       :label="`${g.name}（${g.count || 0} 个代理）`" :value="g.id" />
          </el-select>
          <div class="muted" style="font-size:12px;">
            选了 → 新号自动从该分组里轮询绑代理。已绑代理的老号不重绑。
          </div>
        </el-form-item>
        <el-form-item v-if="importProxyGroupId" label="每代理上限">
          <el-input-number v-model="importMaxPerProxy" :min="1" :max="50"
                           controls-position="right" style="width: 100%" />
          <div class="muted" style="font-size:12px;">
            单个代理最多绑几个号。一般 3-5 个，避免一个 IP 出口流量过大被 TG 风控。
          </div>
        </el-form-item>
        <el-form-item label="文件">
          <el-upload
            :http-request="uploadZip"
            :show-file-list="false"
            :before-upload="beforeImportUpload"
            accept=".zip">
            <el-button type="primary" :disabled="!importGroupId">选择 ZIP 并开始导入</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <div class="muted" style="font-size:12px;line-height:1.6;">
        强制选分组：客服只能看到名下分组里 TG 号收到的客户。要"一个客服一批号"严格隔离，建议为每个客服建专属分组。
      </div>
      <template #footer>
        <el-button @click="importDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bindProxyDialog" title="分配代理" width="420px">
      <el-form label-width="100px">
        <el-form-item label="代理">
          <el-select v-model="bindProxyForm.proxy_id" filterable style="width: 100%">
            <el-option v-for="p in proxies" :key="p.id"
                       :label="`${p.name} (${p.host}:${p.port})`" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bindProxyDialog = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="doBindProxy">确定</el-button>
      </template>
    </el-dialog>

    <el-table
      ref="tableRef"
      :data="rows"
      v-loading="loading"
      stripe
      size="small"
      row-key="id"
      @selection-change="(rows) => (selectedRows = rows)"
    >
      <el-table-column type="selection" width="44" reserve-selection />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="tg_user_id" label="TG ID" min-width="120" />
      <el-table-column prop="phone" label="手机号" width="160" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :disabled="!auth.isAdmin"
            @change="(v) => toggleEnabled(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="daily_limit" label="日上限" width="90" />
      <el-table-column label="时上限" width="90">
        <template #default="{ row }">{{ row.hourly_limit ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="sent_today" label="今日已发" width="100" />
      <el-table-column prop="total_sent" label="累计发送" width="100" />
      <el-table-column prop="total_replies" label="累计回复" width="100" />
      <el-table-column prop="proxy_id" label="代理" width="80">
        <template #default="{ row }">{{ row.proxy_id || '未绑定' }}</template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" width="170" />
      <el-table-column label="操作" width="320" v-if="auth.isAdmin">
        <template #default="{ row }">
          <el-button size="small" link :loading="row._validating" @click="validateNow(row)">验证</el-button>
          <el-button size="small" link @click="openLimitsDialog(row)">限额</el-button>
          <el-button size="small" link @click="openTestSend(row)">测试发送</el-button>
          <el-button size="small" link @click="autoBindProxy(row)">自动代理</el-button>
          <el-popconfirm title="确认解绑代理？" @confirm="unbindProxy(row)">
            <template #reference>
              <el-button size="small" link type="danger" :disabled="!row.proxy_id">解绑</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <!-- Admin-only single-shot test send. Used to verify a TG account can
       actually reach a target without setting up a campaign. -->
  <el-dialog v-model="testSendDialog" title="测试发送" width="520px">
    <el-form label-position="top" :model="testForm">
      <el-form-item label="使用账号">
        <el-input :value="testForm.account_label" disabled />
      </el-form-item>
      <el-form-item label="目标类型">
        <el-radio-group v-model="testForm.target_kind">
          <el-radio-button value="phone">手机号</el-radio-button>
          <el-radio-button value="tg_user_id">TG ID / 用户名</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="testForm.target_kind === 'phone' ? '手机号（含国家码）' : 'TG 数字 ID 或 @username'">
        <el-input
          v-model="testForm.target"
          :placeholder="testForm.target_kind === 'phone' ? '+12025550100' : '123456789 或 @somebody'"
        />
      </el-form-item>
      <el-form-item label="消息内容">
        <el-input v-model="testForm.text" type="textarea" :rows="4" placeholder="测试消息内容…" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="testSendDialog = false">取消</el-button>
      <el-button
        type="primary"
        :loading="testSending"
        :disabled="!testForm.target.trim() || !testForm.text.trim()"
        @click="submitTestSend"
      >发送</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const rows = ref([])
const groups = ref([])
const proxies = ref([])
const loading = ref(false)
const busy = ref(false)
const statusTab = ref('all')
const filters = reactive({
  group_id: null, phone: '',
  nickname: '', country: '', avatar_status: '', has_proxy: null,
  remark: '', range: [],
})

const advancedDrawer = ref(false)
const moveGroupDialog = ref(false)
const moveGroupForm = reactive({ group_id: null })
const bindProxyDialog = ref(false)
const bindProxyForm = reactive({ proxy_id: null })

const tableRef = ref(null)
const selectedRows = ref([])
const selectedIds = computed(() => selectedRows.value.map((r) => r.id))

const STATUS_LABEL = {
  imported: '待验证', active: '正常', paused: '暂停',
  limited: '受限', error: '异常', archived: '归档',
}
const STATUS_TYPE = {
  imported: 'info', active: 'success', paused: 'warning',
  limited: 'warning', error: 'danger', archived: '',
}
function statusLabel(s) { return STATUS_LABEL[s] || s }
function statusType(s) { return STATUS_TYPE[s] || 'info' }

function buildParams() {
  const params = {}
  if (statusTab.value === 'enabled') params.enabled = true
  else if (statusTab.value !== 'all') params.status = statusTab.value
  if (filters.group_id) params.group_id = filters.group_id
  if (filters.phone) params.phone = filters.phone
  if (filters.nickname) params.nickname = filters.nickname
  if (filters.country) params.country = filters.country
  if (filters.avatar_status) params.avatar_status = filters.avatar_status
  if (filters.has_proxy !== null && filters.has_proxy !== '') params.has_proxy = filters.has_proxy
  if (filters.remark) params.remark = filters.remark
  if (filters.range?.length === 2) {
    params.from_date = filters.range[0]
    params.to_date = filters.range[1]
  }
  return params
}

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/accounts', { params: buildParams() })
    rows.value = data
    if (groups.value.length === 0) {
      const { data: g } = await http.get('/account-groups')
      groups.value = g
    }
  } finally { loading.value = false }
}

function resetFilters() {
  filters.group_id = null
  filters.phone = ''
  filters.nickname = ''
  filters.country = ''
  filters.avatar_status = ''
  filters.has_proxy = null
  filters.remark = ''
  filters.range = []
  statusTab.value = 'all'
  load()
}

function resetAdvanced() {
  filters.nickname = ''
  filters.country = ''
  filters.avatar_status = ''
  filters.has_proxy = null
  filters.remark = ''
  filters.range = []
}

function applyAdvanced() {
  advancedDrawer.value = false
  load()
}

async function onMoreCommand(cmd) {
  if (cmd === 'move-group') {
    moveGroupForm.group_id = null
    moveGroupDialog.value = true
  } else if (cmd === 'bind-proxy') {
    if (!proxies.value.length) {
      const { data } = await http.get('/proxies')
      proxies.value = data
    }
    bindProxyForm.proxy_id = null
    bindProxyDialog.value = true
  } else if (cmd === 'unbind-proxy') {
    await ElMessageBox.confirm(
      `确认解绑 ${selectedIds.value.length} 个账号的代理？`,
      '解绑代理',
      { type: 'warning' },
    )
    await http.post('/accounts/batch', {
      ids: selectedIds.value, proxy_id: null, clear_proxy: true,
    })
    ElMessage.success('已解绑代理')
    tableRef.value?.clearSelection?.()
    await load()
  } else if (cmd === 'modify-info') {
    router.push({ name: 'modify-info' })
  } else if (cmd === 'batch-op') {
    router.push({ name: 'batch-operations' })
  }
}

async function doMoveGroup() {
  if (!moveGroupForm.group_id) { ElMessage.warning('请选择目标分组'); return }
  busy.value = true
  try {
    await http.post('/accounts/batch', {
      ids: selectedIds.value, move_to_group_id: moveGroupForm.group_id,
    })
    ElMessage.success(`已转移 ${selectedIds.value.length} 个账号`)
    moveGroupDialog.value = false
    tableRef.value?.clearSelection?.()
    await load()
  } finally { busy.value = false }
}

async function doBindProxy() {
  if (!bindProxyForm.proxy_id) { ElMessage.warning('请选择代理'); return }
  busy.value = true
  try {
    await http.post('/accounts/batch', {
      ids: selectedIds.value, proxy_id: bindProxyForm.proxy_id,
    })
    ElMessage.success(`已为 ${selectedIds.value.length} 个账号分配代理`)
    bindProxyDialog.value = false
    tableRef.value?.clearSelection?.()
    await load()
  } finally { busy.value = false }
}

function onStatusTabChange() {
  load()
}

const importDialog = ref(false)
const importGroupId = ref(null)
const importProxyGroupId = ref(null)
const importMaxPerProxy = ref(3)
const proxyGroups = ref([])

async function loadProxyGroups() {
  try {
    const { data } = await http.get('/proxy-groups')
    proxyGroups.value = data || []
  } catch (_) { /* toast already fired */ }
}

const limitsDialog = ref(false)
const limitsTarget = ref(null)
const limitsForm = reactive({ daily_limit: 20, hourly_limit: 0 })
const savingLimits = ref(false)

function openLimitsDialog(row) {
  limitsTarget.value = row
  limitsForm.daily_limit = row.daily_limit ?? 20
  // null in DB → 0 in the input means "uncapped"; we coerce back on save.
  limitsForm.hourly_limit = row.hourly_limit ?? 0
  limitsDialog.value = true
}

async function saveLimits() {
  if (!limitsTarget.value) return
  savingLimits.value = true
  try {
    await http.patch(`/accounts/${limitsTarget.value.id}`, {
      daily_limit: limitsForm.daily_limit,
      hourly_limit: limitsForm.hourly_limit > 0 ? limitsForm.hourly_limit : null,
    })
    ElMessage.success('已保存')
    limitsDialog.value = false
    await load()
  } finally { savingLimits.value = false }
}

async function openImportDialog() {
  // Pre-load groups so the dropdown is populated when the dialog opens.
  if (!groups.value.length) {
    const { data: g } = await http.get('/account-groups')
    groups.value = g
  }
  if (!proxyGroups.value.length) await loadProxyGroups()
  importGroupId.value = null
  importProxyGroupId.value = null
  importMaxPerProxy.value = 3
  importDialog.value = true
}

function beforeImportUpload() {
  if (!importGroupId.value) {
    ElMessage.warning('请先选择目标分组')
    return false
  }
  return true
}

async function uploadZip({ file }) {
  if (!importGroupId.value) {
    ElMessage.warning('请先选择目标分组')
    return
  }
  const fd = new FormData()
  fd.append('sessions', file)
  fd.append('group_id', String(importGroupId.value))
  if (importProxyGroupId.value) {
    fd.append('proxy_group_id', String(importProxyGroupId.value))
    if (importMaxPerProxy.value) {
      fd.append('max_accounts_per_proxy', String(importMaxPerProxy.value))
    }
  }
  const { data } = await http.post('/accounts/import-zip', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  const ok = data.imported.length
  const skipped = data.skipped || []
  if (skipped.length) {
    // Surface per-entry reasons so the operator can self-diagnose (esp.
    // for tdata zips where conversion can fail per-phone). HTML mode
    // because ElMessageBox plain text doesn't wrap long messages well.
    const esc = (s) => String(s ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const reasons = skipped.slice(0, 10)
      .map((s) => `<div style="margin-bottom:6px;"><b>${esc(s.file)}</b><br><span style="color:#888;">${esc(s.reason)}</span></div>`)
      .join('')
    const more = skipped.length > 10
      ? `<div style="color:#aaa; font-size:12px;">… 还有 ${skipped.length - 10} 条</div>`
      : ''
    ElMessageBox.alert(
      `<div style="font-size:13px;">${reasons}${more}</div>`,
      `导入完成：成功 ${ok} 个，跳过 ${skipped.length} 个`,
      { confirmButtonText: '知道了', dangerouslyUseHTMLString: true },
    )
  } else {
    let msg = `导入 ${ok} 个`
    if (importProxyGroupId.value) {
      msg += `，已绑代理 ${data.proxy_assigned || 0} 个`
      if (data.proxy_no_pool) {
        msg += `（${data.proxy_no_pool} 个代理池已满未绑）`
      }
    }
    ElMessage.success(msg)
  }
  importDialog.value = false
  await load()
}

async function toggleEnabled(row, enabled) {
  await http.patch(`/accounts/${row.id}`, { enabled })
  await load()
}

async function batchEnabled(enabled) {
  // Confirm to avoid an accidental click on a 100-row selection
  // silently flipping every account offline.
  try {
    await ElMessageBox.confirm(
      `${enabled ? '上线' : '下线'} ${selectedIds.value.length} 个账号？`,
      enabled ? '批量上线' : '批量下线',
      { type: enabled ? 'info' : 'warning' },
    )
  } catch (_) { return }
  await http.post('/accounts/batch', { ids: selectedIds.value, enabled })
  ElMessage.success(`已${enabled ? '上线' : '下线'} ${selectedIds.value.length} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function batchStatus(status) {
  try {
    await ElMessageBox.confirm(
      `把 ${selectedIds.value.length} 个账号设为「${statusLabel(status)}」？`,
      '批量改状态', { type: 'warning' },
    )
  } catch (_) { return }
  await http.post('/accounts/batch', { ids: selectedIds.value, status })
  ElMessage.success(`已设为「${statusLabel(status)}」 ${selectedIds.value.length} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function batchDelete() {
  await ElMessageBox.confirm(
    `确定删除选中的 ${selectedIds.value.length} 个账号？此操作不可撤销。`,
    '批量删除',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
  const { data } = await http.delete('/accounts/batch', { data: { ids: selectedIds.value } })
  ElMessage.success(`已删除 ${data.deleted} 个账号`)
  tableRef.value?.clearSelection?.()
  await load()
}

async function autoBindProxy(row) {
  await http.post(`/accounts/${row.id}/proxy/auto`)
  ElMessage.success('代理已自动绑定')
  await load()
}

async function unbindProxy(row) {
  await http.delete(`/accounts/${row.id}/proxy`)
  await load()
}

// --- validate now ---
const validateAllBusy = ref(false)

async function validateNow(row) {
  row._validating = true
  try {
    const { data } = await http.post(`/accounts/${row.id}/validate`)
    if (data.ok) {
      ElMessage.success(`账号 #${row.id} 验证成功，状态：${data.status}`)
    } else {
      ElMessage.error(`账号 #${row.id} 验证失败：${data.error_message || data.error_code}`)
    }
    await load()
  } catch (_) {
    // http.js already toasted
  } finally {
    row._validating = false
  }
}

async function validateAll() {
  validateAllBusy.value = true
  try {
    await http.post('/accounts/validate-all')
    ElMessage.success('已派发验证任务，几秒后刷新查看结果')
    // Refresh after a short delay so worker has time to start updating rows.
    setTimeout(() => load(), 3000)
  } finally {
    validateAllBusy.value = false
  }
}

// --- test send (admin smoke test) ---
const testSendDialog = ref(false)
const testSending = ref(false)
const testForm = reactive({
  account_id: null,
  account_label: '',
  target: '',
  target_kind: 'phone',
  text: '',
})

function openTestSend(row) {
  testForm.account_id = row.id
  testForm.account_label = `#${row.id} ${row.phone || row.tg_user_id} (${row.status || ''})`
  testForm.target = ''
  testForm.target_kind = 'phone'
  testForm.text = '这是一条测试消息'
  testSendDialog.value = true
}

async function submitTestSend() {
  testSending.value = true
  try {
    const { data } = await http.post(
      `/accounts/${testForm.account_id}/test-send`,
      {
        target: testForm.target.trim(),
        target_kind: testForm.target_kind,
        text: testForm.text,
      },
    )
    ElMessage.success(`发送成功！消息 ID: ${data.external_message_id || data.id}`)
    testSendDialog.value = false
  } catch (_) {
    // http.js already surfaced the friendly error toast (502 etc.).
  } finally {
    testSending.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.status-tabs { margin-bottom: 8px; }
:deep(.status-tabs .el-tabs__header) { margin-bottom: 12px; }

.filter-row {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 12px;
}
.action-row {
  display: flex; gap: 12px; align-items: center; margin-bottom: 12px;
}
.hint { color: #999; font-size: 12px; }
</style>
