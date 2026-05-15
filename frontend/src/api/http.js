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
      // FastAPI validation error: detail is a list of {loc, msg, type}
      message = detail.map((d) => d?.msg).filter(Boolean).join('；') || `请求失败 (${status})`
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
