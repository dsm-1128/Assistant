<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { fetchTask, readableError, responseStatus, submitGuide } from '../api/client'
import type { Evidence, TaskResponse, TravelRequest } from '../api/types'

const STORAGE_KEY = 'travel-assistant-current-task'
const today = new Date()
const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 14)
const end = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 17)
const isoDate = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const form = reactive({
  origin: '',
  destination: '',
  start_date: isoDate(start),
  end_date: isoDate(end),
  adults: 1,
  children: 0,
  budget: 5000,
  currency: 'CNY',
  interests: '美食，人文',
  pace: '适中' as TravelRequest['pace'],
  accommodation: '交通方便、安静',
  dietary_restrictions: '无',
  must_visit: '',
  additional_requirements: '',
})

const task = ref<TaskResponse | null>(null)
const taskId = ref('')
const submitting = ref(false)
const polling = ref(false)
const message = ref('')
let pollTimer: number | undefined
let pollFailures = 0

const busy = computed(() => submitting.value || polling.value)
const statusText = computed(() => {
  if (submitting.value) return '正在提交旅行需求…'
  if (task.value?.status === 'queued') return '任务已排队，等待生成…'
  if (task.value?.status === 'running') return '正在检索资料并生成攻略…'
  if (polling.value) return '正在查询任务状态…'
  return ''
})
const evidenceMap = computed(() => {
  const map = new Map<string, Evidence>()
  task.value?.evidence.forEach((item) => map.set(item.id, item))
  return map
})

function splitValues(value: string): string[] {
  return value
    .replace(/，/g, ',')
    .split(',')
    .map((item: string) => item.trim())
    .filter(Boolean)
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearTimeout(pollTimer)
    pollTimer = undefined
  }
  polling.value = false
}

function persistTask(id: string, currency: string) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ taskId: id, currency }))
}

function restoreTask(): { taskId: string; currency?: string } | null {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (!stored) return null
  try {
    const parsed = JSON.parse(stored) as { taskId?: unknown; currency?: unknown }
    if (typeof parsed.taskId === 'string' && parsed.taskId) {
      return {
        taskId: parsed.taskId,
        currency: typeof parsed.currency === 'string' ? parsed.currency : undefined,
      }
    }
  } catch {
    // 兼容早期版本直接保存 task_id 的格式。
    return { taskId: stored }
  }
  localStorage.removeItem(STORAGE_KEY)
  return null
}

async function poll() {
  if (!taskId.value) return
  polling.value = true
  try {
    task.value = await fetchTask(taskId.value)
    pollFailures = 0
    message.value = ''
    if (task.value.status === 'queued' || task.value.status === 'running') {
      pollTimer = window.setTimeout(poll, 1800)
      return
    }
    polling.value = false
    if (task.value.status === 'failed') {
      message.value = task.value.error?.message || '攻略生成失败，请稍后重试。'
    }
  } catch (error) {
    if (responseStatus(error) === 404) {
      localStorage.removeItem(STORAGE_KEY)
      taskId.value = ''
      task.value = null
      polling.value = false
      message.value = '之前的任务已失效，可能是后端服务已重启，请重新提交。'
      return
    }
    pollFailures += 1
    message.value = readableError(error)
    if (pollFailures < 5) {
      pollTimer = window.setTimeout(poll, Math.min(1_500 * 2 ** pollFailures, 12_000))
      return
    }
    polling.value = false
    message.value = `${message.value} 已暂停自动查询，你可以重新提交或刷新页面继续。`
  }
}

async function handleSubmit() {
  if (busy.value) return
  message.value = ''
  task.value = null
  if (!form.origin.trim() || !form.destination.trim()) {
    message.value = '请填写出发地和目的地。'
    return
  }
  if (form.start_date > form.end_date) {
    message.value = '出发日期不能晚于返回日期。'
    return
  }
  if (form.adults + form.children <= 0) {
    message.value = '旅行人数必须大于 0。'
    return
  }
  stopPolling()
  submitting.value = true
  try {
    const payload: TravelRequest = {
      ...form,
      origin: form.origin.trim(),
      destination: form.destination.trim(),
      interests: splitValues(form.interests),
      must_visit: splitValues(form.must_visit),
    }
    taskId.value = await submitGuide(payload)
    persistTask(taskId.value, form.currency)
    await poll()
  } catch (error) {
    message.value = readableError(error)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  const stored = restoreTask()
  if (stored) {
    taskId.value = stored.taskId
    if (stored.currency) form.currency = stored.currency
    void poll()
  }
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="hero">
    <p class="eyebrow">PERSONAL JOURNEY PLANNER</p>
    <h1>把想去的地方，变成一份<br /><em>真正适合你的行程</em></h1>
    <p>在线模型负责规划，RAG 知识库提供目的地依据；你只需要告诉我们旅行偏好。</p>
  </section>

  <section class="workspace-grid">
    <form class="panel form-panel" @submit.prevent="handleSubmit">
      <div class="section-heading">
        <span>01</span>
        <div><h2>旅行条件</h2><p>填写得越具体，攻略越贴近你的需求。</p></div>
      </div>

      <div class="form-grid">
        <label>出发地<input v-model="form.origin" required placeholder="例如：上海" /></label>
        <label>目的地<input v-model="form.destination" required placeholder="例如：成都" /></label>
        <label>出发日期<input v-model="form.start_date" required type="date" /></label>
        <label>返回日期<input v-model="form.end_date" required type="date" /></label>
        <label>成人数<input v-model.number="form.adults" min="0" type="number" /></label>
        <label>儿童数<input v-model.number="form.children" min="0" type="number" /></label>
        <label>总预算<input v-model.number="form.budget" min="0" step="1" type="number" /></label>
        <label>币种
          <select v-model="form.currency">
            <option value="CNY">CNY（人民币）</option>
            <option value="USD">USD（美元）</option>
            <option value="EUR">EUR（欧元）</option>
            <option value="JPY">JPY（日元）</option>
            <option value="HKD">HKD（港币）</option>
          </select>
        </label>
        <label>旅行节奏
          <select v-model="form.pace"><option>轻松</option><option>适中</option><option>紧凑</option></select>
        </label>
        <label>兴趣<input v-model="form.interests" placeholder="美食，人文，摄影" /></label>
        <label class="wide">住宿偏好<input v-model="form.accommodation" /></label>
        <label class="wide">饮食禁忌<input v-model="form.dietary_restrictions" /></label>
        <label class="wide">必去地点<input v-model="form.must_visit" placeholder="多个地点用逗号分隔" /></label>
        <label class="wide">其他要求<textarea v-model="form.additional_requirements" rows="3" /></label>
      </div>

      <p v-if="message" class="alert error">{{ message }}</p>
      <button class="primary-button" :disabled="busy" type="submit">
        {{ busy ? statusText : '生成我的旅行攻略' }}
      </button>
      <small v-if="taskId" class="task-id">任务 ID：{{ taskId }}</small>
    </form>

    <aside class="panel process-panel">
      <p class="eyebrow">HOW IT WORKS</p>
      <h2>每一程，都有依据</h2>
      <ol>
        <li><b>理解偏好</b><span>整理日期、预算、人数与旅行节奏。</span></li>
        <li><b>检索资料</b><span>从你的目的地知识库中寻找相关依据。</span></li>
        <li><b>生成攻略</b><span>在线模型组合逐日行程、预算与提醒。</span></li>
      </ol>
    </aside>
  </section>

  <section v-if="task?.status === 'completed' && task.guide" class="guide-result">
    <div class="result-title">
      <p class="eyebrow">YOUR ITINERARY</p>
      <h2>{{ task.guide.title }}</h2>
      <p>{{ task.guide.overview }}</p>
      <p v-if="task.guide.insufficient_evidence" class="alert warning">
        未检索到该目的地资料，本攻略主要来自模型的通用规划能力。
      </p>
    </div>

    <div class="days">
      <article v-for="day in task.guide.days" :key="day.day" class="day-card">
        <div class="day-number">DAY<br /><strong>{{ day.day }}</strong></div>
        <div class="day-content">
          <p class="day-date">{{ day.date }}</p>
          <h3>{{ day.theme }}</h3>
          <div v-for="activity in day.activities" :key="`${day.day}-${activity.period}`" class="activity">
            <span>{{ activity.period }}</span>
            <div>
              <h4>{{ activity.activity }}</h4>
              <p>{{ activity.location || '地点待定' }} · {{ activity.duration || '按实际安排' }} · {{ activity.transport || '步行或公共交通' }}</p>
              <p>估算 {{ activity.estimated_cost.toLocaleString() }} {{ form.currency }}
                <template v-for="citation in activity.citations" :key="citation">
                  <a v-if="evidenceMap.has(citation)" :href="`#evidence-${citation}`">[{{ citation }}]</a>
                </template>
              </p>
            </div>
          </div>
          <p v-if="day.meals.length" class="muted"><b>餐饮：</b>{{ day.meals.join('；') }}</p>
          <p v-if="day.notes.length" class="muted"><b>提醒：</b>{{ day.notes.join('；') }}</p>
        </div>
      </article>
    </div>

    <div class="summary-grid">
      <article class="panel"><h3>交通建议</h3><ul><li v-for="item in task.guide.transportation_advice" :key="item">{{ item }}</li></ul></article>
      <article class="panel"><h3>餐饮与住宿</h3><ul><li v-for="item in task.guide.food_and_stay_advice" :key="item">{{ item }}</li></ul></article>
      <article class="panel budget"><h3>预算估算</h3><p v-for="item in task.guide.budget_items" :key="item.category"><span>{{ item.category }}</span><b>{{ item.amount.toLocaleString() }} {{ form.currency }}</b></p><strong>合计 {{ task.guide.budget_total.toLocaleString() }} {{ form.currency }}</strong></article>
      <article class="panel"><h3>行前准备</h3><ul><li v-for="item in task.guide.preparation" :key="item">{{ item }}</li></ul></article>
      <article class="panel warning-card"><h3>风险与避坑</h3><ul><li v-for="item in task.guide.warnings" :key="item">{{ item }}</li></ul></article>
    </div>

    <div v-if="task.evidence.length" class="evidence-list">
      <h3>资料来源</h3>
      <article v-for="item in task.evidence" :id="`evidence-${item.id}`" :key="item.id">
        <b>[{{ item.id }}] {{ item.source }}</b>
        <span>{{ item.topic }} · 更新：{{ item.updated_at }}</span>
        <p>{{ item.content }}</p>
      </article>
    </div>
  </section>
</template>
