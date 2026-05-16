<template>
  <div class="login-bg">
    <el-card class="login-card">
      <h2>TG Support Hub</h2>
      <el-tabs v-model="mode">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane :label="bootstrapTabLabel" name="bootstrap" :disabled="hasAdmin" />
      </el-tabs>
      <el-form :model="form" label-width="84px" @submit.prevent>
        <el-form-item v-if="mode === 'login'" label="登录身份">
          <el-radio-group v-model="form.actorKind" size="default">
            <el-radio-button value="support_agent">客服 / 管理员</el-radio-button>
            <el-radio-button value="business_agent">商务代理</el-radio-button>
            <el-radio-button value="merchant">商家</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item v-if="mode === 'bootstrap'" label="昵称">
          <el-input v-model="form.nickname" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">
            {{ mode === 'login' ? '登录' : '创建管理员并登录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <p class="hint">{{ hint }}</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const mode = ref('login')
const loading = ref(false)
const hasAdmin = ref(false)
const form = reactive({ username: '', password: '', nickname: '', actorKind: 'support_agent' })

const LOGIN_PATHS = {
  support_agent: '/auth/login',
  business_agent: '/auth/business-login',
  merchant: '/auth/merchant-login',
}

const bootstrapTabLabel = computed(() => (hasAdmin.value ? '初始化管理员（已禁用）' : '初始化管理员'))

const hint = computed(() => {
  if (mode.value === 'login') {
    return hasAdmin.value
      ? '请使用管理员或客服账号登录。'
      : '系统尚未初始化管理员，请先切换到右侧标签创建首个 admin。'
  }
  return hasAdmin.value
    ? '系统已存在管理员账号，无法重复初始化。请切回登录标签。'
    : '仅当系统尚无管理员时可用。'
})

async function loadHasAdmin() {
  try {
    const { data } = await http.get('/auth/has-admin')
    hasAdmin.value = !!data?.has_admin
  } catch (_) {
    // network/backend down — leave default false; user will see real error on submit
  }
}

watch(hasAdmin, (v) => {
  // Force user back to the only available tab.
  if (v && mode.value === 'bootstrap') mode.value = 'login'
  if (!v && mode.value === 'login') mode.value = 'bootstrap'
}, { immediate: false })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const url = mode.value === 'login'
      ? LOGIN_PATHS[form.actorKind]
      : '/auth/bootstrap-admin'
    const payload = mode.value === 'login'
      ? { username: form.username, password: form.password }
      : { username: form.username, password: form.password, nickname: form.nickname || undefined }
    const { data } = await http.post(url, payload)
    auth.setSession({
      token: data.access_token,
      role: data.role,
      agentId: data.agent_id,
      username: form.username,
      actorKind: data.actor_kind || 'support_agent',
      actorId: data.actor_id || data.agent_id || 0,
    })
    ElMessage.success(mode.value === 'login' ? '登录成功' : '管理员已创建')
    // The router's beforeEach + landingRouteFor() will redirect to the
    // right home for the actor (support_agent role=agent → console).
    if (route.query.next) {
      router.push(route.query.next)
    } else if (auth.actorKind === 'support_agent' && auth.role === 'agent') {
      router.push({ name: 'console' })
    } else {
      router.push({ name: 'dashboard' })
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadHasAdmin)
</script>

<style scoped>
.login-bg {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4f6cff 0%, #5cb6ff 100%);
}
.login-card {
  width: 420px;
  padding: 8px 4px;
}
h2 { margin: 0 0 16px 0; }
.hint { color: #999; font-size: 12px; margin: 8px 0 0; }
</style>
