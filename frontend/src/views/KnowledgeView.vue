<script setup lang="ts">
import { ref } from 'vue'

import { readableError, uploadKnowledge } from '../api/client'

const destination = ref('')
const topic = ref('综合')
const updatedAt = ref(new Date().toISOString().slice(0, 10))
const files = ref<File[]>([])
const busy = ref(false)
const success = ref('')
const error = ref('')

function selectFiles(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files || [])
}

async function submit() {
  success.value = ''
  error.value = ''
  if (!destination.value.trim() || !files.value.length) {
    error.value = '请填写目的地并至少选择一个文件。'
    return
  }
  const form = new FormData()
  files.value.forEach((file) => form.append('files', file))
  form.append('destination', destination.value.trim())
  form.append('topic', topic.value.trim() || '综合')
  if (updatedAt.value) form.append('updated_at', updatedAt.value)
  busy.value = true
  try {
    const result = await uploadKnowledge(form)
    success.value = result.message
  } catch (reason) {
    error.value = readableError(reason)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="page-heading">
    <p class="eyebrow">KNOWLEDGE BASE</p>
    <h1>为目的地补充可靠资料</h1>
    <p>上传 TXT、Markdown 或带文本层的 PDF。资料会通过在线 Embedding 转为向量并写入 ChromaDB。</p>
  </section>

  <form class="panel narrow-form" @submit.prevent="submit">
    <div class="section-heading"><span>02</span><div><h2>导入知识</h2><p>入库目的地名称应与生成攻略时保持一致。</p></div></div>
    <label>目的地<input v-model="destination" required placeholder="例如：成都" /></label>
    <label>资料主题<input v-model="topic" placeholder="例如：美食、交通、景点" /></label>
    <label>资料更新时间<input v-model="updatedAt" type="date" /></label>
    <label class="file-input">
      <span>选择资料文件</span>
      <input accept=".txt,.md,.pdf" multiple required type="file" @change="selectFiles" />
      <small>{{ files.length ? `已选择 ${files.length} 个文件` : '支持 TXT、MD、文本型 PDF' }}</small>
    </label>
    <p v-if="success" class="alert success">{{ success }}</p>
    <p v-if="error" class="alert error">{{ error }}</p>
    <button class="primary-button" :disabled="busy" type="submit">{{ busy ? '正在解析并向量化…' : '写入知识库' }}</button>
  </form>
</template>

