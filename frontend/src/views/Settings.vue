<template>
  <el-card>
    <template #header>
      <div class="card-head">
        <span>系统设置</span>
      </div>
    </template>

    <el-tabs v-model="tab">
      <el-tab-pane label="翻译服务" name="translator">
        <el-form label-position="top" :model="tr" style="max-width: 600px;">
          <el-form-item label="翻译服务商">
            <el-select v-model="tr.provider" style="width: 100%;">
              <el-option
                v-for="p in providers"
                :key="p.value"
                :label="p.label"
                :value="p.value"
              />
            </el-select>
            <div class="hint">{{ providerHint }}</div>
          </el-form-item>

          <el-form-item label="HTTP / SOCKS5 代理（可选）">
            <el-input
              v-model="tr.proxy_url"
              placeholder="例如 http://127.0.0.1:7890 或 socks5://1.2.3.4:1080"
              clearable
            />
            <div class="hint">
              如果服务器在中国境内无法直连 Google，可填代理；其它 provider 通常不需要。
            </div>
          </el-form-item>

          <el-form-item v-if="needsKey" label="API Key">
            <el-input
              v-model="tr.api_key"
              type="password"
              show-password
              :placeholder="tr.has_api_key ? `当前已配置：${tr.api_key_masked}（留空保留，输入新值覆盖，输入空白清除）` : '尚未配置'"
            />
            <div class="hint">
              <template v-if="tr.provider === 'openai'">
                到 <code>platform.openai.com</code> 申请；推荐 gpt-4o-mini 模型。
              </template>
              <template v-else-if="tr.provider === 'deepl'">
                到 <code>www.deepl.com/pro-api</code> 申请；以 <code>:fx</code> 结尾的 key
                自动走免费层端点。
              </template>
            </div>
          </el-form-item>

          <el-form-item v-if="tr.provider === 'openai'" label="模型（可选）">
            <el-input v-model="tr.model" placeholder="gpt-4o-mini（默认）" />
          </el-form-item>

          <el-form-item v-if="needsKey" label="自定义 API 端点（可选）">
            <el-input
              v-model="tr.base_url"
              :placeholder="basePlaceholder"
            />
            <div class="hint">用于 OpenAI 兼容代理或 DeepL Pro，留空走官方默认。</div>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
            <el-button :loading="testing" @click="test">立即测试</el-button>
            <span v-if="testResult" class="test-result" :class="{ ok: testResult.ok }">
              {{ testResult.message }}
            </span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const tab = ref('translator')
const tr = reactive({
  provider: 'google_free',
  proxy_url: '',
  model: '',
  base_url: '',
  api_key: '',
  api_key_masked: '',
  has_api_key: false,
})
const providers = ref([])
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

const PROVIDER_META = {
  google_free: {
    label: 'Google 免费端点（无需 key）',
    hint: '默认；服务器在境内一般需要配代理。质量好，但 Google 可能随时变更端口或限流。',
    base: '',
  },
  openai: {
    label: 'OpenAI（gpt-4o-mini 等）',
    hint: '需要 OpenAI API key；翻译质量最好，约 $0.0001/条短消息。',
    base: 'https://api.openai.com/v1',
  },
  deepl: {
    label: 'DeepL',
    hint: '需要 DeepL key；50 万字符/月免费，欧洲语种翻译质量极佳。',
    base: 'https://api-free.deepl.com/v2/translate',
  },
}

const providerHint = computed(() => PROVIDER_META[tr.provider]?.hint || '')
const needsKey = computed(() => tr.provider !== 'google_free')
const basePlaceholder = computed(() => PROVIDER_META[tr.provider]?.base || '')

async function load() {
  const { data } = await http.get('/system/translator')
  Object.assign(tr, {
    provider: data.provider || 'google_free',
    proxy_url: data.proxy_url || '',
    model: data.model || '',
    base_url: data.base_url || '',
    api_key: '',  // never echo plain key
    api_key_masked: data.api_key_masked || '',
    has_api_key: data.has_api_key || false,
  })
  providers.value = (data.supported_providers || []).map((p) => ({
    value: p,
    label: PROVIDER_META[p]?.label || p,
  }))
}

async function save() {
  saving.value = true
  testResult.value = null
  try {
    const payload = {
      provider: tr.provider,
      proxy_url: tr.proxy_url || '',
      model: tr.model || '',
      base_url: tr.base_url || '',
    }
    // Only send api_key if the user actually typed something. Empty
    // submit leaves the stored key alone (preserves their secret).
    if (tr.api_key) payload.api_key = tr.api_key
    await http.patch('/system/translator', payload)
    ElMessage.success('已保存')
    tr.api_key = ''
    await load()
  } finally {
    saving.value = false
  }
}

async function test() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await http.post('/translate', { text: 'Hello, world.' })
    testResult.value = {
      ok: true,
      message: `成功：${data.translated_text}（检测到原文：${data.source_lang || '未知'}）`,
    }
  } catch (err) {
    testResult.value = {
      ok: false,
      message: `失败：${err?.response?.data?.detail || err?.message || '未知错误'}`,
    }
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-head { display: flex; justify-content: space-between; align-items: center; }
.hint { color: #888; font-size: 12px; margin-top: 4px; line-height: 1.5; }
.hint code { background: #f5f5f5; padding: 0 4px; border-radius: 3px; }
.test-result { margin-left: 12px; font-size: 13px; color: #f56c6c; }
.test-result.ok { color: #67c23a; }
</style>
