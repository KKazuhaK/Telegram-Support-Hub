<template>
  <el-card>
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新建客服</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="role" label="角色" width="100" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column prop="last_login_at" label="最近登录" width="200" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
          <el-button size="small" link @click="openPermDialog(row)">权限</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑客服' : '新建客服'" width="480px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="用户名" v-if="!form.id"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="昵称"><el-input v-model="form.nickname" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role">
          <el-option label="admin" value="admin" />
          <el-option label="supervisor" value="supervisor" />
          <el-option label="agent" value="agent" />
        </el-select>
      </el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" :placeholder="form.id ? '留空则不修改' : ''" /></el-form-item>
      <el-form-item label="状态" v-if="form.id"><el-select v-model="form.status"><el-option label="启用" value="enabled" /><el-option label="禁用" value="disabled" /></el-select></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="permDialog" :title="`配置 ${permTarget?.username} 的账号分组权限`" width="640px">
    <el-table :data="permRows" border size="small">
      <el-table-column label="账号分组" width="180">
        <template #default="{ row }">
          <el-select v-model="row.account_group_id" placeholder="选择分组">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="发送" width="80"><template #default="{ row }"><el-switch v-model="row.can_send_message" /></template></el-table-column>
      <el-table-column label="群发" width="80"><template #default="{ row }"><el-switch v-model="row.can_broadcast" /></template></el-table-column>
      <el-table-column label="导出" width="80"><template #default="{ row }"><el-switch v-model="row.can_export_data" /></template></el-table-column>
      <el-table-column label="看好友" width="80"><template #default="{ row }"><el-switch v-model="row.can_view_friends" /></template></el-table-column>
      <el-table-column label="看聊天" width="80"><template #default="{ row }"><el-switch v-model="row.can_view_chats" /></template></el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" @click="permRows.splice($index, 1)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button style="margin-top: 12px" @click="addPermRow">添加分组</el-button>
    <template #footer>
      <el-button @click="permDialog = false">取消</el-button>
      <el-button type="primary" @click="savePermissions">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const rows = ref([])
const groups = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive({ id: null, username: '', nickname: '', role: 'agent', password: '', status: 'enabled' })

const permDialog = ref(false)
const permTarget = ref(null)
const permRows = ref([])

async function load() {
  loading.value = true
  try {
    const [{ data: r }, { data: g }] = await Promise.all([
      http.get('/support-agents'),
      http.get('/account-groups'),
    ])
    rows.value = r
    groups.value = g
  } finally { loading.value = false }
}

function openDialog(row = null) {
  if (row) Object.assign(form, { id: row.id, username: row.username, nickname: row.nickname, role: row.role, password: '', status: row.status })
  else Object.assign(form, { id: null, username: '', nickname: '', role: 'agent', password: '', status: 'enabled' })
  dialogVisible.value = true
}

async function save() {
  if (form.id) {
    const payload = { nickname: form.nickname, role: form.role, status: form.status }
    if (form.password) payload.password = form.password
    await http.patch(`/support-agents/${form.id}`, payload)
  } else {
    await http.post('/support-agents', { username: form.username, nickname: form.nickname, role: form.role, password: form.password })
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  await load()
}

async function openPermDialog(row) {
  permTarget.value = row
  const { data } = await http.get(`/support-agents/${row.id}/account-group-permissions`)
  permRows.value = data.map((d) => ({ ...d }))
  permDialog.value = true
}

function addPermRow() {
  permRows.value.push({
    account_group_id: groups.value[0]?.id ?? null,
    can_view_friends: true, can_view_chats: true, can_send_message: true,
    can_broadcast: false, can_edit_profile: false, can_delete_friend: false,
    can_clear_chat: false, can_export_data: false, chat_scope: { all: true },
  })
}

async function savePermissions() {
  const payload = permRows.value.filter((r) => r.account_group_id)
  await http.put(`/support-agents/${permTarget.value.id}/account-group-permissions`, payload)
  ElMessage.success('权限已更新')
  permDialog.value = false
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
</style>
