<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, apiPost, apiDelete } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const recActive = ref(false)
const recCount = ref(0)
const recElapsed = ref(0)
const playActive = ref(false)
const playProgress = ref(0)
const playTotal = ref(0)
const playFilename = ref('')
const speed = ref(1.0)
const loop = ref(false)
const recordings = ref<any[]>([])
const msg = ref('')
const oscEvents = ref<any[]>([])
const canvasARef = ref<HTMLCanvasElement | null>(null)
const canvasBRef = ref<HTMLCanvasElement | null>(null)

let timers: number[] = []

async function startRec() {
  const data = await apiPost('/api/v1/recorder/start')
  if (!data.success) msg.value = data.message
}

async function stopRec() {
  const data = await apiPost('/api/v1/recorder/stop')
  if (data.success) { msg.value = `${t('common.saved')} ${data.filename}`; loadFiles() }
}

async function startPlay(filename: string) {
  await apiPost('/api/v1/playback/start', { filename, speed: speed.value, loop: loop.value })
}

async function stopPlay() {
  await apiPost('/api/v1/playback/stop')
}

async function deleteFile(name: string) {
  if (!confirm(t('recorder.deleteConfirm', { name }))) return
  await apiDelete(`/api/v1/recordings/${encodeURIComponent(name)}`)
  loadFiles()
}

async function loadFiles() {
  const data = await api('/api/v1/recordings')
  recordings.value = data.recordings || []
}

async function pollStatus() {
  try {
    const r = await api('/api/v1/recorder/status')
    recActive.value = r.recording
    recCount.value = r.message_count
    recElapsed.value = r.elapsed_ms

    const p = await api('/api/v1/playback/status')
    playActive.value = p.active
    playProgress.value = p.progress
    playTotal.value = p.total
    playFilename.value = p.filename || ''
  } catch {}
}

async function pollOsc() {
  try {
    const data = await api('/api/v1/osc_activity')
    oscEvents.value = (data.events || []).slice(0, 20)
  } catch {}
}

async function pollWave() {
  try {
    const data = await api('/api/v1/wave_history')
    drawWave(canvasARef.value, data.A || [], '#8b5cf6')
    drawWave(canvasBRef.value, data.B || [], '#3b82f6')
  } catch {}
}

function drawWave(canvas: HTMLCanvasElement | null, samples: number[], color: string) {
  if (!canvas) return
  const ratio = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  canvas.width = W * ratio
  canvas.height = H * ratio
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, W, H)
  const bars = samples.slice(-60)
  if (!bars.length) return
  const gap = 2
  const barW = Math.max(2, (W - gap * (bars.length - 1)) / bars.length)
  bars.forEach((sample, i) => {
    const v = Math.max(0, Math.min(100, sample))
    const barH = (v / 100) * (H - 4)
    const x = i * (barW + gap)
    const y = H - barH
    ctx.globalAlpha = 0.4 + v / 180
    ctx.fillStyle = color
    ctx.fillRect(x, y, barW, barH)
  })
  ctx.globalAlpha = 1
}

function shortPath(addr: string) { return addr.replace('/avatar/parameters/', '') }
function timeStr(ts: number) { return new Date(ts * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) }

onMounted(() => {
  loadFiles(); pollStatus(); pollOsc(); pollWave()
  timers.push(window.setInterval(pollStatus, 1000))
  timers.push(window.setInterval(pollOsc, 500))
  timers.push(window.setInterval(pollWave, 250))
})
onUnmounted(() => timers.forEach(clearInterval))
</script>

<template>
  <div>
    <h1 class="gradient-text page-title">{{ t('recorder.title') }}</h1>

    <div class="top-grid">
      <!-- Recording -->
      <section class="card">
        <h2>{{ t('recorder.recording') }}</h2>
        <div class="status-badge" :class="recActive ? 'recording' : ''">
          <span class="dot" :class="recActive ? 'dot-rec' : ''"></span>
          {{ recActive ? `${t('recorder.recordingActive')} · ${recCount} ${t('recorder.messages')} · ${(recElapsed / 1000).toFixed(1)}s` : t('recorder.standby') }}
        </div>
        <div class="actions">
          <button class="btn btn-danger" :disabled="recActive" @click="startRec">{{ t('recorder.startRec') }}</button>
          <button class="btn btn-ghost" :disabled="!recActive" @click="stopRec">{{ t('recorder.stopRec') }}</button>
        </div>
      </section>

      <!-- Playback -->
      <section class="card">
        <h2>{{ t('recorder.playbackControl') }}</h2>
        <div class="status-badge" :class="playActive ? 'playing' : ''">
          <span class="dot" :class="playActive ? 'dot-play' : ''"></span>
          {{ playActive ? `${t('recorder.playbackActive')} · ${playFilename}` : t('recorder.playbackStopped') }}
        </div>
        <label>{{ t('recorder.speed') }}: {{ speed.toFixed(2) }}x</label>
        <input type="range" v-model.number="speed" min="0.25" max="3" step="0.25">
        <label><input type="checkbox" v-model="loop"> {{ t('recorder.loopPlayback') }}</label>
        <div class="actions">
          <button class="btn btn-ghost" :disabled="!playActive" @click="stopPlay">{{ t('recorder.stopPlayback') }}</button>
        </div>
        <div v-if="playActive" class="playback-progress">
          <div class="progress-bar"><div class="fill" :style="{width: (playTotal > 0 ? playProgress / playTotal * 100 : 0) + '%'}"></div></div>
          <div class="progress-text">{{ playProgress }} / {{ playTotal }} <span class="progress-pct">{{ playTotal > 0 ? Math.round(playProgress / playTotal * 100) : 0 }}%</span></div>
        </div>
      </section>

      <!-- Files -->
      <section class="card">
        <h2>{{ t('recorder.files') }}</h2>
        <div class="file-list">
          <div class="file-item" v-for="f in recordings" :key="f.name">
            <span class="file-name">{{ f.name }}</span>
            <span class="file-meta">{{ f.message_count }}{{ t('recorder.messages') }} · {{ (f.duration_ms / 1000).toFixed(1) }}s</span>
            <button class="fbtn play" @click="startPlay(f.name)">▶</button>
            <button class="fbtn del" @click="deleteFile(f.name)">✕</button>
          </div>
          <div v-if="!recordings.length" class="empty">{{ t('recorder.noFiles') }}</div>
        </div>
      </section>
    </div>

    <!-- Live monitoring -->
    <div class="monitor-grid">
      <!-- Wave -->
      <section class="card">
        <h2>{{ t('recorder.playbackWave') }}</h2>
        <div class="wave-row">
          <div class="wave-panel"><div class="wave-ch">A</div><canvas ref="canvasARef" class="wave-canvas"></canvas></div>
          <div class="wave-panel"><div class="wave-ch">B</div><canvas ref="canvasBRef" class="wave-canvas"></canvas></div>
        </div>
      </section>

      <!-- OSC Feed -->
      <section class="card">
        <h2>{{ t('recorder.oscTrigger') }}</h2>
        <div class="osc-feed">
          <div class="osc-row" v-for="(e, i) in oscEvents" :key="i">
            <span class="badge" :class="'b-' + e.channel.toLowerCase()">{{ e.channel }}</span>
            <span class="osc-mode">{{ e.mode }}</span>
            <span class="osc-path">{{ shortPath(e.address) }}</span>
            <span class="osc-val">{{ e.value }}</span>
            <span class="osc-time">{{ timeStr(e.time) }}</span>
          </div>
          <div v-if="!oscEvents.length" class="empty">{{ t('recorder.waitingData') }}</div>
        </div>
      </section>
    </div>

    <div v-if="msg" class="msg-toast">{{ msg }}</div>
  </div>
</template>

<style scoped>
.top-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--sp-4); margin-bottom: var(--sp-4); }
.monitor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }

.status-badge { display: inline-flex; align-items: center; gap: 8px; padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-md); background: rgba(20,16,32,0.6); font-size: var(--text-sm); margin-bottom: var(--sp-3); }
.status-badge.recording { background: rgba(239,68,68,0.1); color: var(--danger); }
.status-badge.playing { background: rgba(34,197,94,0.1); color: var(--success); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.dot-rec { background: var(--danger); animation: pulse 1s infinite; }
.dot-play { background: var(--success); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

.actions { display: flex; gap: var(--sp-2); margin: var(--sp-2) 0; }
label { display: block; font-size: var(--text-xs); color: var(--text-muted); margin: var(--sp-2) 0 var(--sp-1); }
.playback-progress { margin-top: var(--sp-3); }
.progress-bar { height: 8px; background: rgba(139,92,246,0.1); border-radius: 4px; overflow: hidden; }
.fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--success)); transition: width 0.3s; border-radius: 4px; }
.progress-text { display: flex; justify-content: space-between; margin-top: var(--sp-1); font-size: var(--text-xs); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.progress-pct { color: var(--accent); font-weight: 600; }

.file-list { max-height: 200px; overflow-y: auto; }
.file-item { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2); border-radius: var(--radius-sm); font-size: var(--text-sm); transition: background var(--transition); }
.file-item:hover { background: rgba(139,92,246,0.04); }
.file-name { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { color: var(--text-muted); font-size: var(--text-xs); }
.fbtn { border: none; border-radius: var(--radius-sm); padding: 3px 8px; cursor: pointer; color: #fff; font-size: var(--text-xs); transition: transform var(--transition); }
.fbtn:hover { transform: scale(1.1); }
.fbtn.play { background: var(--success); }
.fbtn.del { background: rgba(239,68,68,0.6); }

/* Wave */
.wave-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
.wave-panel { position: relative; }
.wave-ch { position: absolute; top: var(--sp-2); left: var(--sp-3); font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); }
.wave-canvas { width: 100%; height: 100px; border-radius: var(--radius-md); background: rgba(10,8,16,0.5); border: 1px solid var(--border); }

/* OSC Feed */
.osc-feed { max-height: 200px; overflow-y: auto; }
.osc-row { display: flex; gap: var(--sp-2); align-items: center; padding: var(--sp-1) var(--sp-2); font-size: var(--text-xs); border-radius: var(--radius-sm); }
.osc-row:hover { background: rgba(139,92,246,0.04); }
.badge { padding: 2px 6px; border-radius: var(--radius-sm); font-weight: 700; font-size: 10px; }
.b-a { background: rgba(52,211,153,0.12); color: var(--success); }
.b-b { background: rgba(96,165,250,0.12); color: var(--info); }
.osc-mode { color: var(--warning); min-width: 44px; }
.osc-path { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.osc-val { color: var(--accent-2); min-width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
.osc-time { color: var(--text-muted); min-width: 50px; text-align: right; }

.empty { padding: var(--sp-4); text-align: center; color: var(--text-muted); font-size: var(--text-sm); }
.msg-toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); padding: var(--sp-3) var(--sp-5); background: var(--success); color: #000; border-radius: var(--radius-full); font-size: var(--text-sm); font-weight: 500; }

@media (max-width: 768px) {
  .top-grid { grid-template-columns: 1fr; }
  .monitor-grid { grid-template-columns: 1fr; }
  .wave-row { grid-template-columns: 1fr; }
}
</style>
