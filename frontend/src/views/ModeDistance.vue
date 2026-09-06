<script setup lang="ts">
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import { api, apiPost, apiDelete } from '@/api'
import { useI18n } from '@/i18n'
import WavePreview from '@/components/WavePreview.vue'
import WaveSimulator from '@/components/WaveSimulator.vue'

const { t } = useI18n()

// --- Distance config state ---
const ch = ref<'a' | 'b'>('a')
const freqMs = ref(10)
const wavePreset = ref('')
const waveScale = ref(1.0)
const textureFloor = ref(0)
const windowOps = ref(4)
const sampleStep = ref(1.0)
const advanceSamples = ref(4.0)
const envelopeCurve = ref('smoothstep')
const triggerBottom = ref(0)
const triggerTop = ref(0.8)
const presets = ref<string[]>([])
const distMsg = ref('')
const showAdvanced = ref(false)

// Reactive params for wave simulator
const simParams = computed(() => ({
  freq_ms: freqMs.value,
  wave_preset: wavePreset.value || null,
  wave_scale: waveScale.value,
  texture_floor: textureFloor.value,
  wave_window_ops: windowOps.value,
  wave_sample_step: sampleStep.value,
  wave_advance_samples: advanceSamples.value,
  wave_envelope_curve: envelopeCurve.value,
  trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
}))

// --- Curve editor state ---
const paramList = ref<string[]>([])
const activeParam = ref('')
const points = ref<{x: number; y: number}[]>([])
const curveMsg = ref('')
const canvasRef = ref<HTMLCanvasElement | null>(null)
let dragging: number | null = null
const configuredCurves = ref<Record<string, any>>({})

const PRESETS: Record<string, {x:number;y:number}[]> = {
  relu: [{x:0,y:0},{x:0.1,y:0},{x:1,y:1}],
  linear: [{x:0,y:0},{x:1,y:1}],
  quadratic: [{x:0,y:0},{x:0.25,y:0.0625},{x:0.5,y:0.25},{x:0.75,y:0.5625},{x:1,y:1}],
  scurve: [{x:0,y:0},{x:0.25,y:0.06},{x:0.5,y:0.5},{x:0.75,y:0.94},{x:1,y:1}],
  step: [{x:0,y:0},{x:0.29,y:0},{x:0.3,y:0.5},{x:0.69,y:0.5},{x:0.7,y:1},{x:1,y:1}],
}

// --- Distance config ---
async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function loadDistance() {
  const data = await api(`/api/v1/mode_config/${ch.value}/distance`)
  const cfg = data.config || {}
  freqMs.value = cfg.freq_ms ?? 10
  wavePreset.value = cfg.wave_preset || ''
  waveScale.value = cfg.wave_scale ?? 1.0
  textureFloor.value = cfg.texture_floor ?? 0
  windowOps.value = cfg.wave_window_ops ?? 4
  sampleStep.value = cfg.wave_sample_step ?? 1.0
  advanceSamples.value = cfg.wave_advance_samples ?? 4.0
  envelopeCurve.value = cfg.wave_envelope_curve || 'smoothstep'
  triggerBottom.value = data.trigger_range?.bottom ?? 0
  triggerTop.value = data.trigger_range?.top ?? 0.8
}

async function saveDistance() {
  const data = await apiPost(`/api/v1/mode_config/${ch.value}/distance`, {
    freq_ms: freqMs.value,
    wave_preset: wavePreset.value || null,
    wave_scale: waveScale.value,
    texture_floor: textureFloor.value,
    wave_window_ops: windowOps.value,
    wave_sample_step: sampleStep.value,
    wave_advance_samples: advanceSamples.value,
    wave_envelope_curve: envelopeCurve.value,
    trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
  })
  distMsg.value = data.success ? t('common.saved') : t('common.saveFailed')
  setTimeout(() => distMsg.value = '', 3000)
}

function switchCh(c: 'a' | 'b') { ch.value = c; loadDistance() }

// --- Curve editor ---
async function loadParams() {
  const data = await api('/api/v1/config')
  const basic = data.basic?.dglab3 || {}
  const allParams: string[] = ['channel_a', 'channel_b']
  for (const chKey of ['channel_a', 'channel_b']) {
    const params = basic[chKey]?.avatar_params || []
    for (const p of params) {
      const path = typeof p === 'string' ? p : p.path
      if (path && !allParams.includes(path)) allParams.push(path)
    }
  }
  paramList.value = allParams
  if (allParams.length && !activeParam.value) {
    activeParam.value = allParams[0]
  }
  await loadCurveList()
  loadCurve()
}

async function loadCurveList() {
  try {
    const data = await api('/api/v1/curve')
    configuredCurves.value = data.curves || {}
  } catch {}
}

function hasCurve(key: string): boolean { return key in configuredCurves.value }

function paramLabel(key: string): string {
  if (key === 'channel_a') return t('common.channelA') + ' ' + t('common.default')
  if (key === 'channel_b') return t('common.channelB') + ' ' + t('common.default')
  return key.replace('/avatar/parameters/', '')
}

async function loadCurve() {
  if (!activeParam.value) return
  const data = await api(`/api/v1/curve/${encodeURIComponent(activeParam.value)}`)
  points.value = data.points || PRESETS.relu
  sortPoints()
  await nextTick()
  draw()
  curveMsg.value = ''
}

async function saveCurve() {
  if (!activeParam.value) return
  const data = await apiPost(`/api/v1/curve/${encodeURIComponent(activeParam.value)}`, { points: points.value })
  curveMsg.value = data.success ? t('common.saved') : t('common.saveFailed')
  await loadCurveList()
  setTimeout(() => curveMsg.value = '', 3000)
}

async function deleteCurve() {
  if (!activeParam.value) return
  await apiDelete(`/api/v1/curve/${encodeURIComponent(activeParam.value)}`)
  curveMsg.value = t('modeDistance.curveResetDone')
  await loadCurveList()
  loadCurve()
  setTimeout(() => curveMsg.value = '', 3000)
}

function interpolate(px: number, pts: {x:number;y:number}[]): number {
  if (!pts.length) return 0
  if (px <= pts[0].x) return pts[0].y
  if (px >= pts[pts.length-1].x) return pts[pts.length-1].y
  for (let i = 0; i < pts.length - 1; i++) {
    if (px >= pts[i].x && px <= pts[i+1].x) {
      const t = (px - pts[i].x) / (pts[i+1].x - pts[i].x)
      return pts[i].y + t * (pts[i+1].y - pts[i].y)
    }
  }
  return 0
}

function sortPoints() { points.value.sort((a, b) => a.x - b.x) }

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ratio = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  canvas.width = W * ratio
  canvas.height = H * ratio
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, W, H)

  ctx.strokeStyle = 'rgba(139,92,246,0.06)'
  ctx.lineWidth = 1
  for (let i = 0; i <= 10; i++) {
    const x = (i / 10) * W, y = (i / 10) * H
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
  }

  ctx.fillStyle = 'rgba(139,92,246,0.3)'
  ctx.font = '11px Inter, sans-serif'
  ctx.fillText('0', 4, H - 4)
  ctx.fillText('1', W - 12, H - 4)
  ctx.fillText('1', 4, 14)
  ctx.fillText(t('modeDistance.axisParamValue'), W / 2 - 24, H - 4)

  const pts = points.value
  ctx.beginPath()
  ctx.moveTo(0, H)
  for (let px = 0; px <= W; px++) {
    const x = px / W
    const y = interpolate(x, pts)
    ctx.lineTo(px, (1 - y) * H)
  }
  ctx.lineTo(W, H)
  ctx.closePath()
  ctx.fillStyle = 'rgba(139,92,246,0.08)'
  ctx.fill()

  ctx.beginPath()
  for (let px = 0; px <= W; px++) {
    const x = px / W
    const y = interpolate(x, pts)
    if (px === 0) ctx.moveTo(px, (1 - y) * H)
    else ctx.lineTo(px, (1 - y) * H)
  }
  ctx.strokeStyle = '#8b5cf6'
  ctx.lineWidth = 2.5
  ctx.shadowColor = 'rgba(139,92,246,0.4)'
  ctx.shadowBlur = 8
  ctx.stroke()
  ctx.shadowBlur = 0

  pts.forEach((p, i) => {
    const cx = p.x * W, cy = (1 - p.y) * H
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.fillStyle = dragging === i ? '#fff' : '#a78bfa'
    ctx.fill()
    ctx.strokeStyle = '#13111c'
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(cx, cy, 7, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(139,92,246,0.4)'
    ctx.lineWidth = 1
    ctx.stroke()
  })
}

function toCoord(e: MouseEvent): [number, number] {
  const canvas = canvasRef.value!
  const r = canvas.getBoundingClientRect()
  const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
  const y = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height))
  return [x, y]
}

function findPoint(mx: number, my: number): number {
  const canvas = canvasRef.value!
  const W = canvas.clientWidth, H = canvas.clientHeight
  for (let i = 0; i < points.value.length; i++) {
    const px = points.value[i].x * W, py = (1 - points.value[i].y) * H
    const r = canvas.getBoundingClientRect()
    const cx = mx - r.left, cy = my - r.top
    if (Math.hypot(cx - px, cy - py) < 14) return i
  }
  return -1
}

function onMouseDown(e: MouseEvent) {
  if (e.button === 2) {
    const idx = findPoint(e.clientX, e.clientY)
    if (idx >= 0) { points.value.splice(idx, 1); draw() }
    return
  }
  const idx = findPoint(e.clientX, e.clientY)
  if (idx >= 0) { dragging = idx }
  else {
    const [x, y] = toCoord(e)
    points.value.push({x, y})
    sortPoints()
    dragging = points.value.findIndex(p => Math.abs(p.x - x) < 0.001 && Math.abs(p.y - y) < 0.001)
    draw()
  }
}

function onMouseMove(e: MouseEvent) {
  if (dragging === null) return
  const [x, y] = toCoord(e)
  points.value[dragging] = {x, y}
  sortPoints()
  dragging = points.value.findIndex(p => Math.abs(p.x - x) < 0.001 && Math.abs(p.y - y) < 0.001)
  draw()
}

function onMouseUp() { dragging = null; draw() }
function applyPreset(name: string) {
  points.value = JSON.parse(JSON.stringify(PRESETS[name]))
  sortPoints()
  draw()
}

watch(points, draw, { deep: true })
onMounted(() => {
  loadPresets()
  loadDistance()
  loadParams()
  window.addEventListener('resize', draw)
})
</script>

<template>
  <div>
    <h1 class="gradient-text page-title">{{ t('modeDistance.title') }}</h1>
    <p class="page-desc">{{ t('modeDistance.desc') }}</p>

    <div class="ch-tabs">
      <button :class="{ active: ch === 'a' }" @click="switchCh('a')">{{ t('common.channelA') }}</button>
      <button :class="{ active: ch === 'b' }" @click="switchCh('b')">{{ t('common.channelB') }}</button>
    </div>

    <!-- Distance Config -->
    <div class="grid">
      <section class="card">
        <h2>{{ t('modeDistance.waveParams') }}</h2>
        <div class="field">
          <label>{{ t('common.wavePreset') }}</label>
          <select v-model="wavePreset">
            <option value="">{{ t('modeDistance.presetNone') }}</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p }}</option>
          </select>
          <p class="hint">{{ t('modeDistance.presetHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('common.waveScale') }}: {{ (waveScale * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="waveScale" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>{{ t('common.textureFloor') }}: {{ (textureFloor * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="textureFloor" min="0" max="0.5" step="0.01">
          <p class="hint">{{ t('modeDistance.floorHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('modeDistance.freqMs') }}: {{ freqMs }}ms</label>
          <input type="range" v-model.number="freqMs" min="10" max="240" step="5">
          <p class="hint">{{ t('modeDistance.freqMsHint') }}</p>
        </div>
        <div class="field" v-if="wavePreset">
          <label>{{ t('modeShock.preview') }}</label>
          <WavePreview
            :preset-name="wavePreset"
            :wave-scale="waveScale"
            :texture-floor="textureFloor"
            :height="90"
          />
        </div>
      </section>

      <section class="card">
        <h2>{{ t('common.triggerRange') }}</h2>
        <div class="field">
          <label>{{ t('common.triggerBottom') }}: {{ triggerBottom.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerBottom" min="0" max="0.9" step="0.01">
          <p class="hint">{{ t('modeDistance.bottomHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('common.triggerTop') }}: {{ triggerTop.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerTop" min="0.1" max="1" step="0.01">
          <p class="hint">{{ t('modeDistance.topHint') }}</p>
        </div>
        <div class="visual">
          <div class="bar">
            <div class="fill" :style="{ left: (triggerBottom*100)+'%', width: ((triggerTop-triggerBottom)*100)+'%' }"></div>
            <span class="mark" :style="{ left: (triggerBottom*100)+'%' }">{{ triggerBottom.toFixed(2) }}</span>
            <span class="mark" :style="{ left: (triggerTop*100)+'%' }">{{ triggerTop.toFixed(2) }}</span>
          </div>
        </div>

        <div style="margin-top:var(--sp-4)">
          <button class="btn btn-ghost btn-sm" @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '▾' : '▸' }} {{ t('common.advanced') }}
          </button>
        </div>
        <template v-if="showAdvanced">
          <div class="field" style="margin-top:var(--sp-3)">
            <label>{{ t('modeDistance.windowSize') }}: {{ windowOps }} ops</label>
            <input type="range" v-model.number="windowOps" min="1" max="16" step="1">
          </div>
          <div class="field">
            <label>{{ t('modeDistance.sampleStep') }}: {{ sampleStep.toFixed(2) }}</label>
            <input type="range" v-model.number="sampleStep" min="0.25" max="4" step="0.25">
          </div>
          <div class="field">
            <label>{{ t('modeDistance.windowAdvance') }}: {{ advanceSamples.toFixed(1) }}</label>
            <input type="range" v-model.number="advanceSamples" min="1" max="16" step="0.5">
          </div>
          <div class="field">
            <label>{{ t('modeDistance.envelope') }}</label>
            <select v-model="envelopeCurve">
              <option value="smoothstep">smoothstep</option>
              <option value="linear">linear</option>
              <option value="ease_in">ease_in</option>
              <option value="ease_out">ease_out</option>
            </select>
          </div>
        </template>
      </section>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="saveDistance">{{ t('modeDistance.saveDistance') }}</button>
      <button class="btn btn-ghost" @click="loadDistance">{{ t('common.reload') }}</button>
      <span class="msg">{{ distMsg }}</span>
    </div>

    <!-- Wave Simulator -->
    <section class="card" style="margin-top:var(--sp-5)">
      <h2>{{ t('common.waveSimulator') }}</h2>
      <WaveSimulator
        mode="distance"
        :channel="ch"
        :params="simParams"
      />
    </section>

    <!-- Curve Editor Section -->
    <div class="section-divider"></div>
    <h2 class="gradient-text" style="font-size:var(--text-xl);margin-bottom:var(--sp-2)">{{ t('modeDistance.curveTitle') }}</h2>
    <p class="page-desc">{{ t('modeDistance.curveDesc') }}</p>

    <div class="param-selector">
      <label>{{ t('modeDistance.curveParam') }}:</label>
      <select v-model="activeParam" @change="loadCurve()">
        <option v-for="p in paramList" :key="p" :value="p">
          {{ paramLabel(p) }}{{ hasCurve(p) ? ' ●' : '' }}
        </option>
      </select>
      <span class="curve-status" v-if="activeParam">
        {{ hasCurve(activeParam) ? t('modeDistance.curveCustom') : t('modeDistance.curveDefault') }}
      </span>
    </div>

    <div class="editor-grid">
      <div class="card canvas-card">
        <canvas
          ref="canvasRef"
          class="curve-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @contextmenu.prevent
        ></canvas>
      </div>

      <div class="side-panel">
        <div class="card">
          <h3>{{ t('modeDistance.curvePresets') }}</h3>
          <div class="preset-grid">
            <button v-for="(_, name) in PRESETS" :key="name" class="preset-btn" @click="applyPreset(name)">{{ name }}</button>
          </div>
        </div>
        <div class="card">
          <h3>{{ t('modeDistance.curvePoints') }} ({{ points.length }})</h3>
          <div class="point-list">
            <div v-for="(p, i) in points" :key="i" class="pt-row">
              <span class="pt-idx">{{ i }}</span>
              <span class="pt-coord">({{ p.x.toFixed(3) }}, {{ p.y.toFixed(3) }})</span>
              <button class="pt-del" @click="points.splice(i, 1); draw()">✕</button>
            </div>
          </div>
        </div>
        <div class="actions">
          <button class="btn btn-primary" @click="saveCurve">{{ t('modeDistance.curveSave') }}</button>
          <button class="btn btn-ghost" @click="loadCurve">{{ t('common.reload') }}</button>
          <button class="btn btn-danger" @click="deleteCurve">{{ t('modeDistance.curveReset') }}</button>
        </div>
        <div v-if="curveMsg" class="msg-text">{{ curveMsg }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ch-tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.ch-tabs button { padding: var(--sp-2) var(--sp-4); border: 1px solid var(--border); border-radius: var(--radius-md); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-sm); }
.ch-tabs button.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.08); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-1); font-weight: 500; }
.field select, .field input[type="number"] { width: 100%; }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.visual { margin-top: var(--sp-3); }
.bar { position: relative; height: 8px; background: var(--bg-inset); border-radius: 4px; }
.fill { position: absolute; top: 0; height: 100%; background: var(--accent); border-radius: 4px; opacity: 0.4; }
.mark { position: absolute; top: 14px; font-size: 10px; color: var(--text-muted); transform: translateX(-50%); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.msg { font-size: var(--text-sm); color: var(--success); }

.section-divider { margin: var(--sp-6) 0; border-top: 1px solid var(--border); }

/* Curve editor */
.param-selector { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.param-selector label { font-size: var(--text-sm); color: var(--text-muted); font-weight: 500; white-space: nowrap; }
.param-selector select { flex: 1; max-width: 400px; }
.curve-status { font-size: var(--text-xs); color: var(--accent); white-space: nowrap; }

.editor-grid { display: grid; grid-template-columns: 1fr 240px; gap: var(--sp-4); }
.canvas-card { padding: var(--sp-3); }
.curve-canvas {
  width: 100%; height: 320px; cursor: crosshair;
  border-radius: var(--radius-lg);
  background: rgba(10, 8, 16, 0.6);
  border: 1px solid var(--border);
}

.side-panel { display: flex; flex-direction: column; gap: var(--sp-3); }
.preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-2); }
.preset-btn {
  padding: var(--sp-2) var(--sp-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: 500;
  transition: all var(--transition);
}
.preset-btn:hover { border-color: var(--accent); color: var(--text); background: rgba(139,92,246,0.06); }

.point-list { max-height: 140px; overflow-y: auto; }
.pt-row { display: flex; align-items: center; gap: var(--sp-2); padding: 2px 0; font-variant-numeric: tabular-nums; font-size: var(--text-xs); }
.pt-idx { color: var(--text-muted); width: 16px; }
.pt-coord { color: var(--text-secondary); flex: 1; }
.pt-del { border: none; background: transparent; color: var(--text-muted); cursor: pointer; padding: 2px 6px; border-radius: 4px; }
.pt-del:hover { color: var(--danger); }

.actions { display: flex; gap: var(--sp-2); flex-wrap: wrap; }
.msg-text { font-size: var(--text-sm); color: var(--success); margin-top: var(--sp-2); }

@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; }
  .editor-grid { grid-template-columns: 1fr; }
}
</style>
