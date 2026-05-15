import { defineStore } from 'pinia'

const STORAGE_KEY = 'tg.theme'

function applyTheme(name) {
  const root = document.documentElement
  if (name === 'dark') {
    root.classList.add('dark')
    root.setAttribute('data-theme', 'dark')
  } else {
    root.classList.remove('dark')
    root.setAttribute('data-theme', 'light')
  }
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: localStorage.getItem(STORAGE_KEY) || 'light',
  }),
  actions: {
    init() {
      applyTheme(this.theme)
    },
    set(name) {
      this.theme = name === 'dark' ? 'dark' : 'light'
      localStorage.setItem(STORAGE_KEY, this.theme)
      applyTheme(this.theme)
    },
    toggle() {
      this.set(this.theme === 'dark' ? 'light' : 'dark')
    },
  },
})
