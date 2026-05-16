import { defineStore } from 'pinia'

const STORAGE_KEY = 'tg-support-hub-auth'

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (_) {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const stored = loadFromStorage() || {}
    return {
      token: stored.token || '',
      role: stored.role || '',
      agentId: stored.agentId || null,
      username: stored.username || '',
      actorKind: stored.actorKind || 'support_agent',
      actorId: stored.actorId || 0,
    }
  },
  getters: {
    isAuthenticated: (state) => !!state.token,
    isAdmin: (state) => state.actorKind === 'support_agent'
      && (state.role === 'admin' || state.role === 'supervisor'),
    isSupportAgent: (state) => state.actorKind === 'support_agent',
    isBusinessAgent: (state) => state.actorKind === 'business_agent',
    isMerchant: (state) => state.actorKind === 'merchant',
  },
  actions: {
    setSession({ token, role, agentId, username, actorKind, actorId }) {
      this.token = token
      this.role = role
      this.agentId = agentId
      this.username = username || this.username
      this.actorKind = actorKind || 'support_agent'
      this.actorId = actorId || 0
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        token, role, agentId, username: this.username,
        actorKind: this.actorKind, actorId: this.actorId,
      }))
    },
    logout() {
      this.token = ''
      this.role = ''
      this.agentId = null
      this.username = ''
      this.actorKind = 'support_agent'
      this.actorId = 0
      localStorage.removeItem(STORAGE_KEY)
    },
  },
})
