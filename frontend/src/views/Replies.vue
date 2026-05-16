<template>
  <el-card>
    <div class="toolbar">
      <el-tag :type="wsStatus === 'open' ? 'success' : 'info'">实时连接：{{ wsStatus }}</el-tag>
      <el-button :loading="loading" @click="load">刷新已回复客户</el-button>
    </div>
    <el-row :gutter="16">
      <el-col :span="14">
        <h3>已回复客户</h3>
        <el-table :data="customers" v-loading="loading" stripe size="small">
          <el-table-column prop="phone" label="手机号" width="160" />
          <el-table-column prop="name" label="姓名" width="120" />
          <el-table-column prop="last_reply_text" label="最近回复" show-overflow-tooltip />
          <el-table-column prop="last_reply_at" label="时间" width="180" />
        </el-table>
      </el-col>
      <el-col :span="10">
        <h3>实时事件</h3>
        <el-card class="event-list">
          <p v-if="!liveEvents.length" class="hint">等待回复事件…（需要 worker-listen 已启动并配置 TELEGRAM_API_ID/HASH）</p>
          <ul>
            <li v-for="(ev, idx) in liveEvents" :key="idx">
              <strong>account#{{ ev.account_id }}</strong>
              <span class="from">{{ ev.phone || ev.tg_user_id }}</span>
              <div class="text">{{ ev.text }}</div>
              <div class="ts">{{ ev.received_at }}</div>
            </li>
          </ul>
        </el-card>
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const customers = ref([])
const loading = ref(false)
const liveEvents = ref([])
const wsStatus = ref('connecting')
let ws = null
let reconnectTimer = null
let reconnectAttempt = 0
let stopped = false

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/customers', { params: { status: 'replied' } })
    customers.value = data
  } finally { loading.value = false }
}

function scheduleReconnect() {
  if (stopped) return
  // Exponential backoff capped at 30s — first retry after 1s, then 2/4/8/16/30.
  const delay = Math.min(1000 * 2 ** reconnectAttempt, 30000)
  reconnectAttempt += 1
  wsStatus.value = `reconnect in ${Math.round(delay / 1000)}s`
  reconnectTimer = setTimeout(connect, delay)
}

function connect() {
  if (stopped || !auth.token) return
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/replies?token=${encodeURIComponent(auth.token)}`
  try {
    ws = new WebSocket(url)
  } catch (_) {
    scheduleReconnect()
    return
  }
  ws.onopen = () => {
    wsStatus.value = 'open'
    reconnectAttempt = 0
  }
  ws.onclose = () => {
    wsStatus.value = 'closed'
    scheduleReconnect()
  }
  ws.onerror = () => { wsStatus.value = 'error' }
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data)
      if (data.type === 'reply') {
        liveEvents.value.unshift(data.payload)
        if (liveEvents.value.length > 50) liveEvents.value.pop()
      }
    } catch (_) {}
  }
}

onMounted(() => { load(); connect() })
onBeforeUnmount(() => {
  stopped = true
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  try { ws && ws.close() } catch (_) {}
})
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; }
.event-list { max-height: 480px; overflow: auto; }
.event-list ul { list-style: none; margin: 0; padding: 0; }
.event-list li { border-bottom: 1px dashed #eee; padding: 8px 0; }
.from { color: #888; margin-left: 8px; font-size: 12px; }
.text { margin: 4px 0; color: #333; }
.ts { color: #aaa; font-size: 12px; }
.hint { color: #999; font-size: 12px; }
</style>
