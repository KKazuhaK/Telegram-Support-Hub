<template>
  <el-row :gutter="16">
    <el-col v-for="card in cards" :key="card.title" :xs="24" :sm="12" :md="6">
      <el-card class="stat" shadow="hover">
        <div class="stat-title">{{ card.title }}</div>
        <div class="stat-value" :style="{ color: card.color }">{{ card.value ?? '-' }}</div>
        <div class="stat-sub">{{ card.sub }}</div>
      </el-card>
    </el-col>
  </el-row>
  <el-button style="margin-top: 16px" :loading="loading" @click="load">刷新</el-button>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import http from '@/api/http'

const data = ref({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data: resp } = await http.get('/statistics/dashboard')
    data.value = resp
  } finally {
    loading.value = false
  }
}

onMounted(load)

const cards = computed(() => {
  const d = data.value
  return [
    { title: 'TG 账号', value: d.accounts?.total, sub: `可用 ${d.accounts?.active ?? 0} / 异常 ${d.accounts?.error ?? 0}`, color: '#1890ff' },
    { title: '客户', value: d.customers?.total, sub: `已授权 ${d.customers?.consented ?? 0} / 已回复 ${d.customers?.replied ?? 0}`, color: '#52c41a' },
    { title: '今日发送', value: d.messages?.sent_today, sub: `队列 ${d.messages?.queued ?? 0} / 失败 ${d.messages?.failed ?? 0}`, color: '#faad14' },
    { title: '群发任务', value: d.campaigns?.total, sub: `进行中 ${d.campaigns?.running ?? 0} / 完成 ${d.campaigns?.completed ?? 0}`, color: '#722ed1' },
    { title: '代理', value: d.proxies?.total, sub: `正常 ${d.proxies?.active ?? 0} / 异常 ${d.proxies?.error ?? 0}`, color: '#13c2c2' },
    { title: '好友', value: d.friends?.total, sub: `已回复 ${d.friends?.replied ?? 0} / 退订 ${d.friends?.opted_out ?? 0}`, color: '#eb2f96' },
    { title: '消息回复', value: d.messages?.replied, sub: `发送中 ${d.messages?.sending ?? 0} / 已读未回 ${d.customers?.queued ?? 0}`, color: '#fa541c' },
    { title: '账号分组', value: d.account_groups?.total, sub: `已使用的分组数量`, color: '#2f54eb' },
  ]
})
</script>

<style scoped>
.stat { margin-bottom: 16px; }
.stat-title { color: #888; font-size: 13px; }
.stat-value { font-size: 28px; font-weight: 500; margin: 6px 0; }
.stat-sub { color: #999; font-size: 12px; }
</style>
