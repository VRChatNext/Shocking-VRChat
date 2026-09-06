<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps<{
  mode: 'distance' | 'shock' | 'touch'
  channel: 'a' | 'b'
  params: Record<string, any>
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const inputValue = ref(0.7)
const samples = ref<number[]>([])
const effectiveStrength = ref(0)
const durationMs = ref(0)
const loading = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Build request params from props
function buildRequestParams() {
  const p: Record<string, any> = { ...props.params }
  // Ensure trigger_range is included
  if (!p.trigger_range) {
    p.trigger_range = { bottom: 0, top: 0.8 }
  }
  return p
}

async function fetchSimulation() {
  loading.value = true
  try {
    const data = await apiPost('/api/v1/wave_simulate', {
      mode: props.mode,
      channel: props.channel,
      input_value: inputValue.value,
      params: buildRequestParams(),
    })
    samples.value = data.samples || []
    effectiveStrength.value = data.effective_strength ?? 0
    durationMs.value = data.duration_ms ?? 0
  } catch {
    samples.value = []
    effectiveStrength.value = 0
    durationMs.value = 0
  }
  loading.value = false
  await nextTick()
  draw()
}

function debouncedFetch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchSimulation, 300)
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ratio = window.devicePixelRatio || 1
  const W = canvas.clientWidth
  const H = canvas.clientHeight
  if (W <= 0 || H <= 0) return
  canvas.width = W * ratio
  canvas.height = H * ratio
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, W, H)

  // Background grid
  ctx.strokeStyle = 'rgba(139,92,246,0.08)'
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const y = (i / 4) * H
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
  }

  if (!samples.value.length) {
    ctx.fillStyle = 'rgba(139,92,246,0.06)'
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = 'rgba(139,92,246,0.3)'
    ctx.font = '12px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(loading.value ? '...' : t('common.noWaveData'), W / 2, H / 2 + 4)
    return
  }

  const sampleCount = samples.value.length

  // Draw trigger range zone indicator
  const triggerRange = props.params?.trigger_range
  if (triggerRange) {
    const bottomPx = triggerRange.bottom * W
    const topPx = triggerRange.top * W
    ctx.fillStyle = 'rgba(139,92,246,0.04)'
    ctx.fillRect(bottomPx, 0, topPx - bottomPx, H)
  }

  // Draw envelope line (effective_strength as dashed horizontal)
  if (effectiveStrength.value > 0) {
    const envY = (1 - effectiveStrength.value) * H
    ctx.setLineDash([6, 4])
    ctx.strokeStyle = 'rgba(251,191,36,0.5)'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, envY); ctx.lineTo(W, envY); ctx.stroke()
    ctx.setLineDash([])
  }

  // Draw waveform fill
  ctx.beginPath()
  ctx.moveTo(0, H)
  for (let px = 0; px <= W; px++) {
    const t_frac = px / W
    const idx = Math.min(Math.floor(t_frac * sampleCount), sampleCount - 1)
    const val = Math.min(1, Math.max(0, samples.value[idx]))
    ctx.lineTo(px, (1 - val) * H)
  }
  ctx.lineTo(W, H)
  ctx.closePath()
  ctx.fillStyle = 'rgba(139,92,246,0.12)'
  ctx.fill()

  // Draw waveform line
  ctx.beginPath()
  for (let px = 0; px <= W; px++) {
    const t_frac = px / W
    const idx = Math.min(Math.floor(t_frac * sampleCount), sampleCount - 1)
    const val = Math.min(1, Math.max(0, samples.value[idx]))
    if (px === 0) ctx.moveTo(px, (1 - val) * H)
    else ctx.lineTo(px, (1 - val) * H)
  }
  ctx.strokeStyle = '#8b5cf6'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // Labels
  ctx.fillStyle = 'rgba(139,92,246,0.5)'
  ctx.font = '10px Inter, sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText(`${(durationMs.value / 1000).toFixed(1)}s`, 4, H - 4)
  ctx.textAlign = 'right'
  ctx.fillText(`${(effectiveStrength.value * 100).toFixed(0)}%`, W - 4, 12)
}

// Watch all params + input for changes
watch(inputValue, debouncedFetch)
watch(() => props.params, debouncedFetch, { deep: true })
watch(() => props.channel, debouncedFetch)

function onResize() { draw() }

onMounted(() => {
  fetchSimulation()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <div class="wave-sim-wrap">
    <div class="sim-controls">
      <div class="sim-slider">
        <label>{{ t('common.simulatedInput') }}: <strong>{{ inputValue.toFixed(2) }}</strong></label>
        <input type="range" v-model.number="inputValue" min="0" max="1" step="0.01">
      </div>
      <div class="sim-info">
        <span class="info-badge">{{ t('common.effectiveStrength') }}: {{ (effectiveStrength * 100).toFixed(0) }}%</span>
        <span class="info-badge loading" v-if="loading">⟳</span>
      </div>
    </div>
    <div class="sim-canvas-wrap">
      <canvas ref="canvasRef" class="sim-canvas"></canvas>
    </div>
  </div>
</template>

<style scoped>
.wave-sim-wrap {
  width: 100%;
}

.sim-controls {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  margin-bottom: var(--sp-3);
}

.sim-slider {
  flex: 1;
  min-width: 0;
}

.sim-slider label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--sp-1);
  font-weight: 500;
}

.sim-slider label strong {
  color: var(--text);
}

.sim-slider input[type="range"] {
  width: 100%;
  accent-color: var(--accent);
}

.sim-info {
  display: flex;
  gap: var(--sp-2);
  align-items: center;
  flex-shrink: 0;
}

.info-badge {
  font-size: var(--text-xs);
  color: var(--text-muted);
  padding: var(--sp-1) var(--sp-2);
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: border-color var(--transition), color var(--transition);
}

.info-badge:hover {
  border-color: var(--border-hover);
  color: var(--text-secondary);
}

.info-badge.loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.sim-canvas-wrap {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border);
  background: rgba(10, 8, 16, 0.5);
  transition: border-color var(--transition), box-shadow var(--transition);
}

.sim-canvas-wrap:hover {
  border-color: var(--border-hover);
  box-shadow: var(--glow-sm);
}

.sim-canvas {
  width: 100%;
  height: 120px;
  display: block;
}

@media (max-width: 768px) {
  .sim-controls {
    flex-direction: column;
    align-items: stretch;
    gap: var(--sp-2);
  }

  .sim-info {
    justify-content: flex-start;
  }
}
</style>
