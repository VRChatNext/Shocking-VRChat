<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

const props = defineProps<{ content: string; size?: number }>()
const canvasRef = ref<HTMLCanvasElement | null>(null)

// Minimal QR generation using the same script as tiny-qr.html
// We load QrCreator from CDN once and use it
let qrLib: any = null
const loaded = ref(false)

function loadQrLib(): Promise<void> {
  if (qrLib) return Promise.resolve()
  return new Promise((resolve) => {
    if ((window as any).QrCreator) { qrLib = (window as any).QrCreator; loaded.value = true; resolve(); return }
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/qr-creator@1.0.0/dist/qr-creator.min.js'
    script.onload = () => { qrLib = (window as any).QrCreator; loaded.value = true; resolve() }
    document.head.appendChild(script)
  })
}

async function render() {
  await loadQrLib()
  const canvas = canvasRef.value
  if (!canvas || !props.content || !qrLib) return
  const size = props.size || 240
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, size, size)
  qrLib.render({
    text: props.content,
    radius: 0.0,
    ecLevel: 'L',
    background: '#ffffff',
    fill: '#1a1a2e',
    size,
  }, canvas)
}

watch(() => props.content, render)
onMounted(render)
</script>

<template>
  <div class="qr-container">
    <canvas ref="canvasRef" class="qr-canvas"></canvas>
  </div>
</template>

<style scoped>
.qr-container { display: flex; justify-content: center; padding: var(--sp-4); }
.qr-canvas { border-radius: var(--radius-md); max-width: 100%; background: #ffffff; padding: 12px; }
</style>
