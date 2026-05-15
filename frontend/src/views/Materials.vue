<template>
  <el-card class="page-card">
    <el-tabs v-model="kindTab" class="kind-tabs" @tab-change="onKindChange">
      <el-tab-pane label="文本" name="text" />
      <el-tab-pane label="图片" name="image" />
      <el-tab-pane label="语音" name="voice" />
    </el-tabs>

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
            <div class="group-sub">{{ g.remark || '—' }}</div>
            <div class="group-actions">
              <el-button size="small" link @click.stop="openGroupDialog(g)">编辑</el-button>
              <el-popconfirm title="删除分组将连同资料一起删除？" @confirm="deleteGroup(g)">
                <template #reference>
                  <el-button size="small" link type="danger" @click.stop>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
          <el-empty v-if="!groups.length" :description="`暂无${KIND_LABEL[kindTab]}分组`" :image-size="60" />
        </el-scrollbar>
      </div>

      <div class="right-pane">
        <div class="toolbar">
          <template v-if="kindTab === 'text'">
            <el-input v-model="q" placeholder="搜索内容" clearable style="width: 200px" @keyup.enter="loadItems" />
            <el-button @click="loadItems">查询</el-button>
            <el-button type="primary" :disabled="!activeGroupId" @click="textDialog = true">+ 新增文本</el-button>
          </template>
          <template v-else>
            <el-upload
              :http-request="upload"
              :show-file-list="false"
              :before-upload="beforeUpload"
              :accept="kindTab === 'image' ? 'image/*' : 'audio/*'"
              :disabled="!activeGroupId"
            >
              <el-button type="primary" :disabled="!activeGroupId">⬆ 上传{{ KIND_LABEL[kindTab] }}</el-button>
            </el-upload>
          </template>
          <el-button :loading="loading" @click="loadItems">刷新</el-button>
        </div>

        <el-table :data="items" v-loading="loading" stripe size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column v-if="kindTab === 'image'" label="预览" width="100">
            <template #default="{ row }">
              <el-image
                :src="downloadUrl(row.id)"
                fit="cover"
                style="width: 60px; height: 60px; border-radius: 4px"
                :preview-src-list="[downloadUrl(row.id)]"
                preview-teleported
              />
            </template>
          </el-table-column>
          <el-table-column v-if="kindTab === 'voice'" label="试听" width="220">
            <template #default="{ row }">
              <audio :src="downloadUrl(row.id)" controls preload="none" style="height: 30px" />
            </template>
          </el-table-column>
          <el-table-column :prop="kindTab === 'text' ? 'content' : 'content'" :label="kindTab === 'text' ? '内容' : '文件名'" />
          <el-table-column prop="created_at" label="日期" width="200" />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button v-if="kindTab !== 'text'" size="small" link @click="downloadFile(row)">下载</el-button>
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

  <el-dialog v-model="groupDialog" :title="groupForm.id ? '编辑分组' : `新增${KIND_LABEL[kindTab]}分组`" width="420px">
    <el-form :model="groupForm" label-width="80px">
      <el-form-item label="分组名" required><el-input v-model="groupForm.name" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="groupForm.remark" type="textarea" :rows="2" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="groupDialog = false">取消</el-button>
      <el-button type="primary" @click="saveGroup">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="textDialog" title="批量新增文本" width="520px">
    <p class="hint">每行一条；支持模板变量 <code>{name}</code> <code>[Bold=...]</code> 等。</p>
    <el-input v-model="addText" type="textarea" :rows="10" />
    <template #footer>
      <el-button @click="textDialog = false">取消</el-button>
      <el-button type="primary" :loading="adding" @click="doAddText">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const KIND_LABEL = { text: '文本', image: '图片', voice: '语音' }

const auth = useAuthStore()
const kindTab = ref('text')
const groups = ref([])
const items = ref([])
const loading = ref(false)
const activeGroupId = ref(null)
const q = ref('')

const groupDialog = ref(false)
const groupForm = reactive({ id: null, name: '', remark: '' })

const textDialog = ref(false)
const adding = ref(false)
const addText = ref('')

function downloadUrl(id) {
  // Pass auth token via query so <img>/<audio> get authorised access.
  return `/api/materials/${id}/download?token=${encodeURIComponent(auth.token)}`
}

async function loadGroups() {
  const { data } = await http.get('/material-groups', { params: { kind: kindTab.value } })
  groups.value = data
  if (!activeGroupId.value || !data.find((g) => g.id === activeGroupId.value)) {
    activeGroupId.value = data[0]?.id || null
  }
  await loadItems()
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

function onKindChange() {
  activeGroupId.value = null
  items.value = []
  loadGroups()
}

function openGroupDialog(g = null) {
  if (g) Object.assign(groupForm, { id: g.id, name: g.name, remark: g.remark || '' })
  else Object.assign(groupForm, { id: null, name: '', remark: '' })
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.name) { ElMessage.warning('请输入分组名'); return }
  if (groupForm.id) {
    await http.patch(`/material-groups/${groupForm.id}`, { name: groupForm.name, remark: groupForm.remark })
  } else {
    await http.post('/material-groups', { name: groupForm.name, kind: kindTab.value, remark: groupForm.remark })
  }
  groupDialog.value = false
  await loadGroups()
  ElMessage.success('已保存')
}

async function deleteGroup(g) {
  await http.delete(`/material-groups/${g.id}`)
  if (activeGroupId.value === g.id) activeGroupId.value = null
  await loadGroups()
}

async function doAddText() {
  const items = addText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!items.length) { ElMessage.warning('请输入内容'); return }
  adding.value = true
  try {
    const { data } = await http.post(`/material-groups/${activeGroupId.value}/materials`, { items })
    ElMessage.success(`新增 ${data.created} 条`)
    textDialog.value = false
    addText.value = ''
    await loadGroups()
  } finally { adding.value = false }
}

function beforeUpload(file) {
  const max = (kindTab.value === 'voice' ? 50 : 20) * 1024 * 1024
  if (file.size > max) {
    ElMessage.warning(`${file.name} 超过 ${kindTab.value === 'voice' ? 50 : 20}MB 上限`)
    return false
  }
  return true
}

async function upload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await http.post(`/material-groups/${activeGroupId.value}/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  ElMessage.success(`已上传：${data.content}`)
  await loadGroups()
}

async function downloadFile(row) {
  const { data } = await http.get(`/materials/${row.id}/download`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = row.content || `material-${row.id}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

async function deleteItem(row) {
  await http.delete(`/materials/${row.id}`)
  await loadGroups()
}

onMounted(loadGroups)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.kind-tabs { margin-bottom: 8px; }
.two-pane { display: grid; grid-template-columns: 260px 1fr; gap: 12px; }
.left-pane { border-right: 1px solid #f0f0f0; padding-right: 12px; }
.pane-toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.group-list { max-height: calc(100vh - 320px); }
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
.hint { color: #909399; font-size: 12px; margin-bottom: 8px; }
.hint code { background: #f0f0f0; padding: 1px 4px; border-radius: 2px; color: #d56565; }
</style>
