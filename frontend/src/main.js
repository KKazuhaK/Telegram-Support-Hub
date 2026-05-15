import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import en from 'element-plus/dist/locale/en.mjs'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import i18n, { loadLocale } from './i18n'
import { useThemeStore } from './stores/theme'
import './styles/theme.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(i18n)

const elLocale = loadLocale() === 'en-US' ? en : zhCn
app.use(ElementPlus, { locale: elLocale })

useThemeStore(pinia).init()

app.mount('#app')
