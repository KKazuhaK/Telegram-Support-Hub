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
            <div class="group-sub">{{ KIND_LABELS[g.kind] || g.kind }}</div>
            <div class="group-actions">
              <el-button size="small" link @click.stop="openGroupDialog(g)">编辑</el-button>
              <el-popconfirm title="删除分组将连同条目一起删除？" @confirm="deleteGroup(g)">
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
          <el-input v-model="q" placeholder="搜索内容" clearable style="width: 200px" @keyup.enter="loadItems" />
          <el-button @click="loadItems">查询</el-button>
          <el-button type="primary" :disabled="!activeGroupId" @click="addDialog = true">+ 新增文本</el-button>
          <el-button :loading="loading" @click="loadItems">刷新</el-button>
        </div>
        <el-table :data="items" v-loading="loading" stripe size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="content" label="内容" />
          <el-table-column prop="created_at" label="日期" width="200" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-popconfirm title="确定删除？" @confirm="deleteItem(row)">
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

  <el-dialog v-model="groupDialog" :title="groupForm.id ? '编辑文本分组' : '新增文本分组'" width="420px">
    <el-form :model="groupForm" label-width="80px">
      <el-form-item label="分组名" required><el-input v-model="groupForm.name" /></el-form-item>
      <el-form-item label="类型">
        <el-select v-model="groupForm.kind" :disabled="!!groupForm.id">
          <el-option label="文本" value="text" />
          <el-option label="图片" value="image" />
          <el-option label="语音" value="voice" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注"><el-input v-model="groupForm.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="groupDialog = false">取消</el-button>
      <el-button type="primary" @click="saveGroup">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="addDialog" title="批量新增文本" width="520px">
    <p class="hint">每行一条；支持群发模板变量，如 <code>{name}</code> <code>[RandomEmoji=2]</code> 等。</p>
    <el-input v-model="addText" type="textarea" :rows="10" placeholder="你好 {name}，欢迎使用..." />
    <template #footer>
      <el-button @click="addDialog = false">取消</el-button>
      <el-button type="primary" :loading="adding" @click="doAdd">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const KIND_LABELS = { text: '文本', image: '图片', voice: '语音' }

const groups = ref([])
const items = ref([])
const loading = ref(false)
const activeGroupId = ref(null)
const q = ref('')

const groupDialog = ref(false)
const groupForm = reactive({ id: null, name: '', kind: 'text', remark: '' })

const addDialog = ref(false)
const adding = ref(false)
const addText = ref('')

async function loadGroups() {
  const { data } = await http.get('/material-groups')
  groups.value = data
  if (!activeGroupId.value && data.length) selectGroup(data[0].id)
}

async function loadItems() {
  if (!activeGroupId.value) { items.value = []; return }
  loading.value = true
  try {
    const params = { group_id: activeGroupId.value }
    if (q.value) params.q = q.value
    const { data } = await http.get('/materials', { params })
    items.value = data
  } finally { loading.value = false }
}

async function selectGroup(id) {
  activeGroupId.value = id
  q.value = ''
  await loadItems()
}

function openGroupDialog(g = null) {
  if (g) Object.assign(groupForm, { id: g.id, name: g.name, kind: g.kind, remark: g.remark || '' })
  else Object.assign(groupForm, { id: null, name: '', kind: 'text', remark: '' })
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.name) { ElMessage.warning('请输入分组名'); return }
  if (groupForm.id) {
    await http.patch(`/material-groups/${groupForm.id}`, { name: groupForm.name, remark: groupForm.remark })
  } else {
    await http.post('/material-groups', { name: groupForm.name, kind: groupForm.kind, remark: groupForm.remark })
  }
  groupDialog.value = false
  await loadGroups()
  ElMessage.success('已保存')
}

async function deleteGroup(g) {
  await http.delete(`/material-groups/${g.id}`)
  if (activeGroupId.value === g.id) activeGroupId.value = null
  await loadGroups()
  await loadItems()
}

async function doAdd() {
  const items = addText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!items.length) { ElMessage.warning('请输入内容'); return }
  adding.value = true
  try {
    const { data } = await http.post(`/material-groups/${activeGroupId.value}/materials`, { items })
    ElMessage.success(`新增 ${data.created} 条`)
    addDialog.value = false
    addText.value = ''
    await loadGroups()
    await loadItems()
  } finally { adding.value = false }
}

async function deleteItem(row) {
  await http.delete(`/materials/${row.id}`)
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
.hint { color: #909399; font-size: 12px; }
.hint code { background: #f0f0f0; padding: 1px 4px; border-radius: 2px; color: #d56565; }
</style>
