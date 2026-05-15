<template>
  <el-card class="page-card">
    <div class="toolbar">
      <el-button type="primary" @click="openDialog()">新建模板</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" stripe size="small">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="body" label="内容" show-overflow-tooltip />
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="120" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
          <el-button size="small" link @click="previewRow(row)">预览</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑模板' : '新建模板'" width="960px" top="6vh">
    <div class="dialog-grid">
      <div class="dialog-form">
        <el-form :model="form" label-width="80px">
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="内容">
            <el-input
              v-model="form.body"
              type="textarea"
              :rows="14"
              placeholder="支持变量与格式化标签，详见右侧说明"
              @input="livePreview"
            />
          </el-form-item>
          <el-form-item label="预览姓名">
            <el-input v-model="previewContext.name" placeholder="张三" @input="livePreview" style="width: 220px" />
            <el-button style="margin-left: 8px" @click="livePreview">刷新预览</el-button>
          </el-form-item>
          <el-form-item label="渲染结果">
            <div class="preview-box">
              <div class="preview-text">{{ previewResult.text || '（输入内容后自动渲染）' }}</div>
              <div v-if="previewResult.entities?.length" class="preview-entities">
                <el-tag
                  v-for="(e, i) in previewResult.entities"
                  :key="i"
                  size="small" effect="plain"
                  :style="{ marginRight: '4px', marginBottom: '4px' }"
                >{{ e.type }}@{{ e.offset }}+{{ e.length }}{{ e.url ? ' → ' + e.url : '' }}{{ e.language ? ' (' + e.language + ')' : '' }}</el-tag>
              </div>
              <div v-else class="preview-empty">无格式化实体</div>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <div class="dialog-help">
        <el-card shadow="never" class="help-card">
          <div class="help-title">基本变量</div>
          <ul>
            <li><code>{name}</code> 客户姓名（缺省 → "客户"）</li>
            <li><code>{phone}</code> 手机号</li>
            <li><code>{source}</code> 数据来源</li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title">随机内容（防风控）</div>
          <ul>
            <li><code>[RandomEmoji=2]</code> 随机 2 个表情</li>
            <li><code>[RandomAlphabet=2]</code> 随机 2 个字母</li>
            <li><code>[RandomNumber=2]</code> 随机 2 个数字</li>
            <li><code>[RandomSymbol=2]</code> 随机 2 个符号</li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title">富文本格式</div>
          <ul>
            <li><code>[Bold=粗体]</code></li>
            <li><code>[Italic=斜体]</code></li>
            <li><code>[Underline=下划线]</code></li>
            <li><code>[Strike=删除线]</code></li>
            <li><code>[Code=行内代码]</code></li>
            <li><code>[Pre=Go,fmt.Println("Hello")]</code> 多行代码块（语言可选）</li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card">
          <div class="help-title">链接与提及</div>
          <ul>
            <li><code>[URL=https://example.com]</code></li>
            <li><code>[TextURL=查看官网,https://example.com]</code></li>
            <li><code>[Email=hi@example.com]</code></li>
            <li><code>[Mention=@Telegram]</code></li>
            <li><code>[Hashtag=#promo]</code></li>
            <li><code>[Phone=+71234567891]</code></li>
          </ul>
        </el-card>

        <el-card shadow="never" class="help-card tip-card">
          <div class="help-title">小贴士</div>
          <p>无效的随机变量参数（如 <code>[RandomNumber=abc]</code>）会原样保留，便于排查。</p>
          <p>Random 在预览中每次刷新都会变；实际发送时每条消息独立随机一次。</p>
        </el-card>
      </div>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

const rows = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive({ id: null, name: '', body: '' })
const previewContext = reactive({ name: '张三', phone: '+8613800000000', source: 'manual' })
const previewResult = ref({ text: '', entities: [] })

let previewTimer = null

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/message-templates')
    rows.value = data
  } finally { loading.value = false }
}

function openDialog(row = null) {
  if (row) Object.assign(form, { id: row.id, name: row.name, body: row.body })
  else Object.assign(form, { id: null, name: '', body: '' })
  previewResult.value = { text: '', entities: [] }
  dialogVisible.value = true
  // initial preview after dialog renders
  setTimeout(livePreview, 100)
}

function livePreview() {
  // Debounce so we don't hammer the backend while the user types.
  clearTimeout(previewTimer)
  previewTimer = setTimeout(async () => {
    if (!form.body) {
      previewResult.value = { text: '', entities: [] }
      return
    }
    try {
      const { data } = await http.post('/message-templates/preview', {
        body: form.body, context: { ...previewContext },
      })
      previewResult.value = data
    } catch (_) {
      // Errors already surfaced by axios interceptor.
    }
  }, 200)
}

async function save() {
  if (!form.name || !form.body) {
    ElMessage.warning('请填写名称和内容')
    return
  }
  if (form.id) {
    await http.patch(`/message-templates/${form.id}`, { name: form.name, body: form.body })
  } else {
    await http.post('/message-templates', { name: form.name, body: form.body })
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  await load()
}

async function toggleEnabled(row, enabled) {
  await http.patch(`/message-templates/${row.id}`, { enabled })
  await load()
}

async function previewRow(row) {
  const { data } = await http.post('/message-templates/preview', {
    body: row.body, context: { name: '张三', phone: '+8613800000000', source: 'manual' },
  })
  await ElMessageBox.alert(
    `<pre style="white-space:pre-wrap;margin:0;font-family:inherit">${escapeHtml(data.text)}</pre>` +
    (data.entities?.length
      ? `<div style="margin-top:8px;color:#999">实体：${data.entities.map((e) => `${e.type}@${e.offset}+${e.length}`).join('，')}</div>`
      : ''),
    `预览 - ${row.name}`,
    { dangerouslyUseHTMLString: true, confirmButtonText: '关闭' },
  )
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

onMounted(load)
</script>

<style scoped>
.page-card { min-height: calc(100vh - 180px); }
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }

.dialog-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
}
.dialog-form { min-width: 0; }
.dialog-help {
  display: flex; flex-direction: column; gap: 10px;
  max-height: 70vh; overflow-y: auto;
}
.help-card { background: #fafafa; border: 1px solid #f0f0f0; }
:deep(.help-card .el-card__body) { padding: 10px 12px; }
.help-title { font-weight: 600; color: #303133; margin-bottom: 6px; font-size: 13px; }
.help-card ul { margin: 4px 0; padding-left: 18px; font-size: 12px; color: #606266; line-height: 1.7; }
.help-card code {
  background: #f0f0f0; padding: 1px 4px; border-radius: 2px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #d56565;
}
.tip-card p { margin: 4px 0; font-size: 12px; color: #606266; line-height: 1.6; }

.preview-box {
  border: 1px solid #e5e6eb; border-radius: 4px; padding: 12px;
  background: #fafafa; min-height: 80px; width: 100%;
}
.preview-text { white-space: pre-wrap; font-size: 14px; color: #303133; }
.preview-entities { margin-top: 8px; }
.preview-empty { margin-top: 8px; color: #c0c4cc; font-size: 12px; }
</style>
