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
    }
  },
  getters: {
    isAuthenticated: (state) => !!state.token,
    isAdmin: (state) => state.role === 'admin' || state.role === 'supervisor',
  },
  actions: {
    setSession({ token, role, agentId, username }) {
      this.token = token
      this.role = role
      this.agentId = agentId
      this.username = username || this.username
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        token, role, agentId, username: this.username,
      }))
    },
    logout() {
      this.token = ''
      this.role = ''
      this.agentId = null
      this.username = ''
      localStorage.removeItem(STORAGE_KEY)
    },
  },
})
