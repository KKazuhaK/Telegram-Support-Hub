import { defineStore } from 'pinia'

const HOME_TAB = { name: 'dashboard', title: '仪表盘', closable: false }

export const useTabsStore = defineStore('tabs', {
  state: () => ({
    tabs: [HOME_TAB],
    active: 'dashboard',
  }),
  actions: {
    openTab({ name, title }) {
      if (!name) return
      this.active = name
      if (!this.tabs.some((t) => t.name === name)) {
        this.tabs.push({ name, title: title || name, closable: name !== 'dashboard' })
      }
    },
    closeTab(name) {
      const idx = this.tabs.findIndex((t) => t.name === name)
      if (idx < 0) return null
      const tab = this.tabs[idx]
      if (!tab.closable) return null
      this.tabs.splice(idx, 1)
      if (this.active === name) {
        const fallback = this.tabs[idx] || this.tabs[idx - 1] || HOME_TAB
        this.active = fallback.name
        return fallback.name
      }
      return null
    },
    closeOthers(name) {
      this.tabs = this.tabs.filter((t) => !t.closable || t.name === name)
      this.active = name
    },
    closeAll() {
      this.tabs = [HOME_TAB]
      this.active = HOME_TAB.name
    },
    setActive(name) {
      if (this.tabs.some((t) => t.name === name)) this.active = name
    },
  },
})
