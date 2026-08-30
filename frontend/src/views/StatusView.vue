<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchStatus, readableError } from '../api/client'
import type { StatusResponse } from '../api/types'

const status = ref<StatusResponse | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await fetchStatus()
  } catch (reason) {
    error.value = readableError(reason)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page-heading">
    <p class="eyebrow">SYSTEM STATUS</p>
    <h1>运行状态</h1>
    <p>这里只检查配置和本地知识库，不会主动调用或扣费在线模型。</p>
  </section>
  <div class="status-actions"><button class="secondary-button" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新状态' }}</button></div>
  <p v-if="error" class="alert error">{{ error }}</p>
  <section v-if="status" class="status-grid">
    <article class="panel status-card">
      <span :class="['status-dot', status.llm.configured ? 'ok' : 'bad']" />
      <p class="eyebrow">CHAT MODEL</p><h2>在线聊天模型</h2>
      <dl><dt>配置</dt><dd>{{ status.llm.configured ? '完整' : '缺少配置' }}</dd><dt>模型</dt><dd>{{ status.llm.model || '未设置' }}</dd><dt>Base URL</dt><dd>{{ status.llm.base_url || '未设置' }}</dd></dl>
    </article>
    <article class="panel status-card">
      <span :class="['status-dot', status.embedding.configured ? 'ok' : 'bad']" />
      <p class="eyebrow">EMBEDDING</p><h2>在线向量模型</h2>
      <dl><dt>配置</dt><dd>{{ status.embedding.configured ? '完整' : '缺少配置' }}</dd><dt>模型</dt><dd>{{ status.embedding.model || '未设置' }}</dd><dt>Base URL</dt><dd>{{ status.embedding.base_url || '未设置' }}</dd></dl>
    </article>
    <article class="panel status-card">
      <span :class="['status-dot', status.knowledge_base.compatible ? 'ok' : 'bad']" />
      <p class="eyebrow">CHROMADB</p><h2>目的地知识库</h2>
      <dl><dt>Collection</dt><dd>{{ status.knowledge_base.collection_name }}</dd><dt>片段数</dt><dd>{{ status.knowledge_base.chunks }}</dd><dt>向量维度</dt><dd>{{ status.knowledge_base.embedding_dimension }}</dd><dt>兼容性</dt><dd>{{ status.knowledge_base.compatibility_message }}</dd></dl>
    </article>
    <article class="panel status-card">
      <span class="status-dot ok" />
      <p class="eyebrow">TASK QUEUE</p><h2>攻略任务队列</h2>
      <dl><dt>等待中</dt><dd>{{ status.queue.queued }}</dd><dt>执行中</dt><dd>{{ status.queue.running }}</dd><dt>并发策略</dt><dd>单任务串行生成</dd></dl>
    </article>
  </section>
</template>

