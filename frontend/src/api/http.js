import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

const STATUS_FALLBACKS = {
  400: '请求参数有误',
  403: '权限不足',
  404: '资源不存在',
  409: '资源冲突',
  422: '提交内容未通过校验',
  500: '服务器内部错误',
  502: '后端服务不可达',
  503: '服务暂不可用',
  504: '后端响应超时',
}

const FIELD_LABELS = {
  username: '用户名',
  password: '密码',
  nickname: '昵称',
  name: '名称',
  phone: '手机号',
  ports_total: '端口数',
  business_agent_id: '商务代理',
  account_group_ids: '账号分组',
  agent_ids: '客服列表',
  ids: '所选项',
  email: '邮箱',
}

function _translatePydanticError(err) {
  // FastAPI's 422 entries look like {loc: ["body", "password"], msg: "String should have at least 8 characters", type: "string_too_short", ctx: {min_length: 8}}.
  // Convert common patterns to Chinese with the field label inlined.
  const loc = Array.isArray(err?.loc) ? err.loc : []
  const fieldKey = loc.length ? loc[loc.length - 1] : null
  const fieldLabel = FIELD_LABELS[fieldKey] || fieldKey || '该字段'
  const t = err?.type || ''
  const ctx = err?.ctx || {}
  if (t === 'string_too_short') return `${fieldLabel}至少 ${ctx.min_length} 位`
  if (t === 'string_too_long')  return `${fieldLabel}不能超过 ${ctx.max_length} 位`
  if (t === 'missing')           return `${fieldLabel}是必填项`
  if (t === 'too_short')         return `${fieldLabel}至少 ${ctx.min_length} 项`
  if (t === 'too_long')          return `${fieldLabel}最多 ${ctx.max_length} 项`
  if (t === 'value_error')       return err?.msg || `${fieldLabel}格式不正确`
  if (t === 'int_parsing' || t === 'float_parsing') return `${fieldLabel}必须是数字`
  return err?.msg ? `${fieldLabel}：${err.msg}` : `${fieldLabel}校验未通过`
}

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    const onLoginPage = router.currentRoute.value.name === 'login'

    if (status === 401) {
      const auth = useAuthStore()
      const wasAuthenticated = auth.isAuthenticated
      auth.logout()
      if (!onLoginPage) {
        ElMessage.warning(wasAuthenticated ? '登录已过期，请重新登录' : '请先登录')
        router.push({ name: 'login' })
        return Promise.reject(error)
      }
    }

    let message
    if (typeof detail === 'string' && detail) {
      message = detail
    } else if (Array.isArray(detail) && detail.length) {
      // FastAPI validation error: detail is a list of {loc, msg, type}.
      // Translate each entry to Chinese with the field label inlined.
      message = detail.map(_translatePydanticError).join('；') || `请求失败 (${status})`
    } else if (status) {
      message = STATUS_FALLBACKS[status] || `请求失败 (${status})`
    } else {
      message = '网络错误，请检查网络或稍后重试'
    }
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default http
