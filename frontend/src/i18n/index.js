import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

const STORAGE_KEY = 'tg.locale'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']

export function loadLocale() {
  const v = localStorage.getItem(STORAGE_KEY)
  return SUPPORTED_LOCALES.includes(v) ? v : 'zh-CN'
}

export function saveLocale(locale) {
  localStorage.setItem(STORAGE_KEY, locale)
}

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: loadLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

export default i18n
