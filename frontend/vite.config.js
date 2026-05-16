import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const apiTarget = process.env.VITE_API_PROXY || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/ws': { target: apiTarget, changeOrigin: true, ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          // Element Plus is the heaviest single dep; isolating it lets
          // the browser cache it across deploys that only touch app code.
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          // ECharts + vue-echarts is ~500kB on its own and only used by
          // the stats page — a separate chunk lets users who never open
          // /task-stats skip downloading it on first paint.
          echarts: ['echarts', 'vue-echarts'],
          // Vue / Pinia / Router / i18n change rarely; group as 'vendor'.
          vendor: ['vue', 'vue-router', 'pinia', 'vue-i18n', 'axios'],
        },
      },
    },
  },
})
