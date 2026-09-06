<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface LogEntry {
  text: string
  level: string
  time: number
}

const logs = ref<LogEntry[]>([])
const autoScroll = ref(true)
const filterLevel = ref('all')
const filterText = ref('')
const logAreaRef = ref<HTMLDivElement | null>(null)
let ws: WebSocket | null = null

const LEVELS = ['all', 'debug', 'info', 'success', 'warning', 'error', 'critical']

async function loadInitial() {
  const data = await api('/api/v1/logs')
  logs.value = data.logs || []
  await nextTick()
  scrollToBottom()
}

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/live`)
  ws.onopen = () => { ws!.send(JSON.stringify({ subscribe: ['log'] })) }
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.topic === 'log') {
        logs.value.push({ text: msg.text, level: msg.level, time: msg.time })
        if (logs.value.length > 2000) logs.value = logs.value.slice(-1500)
        if (autoScroll.value) {
          nextTick(scrollToBottom)
        }
      }
    } catch {}
  }
  ws.onclose = () => { ws = null; setTimeout(connectWs, 2000) }
  ws.onerror = () => { ws?.close() }
}

function scrollToBottom() {
  const el = logAreaRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function clearLogs() {
  logs.value = []
}

function filteredLogs(): LogEntry[] {
  let result = logs.value
  if (filterLevel.value !== 'all') {
    result = result.filter(l => l.level === filterLevel.value)
  }
  if (filterText.value) {
    const q = filterText.value.toLowerCase()
    result = result.filter(l => l.text.toLowerCase().includes(q))
  }
  return result
}

function levelClass(level: string): string {
  return 'log-' + level
}

onMounted(() => { loadInitial(); connectWs() })
onUnmounted(() => { if (ws) ws.close() })
</script>

<template>
  <div class="logs-page">
    <div class="logs-header">
      <h1 class="gradient-text page-title">{{ t('logs.title') }}</h1>
      <div class="logs-controls">
        <select v-model="filterLevel" class="filter-select">
          <option v-for="lv in LEVELS" :key="lv" :value="lv">{{ lv.toUpperCase() }}</option>
        </select>
        <input type="text" v-model="filterText" :placeholder="t('logs.filter')" class="filter-input">
        <label class="auto-scroll-check">
          <input type="checkbox" v-model="autoScroll">
          <span>{{ t('logs.autoScroll') }}</span>
        </label>
        <button class="btn btn-ghost btn-sm" @click="clearLogs">{{ t('logs.clear') }}</button>
      </div>
    </div>
    <div ref="logAreaRef" class="log-area">
      <div
        v-for="(entry, i) in filteredLogs()"
        :key="i"
        class="log-line"
        :class="levelClass(entry.level)"
      >{{ entry.text }}</div>
      <div v-if="!filteredLogs().length" class="log-empty">{{ t('logs.empty') }}</div>
    </div>
  </div>
</template>

<style scoped>
.logs-page { display: flex; flex-direction: column; height: calc(100vh - 4rem); }
.logs-header { display: flex; align-items: center; gap: var(--sp-4); margin-bottom: var(--sp-3); flex-wrap: wrap; }
.logs-header h1 { margin: 0; white-space: nowrap; }
.logs-controls { display: flex; align-items: center; gap: var(--sp-2); flex: 1; flex-wrap: wrap; }
.filter-select { width: 100px; font-size: var(--text-xs); padding: var(--sp-1) var(--sp-2); }
.filter-input { flex: 1; min-width: 120px; max-width: 250px; font-size: var(--text-xs); padding: var(--sp-1) var(--sp-2); font-family: var(--font-mono); }
.auto-scroll-check { display: flex; align-items: center; gap: var(--sp-1); font-size: var(--text-xs); color: var(--text-muted); cursor: pointer; white-space: nowrap; }
.auto-scroll-check input { accent-color: var(--accent); }

.log-area {
  flex: 1;
  overflow-y: auto;
  background: rgba(10, 8, 16, 0.95);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--sp-3);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 0;
}

/* Level colors matching loguru */
.log-debug { color: #8b8b8b; }
.log-info { color: #d4d4d4; }
.log-success { color: #4ade80; }
.log-warning { color: #fbbf24; }
.log-error { color: #f87171; }
.log-critical { color: #ff4444; font-weight: bold; background: rgba(255,68,68,0.1); }

.log-empty { color: var(--text-muted); text-align: center; padding: var(--sp-8); }
</style>
