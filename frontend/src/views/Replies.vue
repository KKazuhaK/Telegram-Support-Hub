<template>
  <div class="chat-shell">
    <!-- Left: customer list, ranked by most recent activity. -->
    <aside class="chat-sidebar">
      <div class="sidebar-head">
        <el-input
          v-model="search"
          placeholder="搜索客户姓名 / 手机号"
          size="small"
          clearable
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button size="small" :icon="Refresh" link @click="loadCustomers">
          刷新
        </el-button>
      </div>
      <el-scrollbar class="sidebar-list">
        <div
          v-for="c in filteredCustomers"
          :key="c.id"
          class="customer-row"
          :class="{ active: selected?.id === c.id, unread: !!c._unread }"
          @click="selectCustomer(c)"
        >
          <el-avatar :size="40">{{ initial(c) }}</el-avatar>
          <div class="meta">
            <div class="row1">
              <span class="name">{{ c.name || c.phone }}</span>
              <span class="ts">{{ shortTs(c.last_reply_at || c.last_message_at) }}</span>
            </div>
            <div class="preview">{{ c.last_reply_text || c.phone }}</div>
          </div>
          <el-badge v-if="c._unread" is-dot class="dot" />
        </div>
        <div v-if="!filteredCustomers.length" class="empty">
          暂无客户。新客户回复或群发后会出现在这里。
        </div>
      </el-scrollbar>
      <div class="sidebar-foot">
        <el-tag :type="wsStatus === 'open' ? 'success' : 'info'" size="small">
          实时连接：{{ wsStatus }}
        </el-tag>
      </div>
    </aside>

    <!-- Right: chat pane. -->
    <section class="chat-main" v-if="selected">
      <header class="chat-head">
        <div class="title">{{ selected.name || selected.phone }}</div>
        <div class="sub">{{ selected.phone }}</div>
      </header>

      <el-scrollbar ref="historyScroll" class="chat-history">
        <div v-if="historyLoading" class="loading">加载会话中…</div>
        <div v-else-if="!history.length" class="empty">
          还没有消息。在下方输入一句话开始对话。
        </div>
        <div
          v-for="m in history"
          :key="m.id"
          class="bubble-row"
          :class="m.direction === 'outbound' ? 'out' : 'in'"
        >
          <div class="bubble">
            <div class="text">{{ m.body_snapshot }}</div>
            <div class="bubble-meta">
              <span>{{ formatTs(m.created_at) }}</span>
              <span v-if="m.direction === 'outbound'" class="status">
                {{ statusLabel(m.status) }}
              </span>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <footer class="chat-input">
        <div class="input-toolbar">
          <span class="hint">发送账号：</span>
          <el-select v-model="sendAccountId" size="small" filterable placeholder="选择 TG 账号">
            <el-option
              v-for="a in eligibleAccounts"
              :key="a.id"
              :label="`${a.phone || a.tg_user_id} (${a.status})`"
              :value="a.id"
            />
          </el-select>
        </div>
        <div class="input-row">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="3"
            placeholder="输入消息内容，Ctrl+Enter 发送"
            @keydown.enter.ctrl.exact="send"
          />
          <el-button
            type="primary"
            :loading="sending"
            :disabled="!draft.trim() || !sendAccountId"
            @click="send"
          >
            发送
          </el-button>
        </div>
      </footer>
    </section>

    <section v-else class="chat-main empty-state">
      <el-empty description="选择一位客户开始对话" />
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const customers = ref([])
const accounts = ref([])
const selected = ref(null)
const history = ref([])
const historyLoading = ref(false)
const sending = ref(false)
const draft = ref('')
const sendAccountId = ref(null)
const search = ref('')
const wsStatus = ref('connecting')
const historyScroll = ref(null)

let ws = null
let reconnectTimer = null
let reconnectAttempt = 0
let stopped = false

const filteredCustomers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return customers.value
  return customers.value.filter((c) => {
    return (c.name || '').toLowerCase().includes(q)
      || (c.phone || '').includes(q)
  })
})

const eligibleAccounts = computed(() => {
  return accounts.value.filter((a) => a.enabled && a.status === 'active')
})

function initial(c) {
  return (c.name || c.phone || '?').slice(0, 1).toUpperCase()
}

function shortTs(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatTs(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

function statusLabel(status) {
  return { sending: '发送中', sent: '已发送', failed: '发送失败',
           failed_permanent: '永久失败', read: '已读', replied: '已回复' }[status] || status
}

async function loadCustomers() {
  try {
    const { data } = await http.get('/customers', { params: { limit: 200 } })
    // Sort by most recent activity desc so chat-like UI surfaces recent
    // conversations first.
    customers.value = (data || []).slice().sort((a, b) => {
      const ta = (a.last_reply_at || a.last_message_at || a.created_at || '')
      const tb = (b.last_reply_at || b.last_message_at || b.created_at || '')
      return tb.localeCompare(ta)
    })
  } catch (_) { /* http.js already toasted */ }
}

async function loadAccounts() {
  try {
    const { data } = await http.get('/accounts', { params: { limit: 200 } })
    accounts.value = data || []
    if (!sendAccountId.value && eligibleAccounts.value.length) {
      sendAccountId.value = eligibleAccounts.value[0].id
    }
  } catch (_) {}
}

async function selectCustomer(c) {
  selected.value = c
  c._unread = false
  await loadHistory(c.id)
  // Prefer the account that was last used in this conversation.
  const lastOut = [...history.value].reverse().find((m) => m.direction === 'outbound' && m.account_id)
  if (lastOut) sendAccountId.value = lastOut.account_id
  else if (c.assigned_account_id) sendAccountId.value = c.assigned_account_id
}

async function loadHistory(customerId) {
  historyLoading.value = true
  try {
    const { data } = await http.get(`/customers/${customerId}/messages`)
    history.value = data || []
    await nextTick()
    scrollToBottom()
  } finally {
    historyLoading.value = false
  }
}

function scrollToBottom() {
  const el = historyScroll.value?.wrapRef
  if (el) el.scrollTop = el.scrollHeight
}

async function send() {
  const text = draft.value.trim()
  if (!text || !selected.value || !sendAccountId.value) return
  sending.value = true
  try {
    const { data } = await http.post(
      `/customers/${selected.value.id}/messages`,
      { account_id: sendAccountId.value, text },
    )
    history.value.push(data)
    draft.value = ''
    await nextTick()
    scrollToBottom()
    // Bump the customer to the top of the sidebar.
    selected.value.last_message_at = data.created_at
    customers.value = customers.value.slice().sort((a, b) => {
      const ta = (a.last_reply_at || a.last_message_at || '')
      const tb = (b.last_reply_at || b.last_message_at || '')
      return tb.localeCompare(ta)
    })
  } catch (_) { /* error toast already shown by http.js */
  } finally {
    sending.value = false
  }
}

// --- realtime ---
function scheduleReconnect() {
  if (stopped) return
  const delay = Math.min(1000 * 2 ** reconnectAttempt, 30000)
  reconnectAttempt += 1
  wsStatus.value = `reconnect in ${Math.round(delay / 1000)}s`
  reconnectTimer = setTimeout(connect, delay)
}

function connect() {
  if (stopped || !auth.token) return
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/replies?token=${encodeURIComponent(auth.token)}`
  try { ws = new WebSocket(url) } catch (_) { scheduleReconnect(); return }
  ws.onopen = () => { wsStatus.value = 'open'; reconnectAttempt = 0 }
  ws.onclose = () => { wsStatus.value = 'closed'; scheduleReconnect() }
  ws.onerror = () => { wsStatus.value = 'error' }
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data)
      if (data.type === 'reply') handleIncoming(data.payload)
    } catch (_) {}
  }
}

function handleIncoming(payload) {
  // Match the affected customer by phone; bump it to the top + mark unread.
  const phone = payload.phone
  if (!phone) return
  const c = customers.value.find((c) => c.phone === phone)
  if (c) {
    c.last_reply_at = payload.received_at || new Date().toISOString()
    c.last_reply_text = payload.text
    if (selected.value?.id !== c.id) c._unread = true
    customers.value = customers.value.slice().sort((a, b) => {
      const ta = (a.last_reply_at || a.last_message_at || '')
      const tb = (b.last_reply_at || b.last_message_at || '')
      return tb.localeCompare(ta)
    })
  }
  // If the user is currently looking at this conversation, refresh history.
  if (selected.value && (selected.value.phone === phone)) {
    loadHistory(selected.value.id)
  }
}

function tearDownWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  try {
    if (ws) {
      ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null
      ws.close()
    }
  } catch (_) {}
  ws = null
}

watch(() => auth.token, (newToken, oldToken) => {
  if (newToken === oldToken) return
  tearDownWs(); reconnectAttempt = 0; stopped = !newToken
  if (newToken) connect()
})

onMounted(() => {
  loadCustomers()
  loadAccounts()
  connect()
})
onBeforeUnmount(() => { stopped = true; tearDownWs() })
</script>

<style scoped>
.chat-shell {
  display: flex;
  height: calc(100vh - 160px);
  background: var(--tg-surface, #fff);
  border: 1px solid var(--tg-border, #e5e6eb);
  border-radius: 4px;
  overflow: hidden;
}
.chat-sidebar {
  width: 300px;
  border-right: 1px solid var(--tg-border, #e5e6eb);
  display: flex;
  flex-direction: column;
  background: var(--tg-bg, #f5f7fa);
}
.sidebar-head {
  display: flex;
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid var(--tg-border, #e5e6eb);
  align-items: center;
}
.sidebar-list { flex: 1; }
.customer-row {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--tg-border, #f0f0f0);
  position: relative;
  align-items: center;
}
.customer-row:hover { background: rgba(0, 0, 0, 0.03); }
.customer-row.active { background: var(--el-color-primary-light-9); }
.customer-row .meta { flex: 1; min-width: 0; }
.customer-row .row1 {
  display: flex; justify-content: space-between; gap: 6px;
  font-size: 13px; font-weight: 500;
}
.customer-row .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.customer-row .ts { color: #999; font-size: 11px; flex: 0 0 auto; }
.customer-row .preview {
  font-size: 12px; color: #888;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.customer-row .dot { position: absolute; right: 10px; top: 12px; }
.empty { padding: 20px; color: #aaa; font-size: 12px; text-align: center; }
.sidebar-foot { padding: 8px 10px; border-top: 1px solid var(--tg-border, #e5e6eb); }

.chat-main {
  flex: 1;
  display: flex; flex-direction: column;
  min-width: 0;
}
.chat-main.empty-state { align-items: center; justify-content: center; }
.chat-head {
  padding: 12px 16px;
  border-bottom: 1px solid var(--tg-border, #e5e6eb);
  background: var(--tg-surface, #fff);
}
.chat-head .title { font-size: 16px; font-weight: 600; }
.chat-head .sub { font-size: 12px; color: #888; }

.chat-history {
  flex: 1;
  background: #f0f2f5;
  padding: 16px;
}
.bubble-row { display: flex; margin-bottom: 12px; }
.bubble-row.out { justify-content: flex-end; }
.bubble-row.in { justify-content: flex-start; }
.bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.5;
  background: #fff;
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.06);
}
.bubble-row.out .bubble { background: #9eea6a; color: #1a1a1a; }
.bubble .text { white-space: pre-wrap; word-break: break-word; }
.bubble-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #888;
  display: flex; gap: 8px; justify-content: flex-end;
}
.loading { color: #888; padding: 30px; text-align: center; }

.chat-input {
  padding: 8px 12px 12px;
  border-top: 1px solid var(--tg-border, #e5e6eb);
  background: var(--tg-surface, #fff);
}
.input-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.input-toolbar .hint { font-size: 12px; color: #888; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row .el-textarea { flex: 1; }
</style>
