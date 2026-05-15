<template>
  <el-card>
    <div class="toolbar">
      <el-select v-model="status" placeholder="全部状态" clearable style="width: 160px" @change="load">
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button type="primary" @click="importDialog = true">导入客户</el-button>
      <el-button @click="assignDialog = true">分配</el-button>
      <el-button @click="exportCsv">导出 CSV</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="phone" label="手机号" />
      <el-table-column prop="name" label="姓名" />
      <el-table-column prop="source" label="来源" />
      <el-table-column prop="consent" label="授权" width="80">
        <template #default="{ row }"><el-tag :type="row.consent ? 'success' : 'danger'">{{ row.consent ? '是' : '否' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column prop="assigned_account_id" label="分配账号" width="100" />
      <el-table-column prop="last_reply_text" label="最近回复" show-overflow-tooltip />
    </el-table>
  </el-card>

  <el-dialog v-model="importDialog" title="导入客户" width="520px">
    <el-form :model="importForm" label-width="80px">
      <el-form-item label="数据">
        <el-input v-model="importForm.text" type="textarea" :rows="8" placeholder="phone,name,tags,consent&#10;+8613800000000,张三,VIP|售后,yes" />
      </el-form-item>
      <el-form-item label="来源"><el-input v-model="importForm.source" /></el-form-item>
      <el-form-item label="默认授权"><el-switch v-model="importForm.assume_consent" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="importDialog = false">取消</el-button>
      <el-button type="primary" :loading="importing" @click="doImport">导入</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="assignDialog" title="分配客户" width="480px">
    <el-form :model="assignForm" label-width="100px">
      <el-form-item label="账号分组">
        <el-select v-model="assignForm.account_group_ids" multiple>
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="单账号上限"><el-input-number v-model="assignForm.max_per_account" :min="0" /></el-form-item>
      <el-form-item label="只分配未分配"><el-switch v-model="assignForm.only_unassigned" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="assignDialog = false">取消</el-button>
      <el-button type="primary" :loading="assigning" @click="doAssign">分配</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const statuses = ['new', 'assigned', 'queued', 'sending', 'sent', 'replied', 'failed']
const status = ref('')
const rows = ref([])
const groups = ref([])
const loading = ref(false)

const importDialog = ref(false)
const importing = ref(false)
const importForm = reactive({ text: '', source: '', assume_consent: false })

const assignDialog = ref(false)
const assigning = ref(false)
const assignForm = reactive({ account_group_ids: [], max_per_account: 50, only_unassigned: true })

async function load() {
  loading.value = true
  try {
    const params = status.value ? { status: status.value } : {}
    const { data } = await http.get('/customers', { params })
    rows.value = data
    if (groups.value.length === 0) {
      const { data: g } = await http.get('/account-groups')
      groups.value = g
    }
  } finally { loading.value = false }
}

async function doImport() {
  importing.value = true
  try {
    const { data } = await http.post('/customers/import', importForm)
    ElMessage.success(`新增 ${data.created.length}，重复 ${data.duplicated.length}，丢弃 ${data.rejected.length}`)
    importDialog.value = false
    await load()
  } finally { importing.value = false }
}

async function doAssign() {
  assigning.value = true
  try {
    const { data } = await http.post('/customers/assign', assignForm)
    ElMessage.success(`已分配 ${data.assigned}，跳过 ${data.skipped}`)
    assignDialog.value = false
    await load()
  } finally { assigning.value = false }
}

async function exportCsv() {
  const params = status.value ? { status: status.value } : {}
  const { data } = await http.get('/export/customers.csv', { params, responseType: 'blob' })
  const url = window.URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'customers.csv'
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
