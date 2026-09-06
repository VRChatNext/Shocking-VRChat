<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps<{
  presetName: string
  waveScale?: number
  textureFloor?: number
  /** Simulated strength envelope (0-1). If set, modulates the waveform amplitude. */
  envelope?: number
  /** Duration in seconds to display (for shock mode duration vis). 0 = show full preset. */
  displayDuration?: number
  /** Height of the canvas */
  height?: number
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const samples = ref<number[]>([])
const numOps = ref(0)
const loading = ref(false)

let animFrame = 0

async function fetchSamples() {
  if (!props.presetName) {
    samples.value = []
    numOps.value = 0
    draw()
    return
  }
  loading.value = true
  try {
    const data = await api(`/api/v1/wave_presets/${encodeURIComponent(props.presetName)}/samples`)
    samples.value = data.texture_samples || []
    numOps.value = data.num_ops || 0
  } catch {
    samples.value = []
    numOps.value = 0
  }
  loading.value = false
  await nextTick()
  draw()
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

  const scale = props.waveScale ?? 1.0
  const floor = props.textureFloor ?? 0.0
  const env = props.envelope ?? 1.0

  if (!samples.value.length) {
    // No preset selected - show a default square wave pattern
    ctx.fillStyle = 'rgba(139,92,246,0.06)'
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = 'rgba(139,92,246,0.3)'
    ctx.font = '12px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(props.presetName ? t('common.loading') : t('common.noWaveData'), W / 2, H / 2 + 4)
    return
  }

  const sampleCount = samples.value.length
  // Determine how many samples to display
  let displaySamples = sampleCount
  if (props.displayDuration && props.displayDuration > 0) {
    // Each sample = 25ms (1 op = 4 samples = 100ms)
    const samplesNeeded = Math.round(props.displayDuration * 40) // 40 samples/sec
    displaySamples = Math.min(samplesNeeded, sampleCount * 20) // allow repeating up to 20x
  }

  // Draw background grid
  ctx.strokeStyle = 'rgba(139,92,246,0.08)'
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const y = (i / 4) * H
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
  }

  // Draw waveform fill
  ctx.beginPath()
  ctx.moveTo(0, H)
  for (let px = 0; px <= W; px++) {
    const t = px / W
    const sampleIdx = Math.floor(t * displaySamples) % sampleCount
    let val = samples.value[sampleIdx]
    // Apply texture_floor: val ranges 0-1, floor lifts the minimum
    val = floor + val * (1.0 - floor)
    // Apply wave_scale
    val *= scale
    // Apply envelope (simulated strength from trigger)
    val *= env
    val = Math.min(1, Math.max(0, val))
    ctx.lineTo(px, (1 - val) * H)
  }
  ctx.lineTo(W, H)
  ctx.closePath()
  ctx.fillStyle = 'rgba(139,92,246,0.12)'
  ctx.fill()

  // Draw waveform line
  ctx.beginPath()
  for (let px = 0; px <= W; px++) {
    const t = px / W
    const sampleIdx = Math.floor(t * displaySamples) % sampleCount
    let val = samples.value[sampleIdx]
    val = floor + val * (1.0 - floor)
    val *= scale
    val *= env
    val = Math.min(1, Math.max(0, val))
    if (px === 0) ctx.moveTo(px, (1 - val) * H)
    else ctx.lineTo(px, (1 - val) * H)
  }
  ctx.strokeStyle = '#8b5cf6'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // Draw scale/floor indicator lines
  if (floor > 0) {
    const floorY = (1 - floor * scale * env) * H
    ctx.setLineDash([4, 4])
    ctx.strokeStyle = 'rgba(251,191,36,0.4)'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, floorY); ctx.lineTo(W, floorY); ctx.stroke()
    ctx.setLineDash([])
  }

  // Labels
  ctx.fillStyle = 'rgba(139,92,246,0.4)'
  ctx.font = '10px Inter, sans-serif'
  ctx.textAlign = 'left'
  const durationSec = (displaySamples * 0.025).toFixed(1)
  ctx.fillText(`${durationSec}s`, 4, H - 4)
  ctx.textAlign = 'right'
  ctx.fillText(`${(scale * 100).toFixed(0)}%`, W - 4, 12)
}

watch(() => [props.presetName], fetchSamples)
watch(() => [props.waveScale, props.textureFloor, props.envelope, props.displayDuration], () => {
  draw()
})

function onResize() { draw() }

onMounted(() => {
  fetchSamples()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (animFrame) cancelAnimationFrame(animFrame)
})
</script>

<template>
  <div class="wave-preview-wrap">
    <canvas
      ref="canvasRef"
      class="wave-preview-canvas"
      :style="{ height: (height || 80) + 'px' }"
    ></canvas>
  </div>
</template>

<style scoped>
.wave-preview-wrap {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border);
  background: rgba(10, 8, 16, 0.5);
}
.wave-preview-canvas {
  width: 100%;
  display: block;
}
</style>
