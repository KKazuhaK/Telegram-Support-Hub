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
            <!-- Original (whatever was actually sent / received). For
                 outbound auto-translated messages this is the foreign-
                 language text the customer sees. -->
            <div class="text">{{ m.body_snapshot }}</div>
            <!-- Translation (cached on the row, populated by either the
                 auto-translate-on-receive flow or the send-side
                 auto-translate that stored the original Chinese). Hidden
                 when m._collapsed is true. -->
            <div v-if="m.translation && !m._collapsed" class="translated">
              {{ m.translation }}
            </div>
            <div class="bubble-meta">
              <span>{{ formatTs(m.created_at) }}</span>
              <span v-if="m.direction === 'outbound'" class="status">
                {{ statusLabel(m.status) }}
              </span>
              <!-- Toggle collapse if we have a translation, else offer
                   to fetch one (only meaningful on inbound). -->
              <el-button
                v-if="m.translation"
                size="small"
                link
                @click="m._collapsed = !m._collapsed"
              >{{ m._collapsed ? '展开译文' : '收起译文' }}</el-button>
              <el-button
                v-else-if="m.direction === 'inbound'"
                size="small"
                link
                :loading="m._translating"
                @click="translateMessage(m)"
              >翻译</el-button>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <footer class="chat-input">
        <!-- Tenants (merchant / business_agent) don't see TG inventory
             so they can't choose an account to send from. Show a
             read-only hint instead of a broken dropdown. -->
        <el-alert
          v-if="!auth.isSupportAgent && !eligibleAccounts.length"
          type="info"
          show-icon
          :closable="false"
          title="您的账号没有发送权限。如需主动联系客户，请联系平台客服。"
          style="margin-bottom: 8px;"
        />
        <div class="input-toolbar">
          <span class="hint">发送账号：</span>
          <el-select v-model="sendAccountId" size="small" filterable placeholder="选择 TG 账号" style="width: 200px;">
            <el-option
              v-for="a in eligibleAccounts"
              :key="a.id"
              :label="`${a.phone || a.tg_user_id}${a.status ? ' (' + a.status + ')' : ''}`"
              :value="a.id"
            />
          </el-select>
          <el-divider direction="vertical" />
          <el-button size="small" link @click="openQuickReplyDrawer">
            <el-icon><ChatLineSquare /></el-icon>&nbsp;话术
          </el-button>
          <el-button size="small" link @click="openTranslatePanel">
            <el-icon><ChatRound /></el-icon>&nbsp;翻译面板
          </el-button>
          <el-checkbox v-model="autoTranslateInbound" size="small">
            自动翻译来信
          </el-checkbox>
          <el-checkbox v-model="autoTranslateOnSend" size="small" class="auto-tr-toggle">
            发送前翻译成客户语言
            <span v-if="customerLang" class="lang-hint">（{{ customerLang }}）</span>
          </el-checkbox>
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

    <!-- Quick-reply (话术) drawer — pick a saved script to insert into the input. -->
    <el-drawer v-model="quickReplyDrawer" title="话术" size="420px">
      <el-tabs v-model="quickReplyTab">
        <el-tab-pane label="个人话术" name="personal" />
        <el-tab-pane label="公共话术" name="public" />
      </el-tabs>
      <div v-if="quickReplyTab === 'personal'" class="qr-add">
        <el-input
          v-model="qrDraft"
          type="textarea"
          :rows="2"
          placeholder="输入新话术内容…"
        />
        <el-button type="primary" :disabled="!qrDraft.trim()" @click="createQuickReply">
          添加
        </el-button>
      </div>
      <el-divider v-if="quickReplyTab === 'personal'" style="margin: 8px 0;" />
      <div class="qr-list">
        <div v-for="qr in scopedQuickReplies" :key="qr.id" class="qr-item">
          <div class="qr-text" @click="insertQuickReply(qr)">{{ qr.text }}</div>
          <el-button
            v-if="canEditQuickReply(qr)"
            size="small" link type="danger"
            @click.stop="deleteQuickReply(qr)"
          >删除</el-button>
        </div>
        <div v-if="!scopedQuickReplies.length" class="empty">
          暂无{{ quickReplyTab === 'personal' ? '个人' : '公共' }}话术
        </div>
      </div>
    </el-drawer>

    <!-- Standalone translate panel — paste arbitrary text, translate to Chinese. -->
    <el-drawer v-model="translatePanel" title="翻译面板" size="420px">
      <el-form label-position="top">
        <el-form-item label="原文">
          <el-input v-model="trSrc" type="textarea" :rows="5" placeholder="粘贴或输入要翻译的文本" />
        </el-form-item>
        <el-form-item label="译文">
          <el-input v-model="trDst" type="textarea" :rows="5" readonly />
        </el-form-item>
        <el-button type="primary" :loading="trBusy" :disabled="!trSrc.trim()" @click="runStandaloneTranslate">
          翻译成中文
        </el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, ChatLineSquare, ChatRound } from '@element-plus/icons-vue'
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

// Quick-reply drawer state.
const quickReplyDrawer = ref(false)
const quickReplyTab = ref('personal')
const quickReplies = ref([])
const qrDraft = ref('')

// Standalone translate panel state.
const translatePanel = ref(false)
const trSrc = ref('')
const trDst = ref('')
const trBusy = ref(false)

// Outbound auto-translate (send draft → translate → store both).
const autoTranslateOnSend = ref(false)
// Inbound auto-translate (when opening a chat, translate every inbound
// message and cache; default ON because the screenshot UX is bilingual).
const autoTranslateInbound = ref(true)

const filteredCustomers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return customers.value
  return customers.value.filter((c) => {
    return (c.name || '').toLowerCase().includes(q)
      || (c.phone || '').includes(q)
  })
})

const eligibleAccounts = computed(() => {
  // Tenant actors don't get account.status (hidden by sanitizer); rely
  // on the existence of the row in the scoped list as 'usable'.
  return accounts.value.filter((a) =>
    a.status === undefined || (a.enabled && a.status === 'active'),
  )
})

const scopedQuickReplies = computed(() => {
  if (quickReplyTab.value === 'personal') {
    return quickReplies.value.filter((q) => !q.is_public)
  }
  return quickReplies.value.filter((q) => q.is_public)
})

const customerLang = computed(() => selected.value?.last_source_lang || '')

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
    // Pre-init UI-only fields so Vue's Proxy tracks them once we set
    // them later (_translating, _collapsed). translation comes from the
    // server (cached or null).
    history.value = (data || []).map((m) => ({
      ...m, _translating: false, _collapsed: false,
    }))
    await nextTick()
    scrollToBottom()
    // Fire off lazy auto-translate for any inbound row that hasn't
    // been cached yet. Sequential by design — don't hammer the
    // provider with a long history opening.
    autoTranslatePendingInbound()
  } finally {
    historyLoading.value = false
  }
}

function scrollToBottom() {
  const el = historyScroll.value?.wrapRef
  if (el) el.scrollTop = el.scrollHeight
}

async function loadQuickReplies() {
  try {
    const { data } = await http.get('/quick-replies')
    quickReplies.value = data || []
  } catch (_) {}
}

function openQuickReplyDrawer() {
  quickReplyDrawer.value = true
  if (!quickReplies.value.length) loadQuickReplies()
}

async function createQuickReply() {
  const text = qrDraft.value.trim()
  if (!text) return
  try {
    await http.post('/quick-replies', { text })
    qrDraft.value = ''
    await loadQuickReplies()
  } catch (_) {}
}

async function deleteQuickReply(qr) {
  try {
    await ElMessageBox.confirm(`确定删除话术：${qr.text.slice(0, 30)}？`, '删除话术')
  } catch (_) { return }
  await http.delete(`/quick-replies/${qr.id}`)
  await loadQuickReplies()
}

function canEditQuickReply(qr) {
  // Personal scripts editable by their owner; public only by admin
  // (server enforces; frontend just hides the button optimistically).
  if (qr.is_public) return auth.isAdmin
  return qr.actor_kind === auth.actorKind && qr.actor_id === auth.actorId
}

function insertQuickReply(qr) {
  draft.value = draft.value ? `${draft.value}\n${qr.text}` : qr.text
  quickReplyDrawer.value = false
}

function openTranslatePanel() {
  translatePanel.value = true
  // Pre-fill with the last inbound message if there is one — common
  // path is "I want to read what they said".
  if (!trSrc.value && history.value.length) {
    const lastIn = [...history.value].reverse().find((m) => m.direction === 'inbound')
    if (lastIn) trSrc.value = lastIn.body_snapshot
  }
}

async function runStandaloneTranslate() {
  if (!trSrc.value.trim()) return
  trBusy.value = true
  try {
    const { data } = await http.post('/translate', {
      text: trSrc.value,
      customer_id: selected.value?.id,
    })
    trDst.value = data.translated_text
  } catch (_) {} finally {
    trBusy.value = false
  }
}

async function translateMessage(m) {
  if (m._translating || m.translation) return
  m._translating = true
  try {
    // Per-message cache endpoint: server translates + persists to the
    // row's translation column so subsequent loads hit the DB cache.
    const { data } = await http.post(
      `/customers/${selected.value.id}/messages/${m.id}/translate`,
    )
    m.translation = data.translation
    m._collapsed = false
  } catch (_) { /* http.js toasted already */
  } finally {
    m._translating = false
  }
}

// Walk the loaded history and lazily translate any inbound message
// that doesn't already have a cached translation. Fire-and-forget per
// message; failures stay silent (operator can manually retry via the
// "翻译" button if needed).
async function autoTranslatePendingInbound() {
  if (!selected.value || !autoTranslateInbound.value) return
  const pending = history.value.filter(
    (m) => m.direction === 'inbound' && !m.translation,
  )
  // Limit concurrency to avoid blasting the provider on a long history.
  for (const m of pending) {
    await translateMessage(m)
  }
}

async function send() {
  const text = draft.value.trim()
  if (!text || !selected.value || !sendAccountId.value) return
  sending.value = true
  try {
    // Server handles translation when auto_translate=true: it sends the
    // foreign-language version to TG and stores the original Chinese
    // on the row so the bubble can render both.
    const { data } = await http.post(
      `/customers/${selected.value.id}/messages`,
      {
        account_id: sendAccountId.value,
        text,
        auto_translate: autoTranslateOnSend.value,
      },
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
.bubble .text {
  white-space: pre-wrap;
  word-break: break-word;
  color: inherit;
}
.bubble .translated {
  margin-top: 4px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.55);
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-row.out .bubble .translated { color: rgba(0, 0, 0, 0.5); }
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
.input-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.input-toolbar .hint { font-size: 12px; color: #888; }
.auto-tr-toggle { margin-left: auto; font-size: 12px; }
.auto-tr-toggle .lang-hint { color: #888; }

.qr-add { display: flex; gap: 8px; align-items: flex-end; padding: 4px 0; }
.qr-add .el-textarea { flex: 1; }
.qr-list { max-height: calc(100vh - 280px); overflow-y: auto; }
.qr-item {
  padding: 8px;
  border-bottom: 1px solid var(--tg-border, #eee);
  display: flex; gap: 8px; align-items: flex-start;
}
.qr-item .qr-text {
  flex: 1; cursor: pointer; white-space: pre-wrap; word-break: break-word;
  font-size: 13px; line-height: 1.5;
}
.qr-item:hover { background: rgba(0, 0, 0, 0.02); }
.qr-list .empty { padding: 20px; color: #aaa; font-size: 12px; text-align: center; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row .el-textarea { flex: 1; }
</style>
