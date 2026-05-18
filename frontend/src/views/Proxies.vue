<template>
  <el-card class="page-card">
    <div class="two-pane">
      <div class="left-pane">
        <div class="pane-toolbar">
          <el-button type="primary" size="small" @click="openGroupDialog()">⊕ 新增组</el-button>
          <el-button size="small" @click="loadGroups">刷新</el-button>
        </div>
        <el-scrollbar class="group-list">
          <div
            class="group-item"
            :class="{ active: activeGroupId === null }"
            @click="selectGroup(null)"
          >
            <div class="group-name">全部代理<span class="group-count">({{ totalAll }})</span></div>
            <div class="group-sub">不区分分组</div>
          </div>
          <div class="group-item" :class="{ active: activeGroupId === 0 }" @click="selectGroup(0)">
            <div class="group-name">未分组<span class="group-count">({{ ungroupedCount }})</span></div>
            <div class="group-sub">尚未划入任何分组</div>
          </div>
          <div
            v-for="g in groups"
            :key="g.id"
            class="group-item"
            :class="{ active: activeGroupId === g.id }"
            @click="selectGroup(g.id)"
          >
            <div class="group-name">{{ g.name }}<span class="group-count">({{ g.count ?? 0 }})</span></div>
            <div class="group-sub">{{ g.remark || '—' }}</div>
            <div class="group-actions">
              <el-button size="small" link @click.stop="openGroupDialog(g)">编辑</el-button>
              <el-popconfirm title="删除分组（代理将变为未分组）？" @confirm="deleteGroup(g)">
                <template #reference>
                  <el-button size="small" link type="danger" @click.stop>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </el-scrollbar>
      </div>

      <div class="right-pane">
        <div class="toolbar">
          <el-button type="primary" @click="openProxyDialog">+ 新增代理</el-button>
          <el-button @click="openImportDialog">📋 批量导入</el-button>
          <el-button :loading="loading" @click="loadItems">刷新</el-button>
        </div>
        <el-table :data="items" v-loading="loading" stripe size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="protocol" label="类型" width="80" />
          <el-table-column label="代理地址" min-width="200">
            <template #default="{ row }">{{ row.host }}:{{ row.port }}</template>
          </el-table-column>
          <el-table-column prop="country" label="国家" width="80" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="latency_ms" label="延迟" width="80" />
          <el-table-column prop="last_error" label="最近错误" show-overflow-tooltip />
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button size="small" link @click="checkProxy(row)">检测</el-button>
              <el-button size="small" link @click="openProxyDialog(row)">编辑</el-button>
              <el-popconfirm
                title="禁用后该代理不再参与调度；已绑定的账号会被标 proxy_error。确认禁用？"
                @confirm="deleteProxy(row)"
              >
                <template #reference>
                  <el-button size="small" link type="danger" :disabled="row.status === 'disabled'">
                    {{ row.status === 'disabled' ? '已禁用' : '禁用' }}
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </el-card>

  <el-dialog v-model="groupDialog" :title="groupForm.id ? '编辑代理分组' : '新增代理分组'" width="420px">
    <el-form :model="groupForm" label-width="80px">
      <el-form-item label="名称" required><el-input v-model="groupForm.name" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="groupForm.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="groupDialog = false">取消</el-button>
      <el-button type="primary" @click="saveGroup">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="proxyDialog" :title="proxyForm.id ? '编辑代理' : '新建代理'" width="480px">
    <el-form :model="proxyForm" label-width="80px">
      <el-form-item label="所属分组">
        <el-select v-model="proxyForm.group_id" clearable>
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="名称" required><el-input v-model="proxyForm.name" /></el-form-item>
      <el-form-item label="协议">
        <el-select v-model="proxyForm.protocol">
          <el-option label="socks5" value="socks5" />
          <el-option label="http" value="http" />
          <el-option label="https" value="https" />
        </el-select>
      </el-form-item>
      <el-form-item label="主机"><el-input v-model="proxyForm.host" /></el-form-item>
      <el-form-item label="端口"><el-input-number v-model="proxyForm.port" :min="1" :max="65535" /></el-form-item>
      <el-form-item label="用户名"><el-input v-model="proxyForm.username" /></el-form-item>
      <el-form-item label="密码">
        <el-input
          v-model="proxyForm.password"
          type="password"
          show-password
          :placeholder="proxyForm.id ? '留空表示不修改' : ''"
        />
      </el-form-item>
      <el-form-item label="国家"><el-input v-model="proxyForm.country" placeholder="如 CN" /></el-form-item>
      <el-form-item label="最大账号"><el-input-number v-model="proxyForm.max_accounts" :min="0" /></el-form-item>
      <el-form-item v-if="proxyForm.id" label="状态">
        <el-select v-model="proxyForm.status">
          <el-option label="active" value="active" />
          <el-option label="unchecked" value="unchecked" />
          <el-option label="error" value="error" />
          <el-option label="disabled" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注"><el-input v-model="proxyForm.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="proxyDialog = false">取消</el-button>
      <el-button type="primary" :loading="savingProxy" @click="saveProxy">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="importDialog" title="批量导入代理" width="640px" top="6vh">
    <el-form label-width="80px">
      <el-form-item label="协议">
        <el-radio-group v-model="importForm.protocol" size="small">
          <el-radio value="socks5">SOCKS5</el-radio>
          <el-radio value="socks4">SOCKS4</el-radio>
          <el-radio value="http">HTTP</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="分组">
        <el-select v-model="importForm.group_id" placeholder="不分组" clearable style="width: 100%">
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="代理列表">
        <el-input v-model="importForm.text" type="textarea" :rows="10"
                  placeholder="每行一条，支持 host:port 或 host:port:user:pass &#10;例如：&#10;207.228.46.141:1337:user:pass&#10;107.180.175.124:1337:user:pass" />
        <div style="font-size:12px;color:#909399;margin-top:4px;line-height:1.5;">
          已存在的代理（同 host + port + user）自动跳过。格式错误的行跳过并在结果里列出。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="importDialog = false">取消</el-button>
      <el-button type="primary" :loading="importing" @click="doImport">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const groups = ref([])
const allItems = ref([])
const items = ref([])
const loading = ref(false)
const activeGroupId = ref(null)  // null = all, 0 = ungrouped, n = group id

const totalAll = computed(() => allItems.value.length)
const ungroupedCount = computed(() => allItems.value.filter((p) => !p.group_id).length)

const groupDialog = ref(false)
const groupForm = reactive({ id: null, name: '', remark: '' })

const proxyDialog = ref(false)
const savingProxy = ref(false)
const proxyForm = reactive({
  id: null,
  group_id: null, name: '', protocol: 'socks5', host: '', port: 1080,
  username: '', password: '', country: '', max_accounts: 5,
  status: 'unchecked', remark: '',
})

async function loadGroups() {
  const { data } = await http.get('/proxy-groups')
  groups.value = data
}

async function loadAllItems() {
  const { data } = await http.get('/proxies')
  allItems.value = data
  filterItems()
}

async function loadItems() {
  loading.value = true
  try {
    await loadAllItems()
  } finally { loading.value = false }
}

function filterItems() {
  if (activeGroupId.value === null) items.value = allItems.value
  else if (activeGroupId.value === 0) items.value = allItems.value.filter((p) => !p.group_id)
  else items.value = allItems.value.filter((p) => p.group_id === activeGroupId.value)
}

function selectGroup(id) {
  activeGroupId.value = id
  filterItems()
}

function openGroupDialog(g = null) {
  if (g) Object.assign(groupForm, { id: g.id, name: g.name, remark: g.remark || '' })
  else Object.assign(groupForm, { id: null, name: '', remark: '' })
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.name) { ElMessage.warning('请输入分组名'); return }
  if (groupForm.id) {
    await http.patch(`/proxy-groups/${groupForm.id}`, { name: groupForm.name, remark: groupForm.remark })
  } else {
    await http.post('/proxy-groups', { name: groupForm.name, remark: groupForm.remark })
  }
  groupDialog.value = false
  await loadGroups()
  ElMessage.success('已保存')
}

async function deleteGroup(g) {
  await http.delete(`/proxy-groups/${g.id}`)
  if (activeGroupId.value === g.id) activeGroupId.value = null
  await loadGroups()
  await loadItems()
}

const importDialog = ref(false)
const importForm = reactive({ protocol: 'socks5', group_id: null, text: '' })
const importing = ref(false)

function openImportDialog() {
  importForm.protocol = 'socks5'
  importForm.group_id = activeGroupId.value && activeGroupId.value > 0
    ? activeGroupId.value : null
  importForm.text = ''
  importDialog.value = true
}

async function doImport() {
  if (!importForm.text.trim()) { ElMessage.warning('请粘贴代理列表'); return }
  importing.value = true
  try {
    const { data } = await http.post('/proxies/import-text', {
      text: importForm.text,
      protocol: importForm.protocol,
      group_id: importForm.group_id,
    })
    const created = data.created?.length || 0
    const dup = data.duplicated_count || 0
    const skipped = data.skipped?.length || 0
    if (skipped > 0) {
      // Show parse failures so the user can fix and re-paste.
      const lines = data.skipped.slice(0, 10)
        .map((s) => `  • ${s.line}（${s.reason}）`).join('\n')
      const more = skipped > 10 ? `\n（还有 ${skipped - 10} 行）` : ''
      ElMessage({
        type: 'warning', duration: 8000,
        message: `导入：新建 ${created}，重复跳过 ${dup}，格式错误 ${skipped}\n${lines}${more}`,
      })
    } else {
      ElMessage.success(`导入：新建 ${created}，重复跳过 ${dup}`)
    }
    importDialog.value = false
    await loadItems()
    await loadGroups()
  } finally { importing.value = false }
}

function openProxyDialog(row = null) {
  if (row) {
    Object.assign(proxyForm, {
      id: row.id,
      group_id: row.group_id ?? null,
      name: row.name || '',
      protocol: row.protocol || 'socks5',
      host: row.host || '',
      port: row.port || 1080,
      username: row.username || '',
      password: '',  // never echo back the stored password
      country: row.country || '',
      max_accounts: row.max_accounts ?? 5,
      status: row.status || 'unchecked',
      remark: row.remark || '',
    })
  } else {
    Object.assign(proxyForm, {
      id: null,
      group_id: typeof activeGroupId.value === 'number' && activeGroupId.value > 0 ? activeGroupId.value : null,
      name: '', protocol: 'socks5', host: '', port: 1080,
      username: '', password: '', country: '', max_accounts: 5,
      status: 'unchecked', remark: '',
    })
  }
  proxyDialog.value = true
}

async function saveProxy() {
  if (!proxyForm.name || !proxyForm.host) {
    ElMessage.warning('请填写名称和主机')
    return
  }
  savingProxy.value = true
  try {
    if (proxyForm.id) {
      // PATCH only sends fields the user actually filled. Empty password
      // means "don't change", not "set to empty".
      const payload = {
        group_id: proxyForm.group_id,
        name: proxyForm.name,
        protocol: proxyForm.protocol,
        host: proxyForm.host,
        port: proxyForm.port,
        username: proxyForm.username,
        country: proxyForm.country,
        max_accounts: proxyForm.max_accounts,
        status: proxyForm.status,
        remark: proxyForm.remark,
      }
      if (proxyForm.password) payload.password = proxyForm.password
      await http.patch(`/proxies/${proxyForm.id}`, payload)
      ElMessage.success('已更新')
    } else {
      await http.post('/proxies', {
        group_id: proxyForm.group_id,
        name: proxyForm.name,
        protocol: proxyForm.protocol,
        host: proxyForm.host,
        port: proxyForm.port,
        username: proxyForm.username,
        password: proxyForm.password,
        country: proxyForm.country,
        max_accounts: proxyForm.max_accounts,
        remark: proxyForm.remark,
      })
      ElMessage.success('已创建')
    }
    proxyDialog.value = false
    await loadGroups()
    await loadItems()
  } finally {
    savingProxy.value = false
  }
}

async function deleteProxy(row) {
  // No dedicated DELETE endpoint yet; "disable" via PATCH instead so
  // existing account bindings stay intact but the proxy won't be used.
  await http.patch(`/proxies/${row.id}`, { status: 'disabled' })
  ElMessage.success(`已禁用代理 ${row.name}`)
  await loadGroups()
  await loadItems()
}

async function checkProxy(row) {
  await http.post(`/proxies/${row.id}/check`)
  ElMessage.success('检测完成')
  await loadItems()
}

onMounted(async () => {
  await loadGroups()
  await loadItems()
})
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.two-pane { display: grid; grid-template-columns: 260px 1fr; gap: 12px; }
.left-pane { border-right: 1px solid #f0f0f0; padding-right: 12px; }
.pane-toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.group-list { max-height: calc(100vh - 280px); }
.group-item {
  padding: 8px 10px; border: 1px solid #e5e6eb; border-radius: 4px;
  margin-bottom: 6px; cursor: pointer; transition: all 0.15s; background: #fff;
}
.group-item:hover { border-color: var(--el-color-primary); }
.group-item.active { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary); }
.group-name { font-weight: 500; font-size: 14px; color: #303133; }
.group-count { color: var(--el-color-primary); margin-left: 4px; font-weight: 600; }
.group-sub { font-size: 12px; color: #909399; margin-top: 2px; }
.group-actions { margin-top: 4px; }
.right-pane { min-width: 0; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
</style>
