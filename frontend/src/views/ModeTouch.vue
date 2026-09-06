<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, apiPost } from '@/api'
import { useI18n } from '@/i18n'
import WavePreview from '@/components/WavePreview.vue'
import WaveSimulator from '@/components/WaveSimulator.vue'

const { t } = useI18n()
const ch = ref<'a' | 'b'>('a')
const wavePreset = ref('')
const waveScale = ref(1.0)
const nDerivative = ref(1)
const textureFloor = ref(0)
const windowOps = ref(4)
const sampleStep = ref(1.0)
const advanceSamples = ref(4.0)
const envelopeCurve = ref('smoothstep')
const triggerBottom = ref(0)
const triggerTop = ref(0.8)
const presets = ref<string[]>([])
const msg = ref('')

// Reactive params for wave simulator
const simParams = computed(() => ({
  wave_preset: wavePreset.value || null,
  wave_scale: waveScale.value,
  n_derivative: nDerivative.value,
  texture_floor: textureFloor.value,
  wave_window_ops: windowOps.value,
  wave_sample_step: sampleStep.value,
  wave_advance_samples: advanceSamples.value,
  wave_envelope_curve: envelopeCurve.value,
  trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
}))

async function loadPresets() {
  const data = await api('/api/v1/wave_presets')
  presets.value = data.presets || []
}

async function load() {
  const data = await api(`/api/v1/mode_config/${ch.value}/touch`)
  const cfg = data.config || {}
  wavePreset.value = cfg.wave_preset || ''
  waveScale.value = cfg.wave_scale ?? 1.0
  nDerivative.value = cfg.n_derivative ?? 1
  textureFloor.value = cfg.texture_floor ?? 0
  windowOps.value = cfg.wave_window_ops ?? 4
  sampleStep.value = cfg.wave_sample_step ?? 1.0
  advanceSamples.value = cfg.wave_advance_samples ?? 4.0
  envelopeCurve.value = cfg.wave_envelope_curve || 'smoothstep'
  triggerBottom.value = data.trigger_range?.bottom ?? 0
  triggerTop.value = data.trigger_range?.top ?? 0.8
}

async function save() {
  const data = await apiPost(`/api/v1/mode_config/${ch.value}/touch`, {
    wave_preset: wavePreset.value || null,
    wave_scale: waveScale.value,
    n_derivative: nDerivative.value,
    texture_floor: textureFloor.value,
    wave_window_ops: windowOps.value,
    wave_sample_step: sampleStep.value,
    wave_advance_samples: advanceSamples.value,
    wave_envelope_curve: envelopeCurve.value,
    trigger_range: { bottom: triggerBottom.value, top: triggerTop.value },
  })
  msg.value = data.success ? t('common.saved') : t('common.saveFailed')
  setTimeout(() => msg.value = '', 3000)
}

function switchCh(c: 'a' | 'b') { ch.value = c; load() }
onMounted(() => { loadPresets(); load() })
</script>

<template>
  <div>
    <h1 class="gradient-text page-title">{{ t('modeTouch.title') }}</h1>
    <p class="page-desc">{{ t('modeTouch.desc') }}</p>

    <div class="ch-tabs">
      <button :class="{ active: ch === 'a' }" @click="switchCh('a')">{{ t('common.channelA') }}</button>
      <button :class="{ active: ch === 'b' }" @click="switchCh('b')">{{ t('common.channelB') }}</button>
    </div>

    <div class="grid">
      <section class="card">
        <h2>{{ t('modeTouch.params') }}</h2>
        <div class="field">
          <label>{{ t('modeTouch.derivative') }}</label>
          <select v-model.number="nDerivative">
            <option :value="0">{{ t('modeTouch.deriv0') }}</option>
            <option :value="1">{{ t('modeTouch.deriv1') }}</option>
            <option :value="2">{{ t('modeTouch.deriv2') }}</option>
            <option :value="3">{{ t('modeTouch.deriv3') }}</option>
          </select>
          <p class="hint">{{ t('modeTouch.derivHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('common.wavePreset') }}</label>
          <select v-model="wavePreset">
            <option value="">{{ t('modeTouch.presetNone') }}</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <div class="field">
          <label>{{ t('common.waveScale') }}: {{ (waveScale * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="waveScale" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>{{ t('common.textureFloor') }}: {{ (textureFloor * 100).toFixed(0) }}%</label>
          <input type="range" v-model.number="textureFloor" min="0" max="0.5" step="0.01">
          <p class="hint">{{ t('modeTouch.floorHint') }}</p>
        </div>
        <div class="field" v-if="wavePreset">
          <label>{{ t('modeTouch.preview') }}</label>
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
          <p class="hint">{{ t('modeTouch.bottomHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('common.triggerTop') }}: {{ triggerTop.toFixed(2) }}</label>
          <input type="range" v-model.number="triggerTop" min="0.1" max="1" step="0.01">
          <p class="hint">{{ t('modeTouch.topHint') }}</p>
        </div>
        <div class="visual">
          <div class="bar">
            <div class="fill" :style="{ left: (triggerBottom*100)+'%', width: ((triggerTop-triggerBottom)*100)+'%' }"></div>
            <span class="mark" :style="{ left: (triggerBottom*100)+'%' }">{{ triggerBottom.toFixed(2) }}</span>
            <span class="mark" :style="{ left: (triggerTop*100)+'%' }">{{ triggerTop.toFixed(2) }}</span>
          </div>
        </div>

        <h2 style="margin-top:var(--sp-5)">{{ t('modeTouch.advancedWaveWindow') }}</h2>
        <div class="field">
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
      </section>
    </div>

    <!-- Wave Simulator -->
    <section class="card" style="margin-top:var(--sp-5)">
      <h2>{{ t('common.waveSimulator') }}</h2>
      <WaveSimulator
        mode="touch"
        :channel="ch"
        :params="simParams"
      />
    </section>

    <div class="save-bar">
      <button class="btn btn-primary" @click="save">💾 {{ t('common.save') }}</button>
      <button class="btn btn-ghost" @click="load">↺ {{ t('common.reload') }}</button>
      <span class="msg">{{ msg }}</span>
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
.field select { width: 100%; }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.visual { margin-top: var(--sp-3); }
.bar { position: relative; height: 8px; background: var(--bg-inset); border-radius: 4px; }
.fill { position: absolute; top: 0; height: 100%; background: var(--accent); border-radius: 4px; opacity: 0.4; }
.mark { position: absolute; top: 14px; font-size: 10px; color: var(--text-muted); transform: translateX(-50%); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.msg { font-size: var(--text-sm); color: var(--success); }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
</style>
