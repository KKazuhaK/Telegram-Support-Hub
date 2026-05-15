<template>
  <el-card class="page-card">
    <div class="page-header">
      <h2>商户账号列表</h2>
      <div>
        <el-button :disabled="!selectedIds.length" @click="batchToggle(false)">⚙ 批量禁用</el-button>
        <el-button :disabled="!selectedIds.length" type="primary" @click="batchToggle(true)">⚙ 批量启用</el-button>
        <el-button type="primary" @click="openDialog()">+ 新建商户账号</el-button>
      </div>
    </div>

    <div class="filter-row">
      <el-select v-model="filters.business_agent_id" placeholder="所属商务代理" clearable style="width: 200px">
        <el-option v-for="a in agents" :key="a.id" :label="`${a.name}(${a.nickname || ''})`" :value="a.id" />
      </el-select>
      <el-input v-model="filters.q" placeholder="账号/昵称" clearable style="width: 200px" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
        <el-option label="启用" :value="true" />
        <el-option label="禁用" :value="false" />
      </el-select>
      <el-select v-model="filters.online_status" placeholder="是否在线" clearable style="width: 140px">
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
      </el-select>
      <el-button @click="reset">重置</el-button>
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe size="small" @selection-change="(rs) => (selectedRows = rs)">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="name" label="账号名称" min-width="120" />
      <el-table-column prop="nickname" label="昵称" min-width="120" />
      <el-table-column label="所属代理" width="160">
        <template #default="{ row }">{{ agentLabel(row.business_agent_id) }}</template>
      </el-table-column>
      <el-table-column prop="statistic_time" label="统计时间" width="100" />
      <el-table-column label="端口" width="160">
        <template #default="{ row }">
          <el-tag size="small">{{ row.ports_used }} / {{ row.ports_total }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ports_expires_at" label="端口到期" width="180" />
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.status" @change="(v) => toggleStatus(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="online_status" label="在线" width="80">
        <template #default="{ row }">
          <el-tag :type="row.online_status === 'online' ? 'success' : 'info'" size="small">
            {{ row.online_status === 'online' ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑商户账号' : '新建商户账号'" width="560px">
    <el-form :model="form" label-width="110px">
      <el-form-item label="账号名称" required><el-input v-model="form.name" :disabled="!!form.id" /></el-form-item>
      <el-form-item label="密码" :required="!form.id">
        <el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '留空则不修改' : ''" />
      </el-form-item>
      <el-form-item label="昵称" required><el-input v-model="form.nickname" /></el-form-item>
      <el-form-item label="所属商务代理">
        <el-select v-model="form.business_agent_id" clearable>
          <el-option v-for="a in agents" :key="a.id" :label="`${a.name}(${a.nickname || ''})`" :value="a.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态"><el-switch v-model="form.status" /></el-form-item>
      <el-form-item label="统计时间">
        <el-time-select v-model="form.statistic_time" :start="'00:00'" :step="'00:30'" :end="'23:30'" />
      </el-form-item>
      <el-divider content-position="left">端口配额</el-divider>
      <el-form-item label="端口总数"><el-input-number v-model="form.ports_total" :min="0" /></el-form-item>
      <el-form-item label="端口到期">
        <el-date-picker v-model="form.ports_expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" />
      </el-form-item>
      <el-form-item label="重置周期(小时)"><el-input-number v-model="form.ports_reset_cycle_hours" :min="1" /></el-form-item>
      <el-divider />
      <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const rows = ref([])
const agents = ref([])
const loading = ref(false)
const selectedRows = ref([])
const selectedIds = computed(() => selectedRows.value.map((r) => r.id))
const filters = reactive({ business_agent_id: null, q: '', status: null, online_status: '' })

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: null, name: '', password: '', nickname: '', business_agent_id: null,
  status: true, statistic_time: '09:00', remark: '',
  ports_total: 0, ports_expires_at: '', ports_reset_cycle_hours: 24,
})

function agentLabel(id) {
  if (!id) return '—'
  const a = agents.value.find((x) => x.id === id)
  return a ? `${a.name}(${a.nickname || ''})` : `#${id}`
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.business_agent_id) params.business_agent_id = filters.business_agent_id
    if (filters.q) params.q = filters.q
    if (filters.status !== null && filters.status !== '') params.status = filters.status
    if (filters.online_status) params.online_status = filters.online_status
    const [{ data: m }, { data: a }] = await Promise.all([
      http.get('/merchants', { params }),
      agents.value.length ? Promise.resolve({ data: agents.value }) : http.get('/business-agents'),
    ])
    rows.value = m
    agents.value = a
  } finally { loading.value = false }
}

function reset() {
  filters.business_agent_id = null
  filters.q = ''
  filters.status = null
  filters.online_status = ''
  load()
}

function openDialog(row = null) {
  if (row) {
    Object.assign(form, {
      id: row.id, name: row.name, password: '', nickname: row.nickname || '',
      business_agent_id: row.business_agent_id, status: row.status,
      statistic_time: row.statistic_time || '09:00', remark: row.remark || '',
      ports_total: row.ports_total || 0,
      ports_expires_at: row.ports_expires_at || '',
      ports_reset_cycle_hours: row.ports_reset_cycle_hours || 24,
    })
  } else {
    Object.assign(form, {
      id: null, name: '', password: '', nickname: '', business_agent_id: null,
      status: true, statistic_time: '09:00', remark: '',
      ports_total: 0, ports_expires_at: '', ports_reset_cycle_hours: 24,
    })
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.nickname) { ElMessage.warning('请填写账号名 / 昵称'); return }
  if (!form.id && !form.password) { ElMessage.warning('请设置初始密码'); return }
  saving.value = true
  try {
    if (form.id) {
      const payload = {
        nickname: form.nickname, business_agent_id: form.business_agent_id,
        status: form.status, statistic_time: form.statistic_time, remark: form.remark,
        ports_total: form.ports_total,
        ports_expires_at: form.ports_expires_at || null,
        ports_reset_cycle_hours: form.ports_reset_cycle_hours,
      }
      if (form.password) payload.password = form.password
      await http.patch(`/merchants/${form.id}`, payload)
    } else {
      await http.post('/merchants', {
        name: form.name, password: form.password, nickname: form.nickname,
        business_agent_id: form.business_agent_id, status: form.status,
        statistic_time: form.statistic_time, remark: form.remark,
        ports_total: form.ports_total,
        ports_expires_at: form.ports_expires_at || null,
        ports_reset_cycle_hours: form.ports_reset_cycle_hours,
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } finally { saving.value = false }
}

async function toggleStatus(row, status) {
  await http.patch(`/merchants/${row.id}`, { status })
  await load()
}

async function remove(row) {
  await http.delete(`/merchants/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

async function batchToggle(status) {
  await http.post('/merchants/batch', { ids: selectedIds.value, status })
  ElMessage.success(`已${status ? '启用' : '禁用'} ${selectedIds.value.length} 个商户`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 16px; }
.filter-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
</style>
