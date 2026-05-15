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
            v-for="g in groups"
            :key="g.id"
            class="group-item"
            :class="{ active: activeGroupId === g.id }"
            @click="selectGroup(g.id)"
          >
            <div class="group-name">{{ g.name }}<span class="group-count">({{ g.count ?? 0 }})</span></div>
            <div class="group-sub">{{ g.country || '—' }} · 剩余 {{ g.remaining ?? 0 }}</div>
            <div class="group-actions">
              <el-button size="small" link @click.stop="openGroupDialog(g)">编辑</el-button>
              <el-popconfirm title="删除分组将连同号码一起删除？" @confirm="deleteGroup(g)">
                <template #reference>
                  <el-button size="small" link type="danger" @click.stop>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
          <el-empty v-if="!groups.length" description="暂无分组" :image-size="60" />
        </el-scrollbar>
      </div>

      <div class="right-pane">
        <div class="toolbar">
          <el-button type="primary" :disabled="!activeGroupId" @click="addDialog = true">+ 新增号码</el-button>
          <el-button :loading="loading" @click="loadItems">刷新</el-button>
          <span v-if="activeGroup" class="hint">当前分组：{{ activeGroup.name }} · 共 {{ activeGroup.count }} · 剩余 {{ activeGroup.remaining }}</span>
        </div>
        <el-table :data="items" v-loading="loading" stripe size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="number" label="号码" min-width="200" />
          <el-table-column prop="used" label="已使用" width="100">
            <template #default="{ row }">
              <el-tag :type="row.used ? 'info' : 'success'" size="small">{{ row.used ? '已用' : '剩余' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="fmt" label="格式" width="120" />
          <el-table-column prop="created_at" label="日期" width="200" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-popconfirm title="确定删除？" @confirm="deletePhone(row)">
                <template #reference>
                  <el-button size="small" link type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </el-card>

  <el-dialog v-model="groupDialog" :title="groupForm.id ? '编辑号码分组' : '新增号码分组'" width="420px">
    <el-form :model="groupForm" label-width="80px">
      <el-form-item label="分组名" required><el-input v-model="groupForm.name" /></el-form-item>
      <el-form-item label="国家"><el-input v-model="groupForm.country" placeholder="如 CN / US" /></el-form-item>
      <el-form-item label="日上限"><el-input-number v-model="groupForm.daily_limit" :min="0" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="groupForm.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="groupDialog = false">取消</el-button>
      <el-button type="primary" @click="saveGroup">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="addDialog" title="批量新增号码" width="520px">
    <p class="hint">每行一个号码，建议带国家区号（如 +8613800000000）。无效号码会被丢弃。</p>
    <el-input v-model="addText" type="textarea" :rows="10" placeholder="+8613800000001&#10;+8613800000002" />
    <template #footer>
      <el-button @click="addDialog = false">取消</el-button>
      <el-button type="primary" :loading="adding" @click="doAdd">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const groups = ref([])
const items = ref([])
const loading = ref(false)
const activeGroupId = ref(null)
const activeGroup = computed(() => groups.value.find((g) => g.id === activeGroupId.value) || null)

const groupDialog = ref(false)
const groupForm = reactive({ id: null, name: '', country: '', daily_limit: 0, remark: '' })

const addDialog = ref(false)
const adding = ref(false)
const addText = ref('')

async function loadGroups() {
  const { data } = await http.get('/phone-groups')
  groups.value = data
  if (!activeGroupId.value && data.length) selectGroup(data[0].id)
}

async function loadItems() {
  if (!activeGroupId.value) { items.value = []; return }
  loading.value = true
  try {
    const { data } = await http.get('/phones', { params: { group_id: activeGroupId.value } })
    items.value = data
  } finally { loading.value = false }
}

async function selectGroup(id) {
  activeGroupId.value = id
  await loadItems()
}

function openGroupDialog(g = null) {
  if (g) Object.assign(groupForm, { id: g.id, name: g.name, country: g.country || '', daily_limit: g.daily_limit || 0, remark: g.remark || '' })
  else Object.assign(groupForm, { id: null, name: '', country: '', daily_limit: 0, remark: '' })
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.name) { ElMessage.warning('请输入分组名'); return }
  if (groupForm.id) {
    await http.patch(`/phone-groups/${groupForm.id}`, {
      name: groupForm.name, country: groupForm.country, daily_limit: groupForm.daily_limit, remark: groupForm.remark,
    })
  } else {
    await http.post('/phone-groups', {
      name: groupForm.name, country: groupForm.country, daily_limit: groupForm.daily_limit, remark: groupForm.remark,
    })
  }
  groupDialog.value = false
  await loadGroups()
  ElMessage.success('已保存')
}

async function deleteGroup(g) {
  await http.delete(`/phone-groups/${g.id}`)
  if (activeGroupId.value === g.id) activeGroupId.value = null
  await loadGroups()
  await loadItems()
  ElMessage.success('已删除')
}

async function doAdd() {
  const numbers = addText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!numbers.length) { ElMessage.warning('请输入号码'); return }
  adding.value = true
  try {
    const { data } = await http.post(`/phone-groups/${activeGroupId.value}/phones`, { numbers })
    ElMessage.success(`新增 ${data.created}，重复 ${data.duplicated.length}，丢弃 ${data.rejected.length}`)
    addDialog.value = false
    addText.value = ''
    await loadGroups()
    await loadItems()
  } finally { adding.value = false }
}

async function deletePhone(row) {
  await http.delete(`/phones/${row.id}`)
  await loadGroups()
  await loadItems()
}

onMounted(loadGroups)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.two-pane { display: grid; grid-template-columns: 260px 1fr; gap: 12px; }
.left-pane { border-right: 1px solid #f0f0f0; padding-right: 12px; }
.pane-toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.group-list { max-height: calc(100vh - 280px); }
.group-item {
  padding: 8px 10px; border: 1px solid #e5e6eb; border-radius: 4px;
  margin-bottom: 6px; cursor: pointer; transition: all 0.15s;
  background: #fff;
}
.group-item:hover { border-color: var(--el-color-primary); }
.group-item.active { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary); }
.group-name { font-weight: 500; font-size: 14px; color: #303133; }
.group-count { color: var(--el-color-primary); margin-left: 4px; font-weight: 600; }
.group-sub { font-size: 12px; color: #909399; margin-top: 2px; }
.group-actions { margin-top: 4px; }
.right-pane { min-width: 0; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.hint { color: #909399; font-size: 12px; }
</style>
