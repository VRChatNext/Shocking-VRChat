<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, apiPost, apiDelete, apiPut } from '@/api'
import QrCode from '@/components/QrCode.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// --- State ---
const connected = ref(false)
const deviceCount = ref(0)
const strength = ref({ A: 0, B: 0 })
const limit = ref({ A: 100, B: 100 })
const oscStatus = ref('')
const lastTrigger = ref('-')
const oscEvents = ref<any[]>([])
const canvasARef = ref<HTMLCanvasElement | null>(null)
const canvasBRef = ref<HTMLCanvasElement | null>(null)
const qrContent = ref('')
const logs = ref<{text: string; level: string}[]>([])

// V4 QR
const qrContentV4 = ref('')
const v4Enabled = ref(true)
const qrMode = ref<'v3' | 'v4'>('v4')  // Default to V4
// Profiles
const profiles = ref<string[]>([])
const profileName = ref('')
const profileMsg = ref('')

let intervals: number[] = []
let dashWs: WebSocket | null = null

// Wave animation state (same approach as WaveTest: pending queue + rAF metering)
const DISPLAY_SLOTS = 200
const SLOT_MS = 25
let pendingA: {s: number; f: number}[] = []
let pendingB: {s: number; f: number}[] = []
let bufferA: {s: number; f: number}[] = []
let bufferB: {s: number; f: number}[] = []
let debtA = 0
let debtB = 0
let animId = 0
let lastFrame = 0

// --- WebSocket-based real-time data ---
function connectLiveWs() {
  if (dashWs) return
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${proto}//${location.host}/ws/live`
  dashWs = new WebSocket(wsUrl)
  dashWs.onopen = () => {
    dashWs!.send(JSON.stringify({ subscribe: ['wave_A', 'wave_B', 'osc', 'status'] }))
  }
  dashWs.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.topic === 'wave_A' && msg.samples) {
        pendingA.push(...msg.samples)
      } else if (msg.topic === 'wave_B' && msg.samples) {
        pendingB.push(...msg.samples)
      } else if (msg.topic === 'osc' && msg.event) {
        oscEvents.value.unshift(msg.event)
        if (oscEvents.value.length > 20) oscEvents.value = oscEvents.value.slice(0, 20)
        lastTrigger.value = t('dashboard.justNow')
      } else if (msg.topic === 'status') {
        const devices = msg.devices || []
        deviceCount.value = devices.length
        connected.value = devices.length > 0
        if (devices.length > 0) {
          strength.value = devices[0].strength || { A: 0, B: 0 }
          limit.value = {
            A: Math.min(devices[0].strength_max?.A || 0, devices[0].strength_limit?.A || 100),
            B: Math.min(devices[0].strength_max?.B || 0, devices[0].strength_limit?.B || 100),
          }
        }
      }
    } catch {}
  }
  dashWs.onclose = () => {
    dashWs = null
    // Reconnect after 2s
    setTimeout(connectLiveWs, 2000)
  }
  dashWs.onerror = () => { dashWs?.close() }
}

function disconnectLiveWs() {
  if (dashWs) { dashWs.close(); dashWs = null }
}

// --- Polling (fallback for initial load and status heartbeat) ---
async function pollStatus() {
  try {
    const data = await api('/api/v1/status')
    const devices = data.devices || []
    deviceCount.value = devices.length
    connected.value = devices.length > 0
    if (devices.length > 0) {
      const attr = devices[0].attr
      strength.value = attr.strength
      limit.value = {
        A: Math.min(attr.strength_max?.A || 0, attr.strength_limit?.A || 100),
        B: Math.min(attr.strength_max?.B || 0, attr.strength_limit?.B || 100),
      }
    }
    oscStatus.value = data.osc_listening || ''
    if (data.last_osc_time) {
      const ago = Math.round(Date.now() / 1000 - data.last_osc_time)
      lastTrigger.value = ago < 2 ? t('dashboard.justNow') : `${ago}s`
    } else { lastTrigger.value = t('dashboard.noData') }
  } catch { connected.value = false }
}

function drawWaveCanvas(canvas: HTMLCanvasElement | null, buffer: {s: number; f: number}[]) {
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  if (W < 1 || H < 1) return
  canvas.width = W * dpr
  canvas.height = H * dpr
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  ctx.fillStyle = 'rgba(10, 8, 16, 0.95)'
  ctx.fillRect(0, 0, W, H)

  ctx.strokeStyle = 'rgba(139,92,246,0.08)'
  ctx.lineWidth = 1
  for (let pct = 25; pct <= 75; pct += 25) {
    const py = H - (pct / 100) * H
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke()
  }

  if (!buffer.length) return

  const slotW = W / DISPLAY_SLOTS
  const startIdx = Math.max(0, buffer.length - DISPLAY_SLOTS)
  const visibleCount = buffer.length - startIdx
  const xBase = (DISPLAY_SLOTS - visibleCount) * slotW

  for (let i = 0; i < visibleCount; i++) {
    const sample = buffer[startIdx + i]
    if (sample.s <= 0) continue

    const dutyCycle = Math.max(0.05, 1 - (sample.f - 10) / (240 - 10))
    const barW = slotW * dutyCycle
    const barH = (sample.s / 100) * H
    const x = xBase + i * slotW + (slotW - barW) / 2

    const freqT = 1 - (sample.f - 10) / 230
    const r = Math.round(139 + (1 - freqT) * 100)
    const g = Math.round(92 * freqT)
    const b = Math.round(246 * freqT + 100 * (1 - freqT))
    ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
    ctx.fillRect(x, H - barH, Math.max(barW, 0.5), barH)
  }
}

function meterAndDraw(now: number) {
  if (lastFrame > 0) {
    const dt = now - lastFrame
    const samplesOwed = dt / SLOT_MS
    // Channel A
    debtA += samplesOwed
    if (pendingA.length > 0) {
      const n = Math.min(Math.floor(debtA), pendingA.length)
      if (n > 0) { bufferA.push(...pendingA.splice(0, n)); debtA -= n }
    } else {
      // No incoming data: push empty slots to scroll out old waveform
      const n = Math.floor(debtA)
      if (n > 0) {
        for (let i = 0; i < n; i++) bufferA.push({ s: 0, f: 0 })
        debtA -= n
      }
    }
    if (bufferA.length > DISPLAY_SLOTS * 2) bufferA = bufferA.slice(-DISPLAY_SLOTS * 2)
    // Channel B
    debtB += samplesOwed
    if (pendingB.length > 0) {
      const n = Math.min(Math.floor(debtB), pendingB.length)
      if (n > 0) { bufferB.push(...pendingB.splice(0, n)); debtB -= n }
    } else {
      const n = Math.floor(debtB)
      if (n > 0) {
        for (let i = 0; i < n; i++) bufferB.push({ s: 0, f: 0 })
        debtB -= n
      }
    }
    if (bufferB.length > DISPLAY_SLOTS * 2) bufferB = bufferB.slice(-DISPLAY_SLOTS * 2)
  } else {
    // First frame: dump all
    if (pendingA.length) { bufferA.push(...pendingA.splice(0)); debtA = 0 }
    if (pendingB.length) { bufferB.push(...pendingB.splice(0)); debtB = 0 }
    if (bufferA.length > DISPLAY_SLOTS * 2) bufferA = bufferA.slice(-DISPLAY_SLOTS * 2)
    if (bufferB.length > DISPLAY_SLOTS * 2) bufferB = bufferB.slice(-DISPLAY_SLOTS * 2)
  }
  lastFrame = now
  drawWaveCanvas(canvasARef.value, bufferA)
  drawWaveCanvas(canvasBRef.value, bufferB)
  animId = requestAnimationFrame(meterAndDraw)
}

function startWaveAnim() {
  if (!animId) animId = requestAnimationFrame(meterAndDraw)
}
function stopWaveAnim() {
  if (animId) { cancelAnimationFrame(animId); animId = 0 }
  lastFrame = 0
}

// Profiles
function addLog(msg: string, level = '') {
  logs.value.unshift({ text: `[${new Date().toLocaleTimeString()}] ${msg}`, level })
  if (logs.value.length > 80) logs.value.pop()
}

async function loadProfiles() {
  const data = await api('/api/v1/profiles')
  profiles.value = data.profiles || []
}

async function saveProfile() {
  if (!profileName.value.trim()) return
  const data = await apiPut(`/api/v1/profiles/${encodeURIComponent(profileName.value)}`)
  if (data.success) { profileMsg.value = t('dashboard.profileSaved'); profileName.value = ''; loadProfiles() }
  else profileMsg.value = data.message || t('dashboard.profileFailed')
  setTimeout(() => profileMsg.value = '', 3000)
}

async function loadProfile(name: string) {
  const data = await apiPost(`/api/v1/profiles/${encodeURIComponent(name)}`)
  if (data.success) addLog(t('dashboard.profileSwitched', { name }))
}

async function deleteProfile(name: string) {
  if (!confirm(t('dashboard.profileDeleteConfirm', { name }))) return
  await apiDelete(`/api/v1/profiles/${encodeURIComponent(name)}`)
  loadProfiles()
}

// QR
async function loadQr() {
  try {
    const data = await api('/api/v1/qr_payload')
    qrContent.value = data.content || ''
  } catch {}
  try {
    const data = await api('/api/v1/qr_payload_v4')
    qrContentV4.value = data.content || ''
    v4Enabled.value = data.enabled !== false
  } catch {}
}

// Helpers
function barPct(ch: 'A' | 'B') {
  return Math.min(strength.value[ch] / 200 * 100, 100)
}
function shortPath(addr: string) { return addr.replace('/avatar/parameters/', '') }
function timeStr(ts: number) { return new Date(ts * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) }

onMounted(() => {
  pollStatus(); loadProfiles(); loadQr()
  connectLiveWs()
  startWaveAnim()
  intervals.push(window.setInterval(pollStatus, 5000))
})
onUnmounted(() => {
  intervals.forEach(clearInterval)
  disconnectLiveWs()
  stopWaveAnim()
})
</script>

<template>
  <div class="dashboard">
    <!-- Stats row -->
    <div class="stats-row">
      <div class="stat-card" :class="connected ? 'stat-on' : ''">
        <span class="stat-dot" :class="connected ? 'on' : ''"></span>
        <div>
          <div class="stat-val">{{ connected ? t('dashboard.deviceCount', { count: deviceCount }) : t('dashboard.disconnected') }}</div>
          <div class="stat-sub">{{ t('dashboard.deviceStatus') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">📡</span>
        <div><div class="stat-val">{{ oscStatus || '-' }}</div><div class="stat-sub">OSC</div></div>
      </div>
      <div class="stat-card">
        <span class="stat-icon">⏱</span>
        <div><div class="stat-val">{{ lastTrigger }}</div><div class="stat-sub">{{ t('dashboard.lastTrigger') }}</div></div>
      </div>
    </div>

    <div class="grid-2">
      <!-- Left column -->
      <div class="col">
        <!-- Channels -->
        <section class="card">
          <h2>{{ t('dashboard.deviceStatus') }}</h2>
          <div class="ch-row" v-for="ch in (['A', 'B'] as const)" :key="ch">
            <div class="ch-head"><span class="ch-name">{{ ch }}</span><strong>{{ strength[ch] }} / 200</strong></div>
            <div class="bar-track"><div class="bar-fill" :class="'bar-' + ch.toLowerCase()" :style="{width: barPct(ch) + '%'}"></div></div>
          </div>
        </section>

        <!-- OSC Feed -->
        <section class="card">
          <h2>{{ t('dashboard.oscEvents') }}</h2>
          <div class="osc-feed">
            <div class="osc-row" v-for="(e, i) in oscEvents" :key="i">
              <span class="badge" :class="'b-' + e.channel.toLowerCase()">{{ e.channel }}</span>
              <span class="osc-mode">{{ e.mode }}</span>
              <span class="osc-path">{{ shortPath(e.address) }}</span>
              <span class="osc-val">{{ e.value }}</span>
              <span class="osc-time">{{ timeStr(e.time) }}</span>
            </div>
            <div v-if="!oscEvents.length" class="empty">{{ t('dashboard.noEvents') }}</div>
          </div>
        </section>

        <!-- Wave visualization -->
        <section class="card">
          <h2>{{ t('dashboard.waveform') }}</h2>
          <div class="wave-dual">
            <div class="wave-channel">
              <div class="wave-ch-label">A</div>
              <canvas ref="canvasARef" class="wave-canvas"></canvas>
            </div>
            <div class="wave-channel">
              <div class="wave-ch-label">B</div>
              <canvas ref="canvasBRef" class="wave-canvas"></canvas>
            </div>
          </div>
        </section>

        <!-- Logs -->
        <section class="card">
          <h2>{{ t('dashboard.logs') }}</h2>
          <div class="log-area">
            <div v-for="(l, i) in logs" :key="i" class="log-line" :class="l.level">{{ l.text }}</div>
            <div v-if="!logs.length" class="empty">{{ t('dashboard.noLogs') }}</div>
          </div>
        </section>
      </div>

      <!-- Right column -->
      <div class="col">
        <!-- QR -->
        <section class="card">
          <h2>{{ t('dashboard.qrTitle') }}</h2>
          <div class="qr-tabs">
            <button class="qr-tab" :class="{ active: qrMode === 'v4' }" @click="qrMode = 'v4'" v-if="v4Enabled">V4</button>
            <button class="qr-tab" :class="{ active: qrMode === 'v3' }" @click="qrMode = 'v3'">V3</button>
          </div>
          <div class="qr-badge" :class="qrMode">{{ qrMode === 'v4' ? t('dashboard.qrV4Badge') : t('dashboard.qrV3Badge') }}</div>
          <QrCode :content="qrMode === 'v4' ? qrContentV4 : qrContent" :size="240" />
          <div class="qr-text">{{ qrMode === 'v4' ? qrContentV4 : qrContent }}</div>
          <div class="qr-hint" v-if="qrMode === 'v4'">{{ t('dashboard.qrV4Hint') }}</div>
          <div class="qr-hint" v-else>{{ t('dashboard.qrV3Hint') }}</div>
        </section>

        <!-- Profiles -->
        <section class="card">
          <h2>{{ t('dashboard.profiles') }}</h2>
          <div class="profile-list">
            <div class="profile-item" v-for="p in profiles" :key="p">
              <span class="profile-name">{{ p }}</span>
              <button class="prof-btn load" @click="loadProfile(p)">▶</button>
              <button class="prof-btn del" @click="deleteProfile(p)">✕</button>
            </div>
            <div v-if="!profiles.length" class="empty">{{ t('dashboard.noProfiles') }}</div>
          </div>
          <div class="profile-add">
            <input type="text" v-model="profileName" :placeholder="t('dashboard.newProfileName')" @keyup.enter="saveProfile">
            <button class="btn btn-primary" @click="saveProfile">{{ t('dashboard.saveCurrent') }}</button>
          </div>
          <div v-if="profileMsg" class="profile-msg">{{ profileMsg }}</div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: var(--sp-5); }

.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-4); }
.stat-card {
  display: flex; align-items: center; gap: var(--sp-4);
  padding: var(--sp-5);
  background: var(--bg-card);
  backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  transition: all var(--transition);
}
.stat-card:hover { border-color: var(--border-hover); box-shadow: var(--glow-sm); }
.stat-card.stat-on { border-color: rgba(52, 211, 153, 0.3); box-shadow: 0 0 20px rgba(52,211,153,0.08); }
.stat-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-muted); transition: all var(--transition); }
.stat-dot.on { background: var(--success); box-shadow: 0 0 12px rgba(52,211,153,0.6); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 12px rgba(52,211,153,0.6); } 50% { box-shadow: 0 0 20px rgba(52,211,153,0.3); } }
.stat-icon { font-size: 1.5em; }
.stat-val { font-size: var(--text-base); font-weight: 600; }
.stat-sub { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }

.grid-2 { display: grid; grid-template-columns: 1.3fr 0.7fr; gap: var(--sp-5); }
.col { display: flex; flex-direction: column; gap: var(--sp-4); }

/* Channels */
.ch-row { margin-bottom: var(--sp-2); }
.ch-row:last-child { margin-bottom: 0; }
.ch-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--sp-1); font-size: var(--text-sm); }
.ch-name { font-weight: 700; font-size: var(--text-base); background: var(--gradient-text); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.bar-track { height: 5px; background: rgba(139,92,246,0.1); border-radius: var(--radius-full); overflow: hidden; }
.bar-fill { height: 100%; border-radius: var(--radius-full); transition: width 200ms linear; }
.bar-a { background: linear-gradient(90deg, #34d399, #6ee7b7); box-shadow: 0 0 8px rgba(52,211,153,0.3); }
.bar-b { background: linear-gradient(90deg, #60a5fa, #93c5fd); box-shadow: 0 0 8px rgba(96,165,250,0.3); }

/* OSC feed */
.osc-feed { max-height: 220px; overflow-y: auto; }
.osc-row {
  display: flex; gap: var(--sp-2); align-items: center;
  padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm);
  font-size: var(--text-xs); font-family: var(--font-mono);
  transition: background var(--transition);
}
.osc-row:hover { background: rgba(139,92,246,0.05); }
.badge { padding: 2px 7px; border-radius: var(--radius-sm); font-weight: 700; font-size: 10px; }
.b-a { background: rgba(52,211,153,0.12); color: var(--success); }
.b-b { background: rgba(96,165,250,0.12); color: var(--info); }
.osc-mode { color: var(--warning); min-width: 48px; }
.osc-path { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.osc-val { color: var(--accent-2); min-width: 40px; text-align: right; font-variant-numeric: tabular-nums; }
.osc-time { color: var(--text-muted); min-width: 52px; text-align: right; }

/* QR */
.qr-tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-3); }
.qr-tab { padding: var(--sp-2) var(--sp-4); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-xs); font-weight: 600; transition: all var(--transition); }
.qr-tab.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.1); }
.qr-tab:hover { border-color: var(--border-hover); color: var(--text); }
.qr-badge { display: inline-block; padding: 2px 10px; border-radius: var(--radius-full); font-size: 10px; font-weight: 700; margin-bottom: var(--sp-3); }
.qr-badge.v4 { background: rgba(52,211,153,0.12); color: var(--success); }
.qr-badge.v3 { background: rgba(96,165,250,0.12); color: var(--info); }
.qr-text { margin-top: var(--sp-3); font-size: var(--text-xs); font-family: var(--font); color: var(--text-muted); word-break: break-all; padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }
.qr-hint { margin-top: var(--sp-2); font-size: 11px; color: var(--text-muted); font-style: italic; }

/* Wave */
.wave-dual { display: flex; flex-direction: column; gap: var(--sp-2); }
.wave-channel { display: flex; align-items: stretch; gap: var(--sp-2); }
.wave-ch-label { display: flex; align-items: center; justify-content: center; width: 24px; font-size: var(--text-xs); font-weight: 600; color: var(--accent); opacity: 0.7; }
.wave-canvas { width: 100%; height: 80px; border-radius: var(--radius-md); display: block; }

/* Controls */
.form-field { margin-bottom: var(--sp-4); }
.form-field label { display: block; font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--sp-2); font-weight: 500; }
.form-field select { width: 100%; }
.btn-group { display: flex; gap: var(--sp-2); flex-wrap: wrap; }

/* Wave preview */
.preview-info { font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: var(--sp-3); padding: var(--sp-2) var(--sp-3); background: rgba(139,92,246,0.05); border-radius: var(--radius-sm); }

/* Profiles */
.profile-list { max-height: 140px; overflow-y: auto; margin-bottom: var(--sp-3); }
.profile-item { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-sm); transition: background var(--transition); }
.profile-item:hover { background: rgba(139,92,246,0.05); }
.profile-name { flex: 1; font-size: var(--text-sm); }
.prof-btn { border: none; border-radius: var(--radius-full); padding: 3px 10px; cursor: pointer; font-size: var(--text-xs); color: #fff; transition: all var(--transition); }
.prof-btn:hover { transform: scale(1.05); }
.prof-btn.load { background: var(--success); }
.prof-btn.del { background: rgba(248,113,113,0.7); }
.profile-add { display: flex; gap: var(--sp-2); }
.profile-add input { flex: 1; }
.profile-msg { font-size: var(--text-xs); color: var(--success); margin-top: var(--sp-2); }

/* Logs */
.log-area { max-height: 140px; overflow-y: auto; font-family: var(--font-mono); font-size: var(--text-xs); padding: var(--sp-2); background: rgba(0,0,0,0.2); border-radius: var(--radius-md); }
.log-line { padding: 2px var(--sp-2); color: var(--text-muted); }
.log-line.warn { color: var(--warning); }
.log-line.error { color: var(--danger); }

.empty { padding: var(--sp-6); text-align: center; color: var(--text-muted); font-size: var(--text-sm); }

@media (max-width: 768px) {
  .stats-row { grid-template-columns: 1fr; }
  .grid-2 { grid-template-columns: 1fr; }
}
</style>
