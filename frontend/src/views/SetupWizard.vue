<script setup lang="ts">
import { ref } from 'vue'
import { apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const step = ref(0)
const totalSteps = 2
const saving = ref(false)
const done = ref(false)
const errMsg = ref('')

// Config state
const scene = ref('')  // 'pcs', 'lms', 'custom'
const sameAB = ref(true)
const modeA = ref('distance')
const modeB = ref('distance')
const strengthA = ref(20)
const strengthB = ref(20)
const customParams = ref('')

const SCENES = [
  { id: 'pcs', tKey: 'PCS', icon: '🤚', params: ['/avatar/parameters/pcs/contact/enterPass'] },
  { id: 'pcs_multi', tKey: 'PCSMulti', icon: '👐', params: ['/avatar/parameters/pcs/sps/pussy', '/avatar/parameters/pcs/sps/ass'] },
  { id: 'lms', tKey: 'LMS', icon: '💋', params: ['/avatar/parameters/lms-penis-proximityA*'] },
  { id: 'custom', tKey: 'Custom', icon: '⌨️', params: [] },
]

const MODES = [
  { value: 'distance', tKey: 'Distance' },
  { value: 'shock', tKey: 'Shock' },
  { value: 'touch', tKey: 'Touch' },
  { value: 'combo', tKey: 'Combo' },
]

function getSelectedParams(): { a: string[]; b: string[] } {
  const selected = SCENES.find(s => s.id === scene.value)
  if (scene.value === 'custom') {
    const lines = customParams.value.split('\n').map(l => l.trim()).filter(l => l.startsWith('/'))
    return { a: lines, b: sameAB.value ? lines : lines }
  }
  if (scene.value === 'pcs_multi') {
    return {
      a: ['/avatar/parameters/pcs/sps/pussy', '/avatar/parameters/pcs/sps/boobs'],
      b: ['/avatar/parameters/pcs/sps/ass', '/avatar/parameters/pcs/sps/mouth'],
    }
  }
  const params = selected?.params || []
  return { a: params, b: sameAB.value ? params : params }
}

function canProceed(): boolean {
  if (step.value === 0) return !!scene.value
  return true
}

async function waitForBackend() {
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 300))
    try { await fetch('/api/v1/status') } catch { break }
  }
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 500))
    try {
      const resp = await fetch('/api/v1/status')
      if (resp.ok) return
    } catch {}
  }
}

async function save() {
  saving.value = true; errMsg.value = ''
  const { a, b } = getSelectedParams()
  try {
    const data = await apiPost('/api/v1/setup', {
      channel_a: { mode: modeA.value, strength_limit: strengthA.value, avatar_params: a },
      channel_b: { mode: sameAB.value ? modeA.value : modeB.value, strength_limit: sameAB.value ? strengthA.value : strengthB.value, avatar_params: b },
    })
    if (data.success) {
      done.value = true
      await waitForBackend()
      window.location.href = '/dashboard'
    } else { errMsg.value = data.message || t('setup.saveFailed') }
  } catch (e: any) { errMsg.value = e.message }
  finally { saving.value = false }
}
</script>

<template>
  <div class="wizard-page" v-if="!done">
    <div class="wizard-card">
      <div class="wizard-header">
        <span class="wizard-logo">⚡</span>
        <h1 class="gradient-text">Shocking VRChat</h1>
        <p class="wizard-sub">{{ t('setup.title') }} · {{ t('setup.subtitle') }}</p>
      </div>

      <!-- Progress -->
      <div class="progress">
        <div class="progress-step" v-for="i in totalSteps" :key="i" :class="{ active: step === i-1, done: step > i-1 }">
          <div class="progress-dot">{{ step > i-1 ? '✓' : i }}</div>
          <span class="progress-label">{{ [t('setup.stepScene'), t('setup.stepConfirm')][i-1] }}</span>
        </div>
      </div>

      <!-- Step 0: Scene -->
      <div v-if="step === 0" class="step">
        <h2>{{ t('setup.sceneTitle') }}</h2>
        <div class="scene-grid">
          <div v-for="s in SCENES" :key="s.id" class="scene-card" :class="{selected: scene === s.id}" @click="scene = s.id">
            <span class="scene-icon">{{ s.icon }}</span>
            <div class="scene-text">
              <div class="scene-name">{{ t('setup.scene' + s.tKey) }}</div>
              <div class="scene-desc">{{ t('setup.scene' + s.tKey + 'Desc') }}</div>
            </div>
          </div>
        </div>

        <div v-if="scene === 'custom'" class="custom-section">
          <label>{{ t('setup.customLabel') }}</label>
          <textarea v-model="customParams" rows="3" placeholder="/avatar/parameters/..."></textarea>
        </div>

        <div class="mode-section" v-if="scene">
          <h3>{{ t('setup.modeTitle') }}</h3>
          <div class="mode-row">
            <div v-for="m in MODES" :key="m.value" class="mode-chip" :class="{selected: modeA === m.value}" @click="modeA = m.value">
              {{ t('setup.mode' + m.tKey) }}
              <span class="mode-chip-desc">{{ t('setup.mode' + m.tKey + 'Desc') }}</span>
            </div>
          </div>
          <label class="same-check" v-if="scene !== 'pcs_multi'">
            <input type="checkbox" v-model="sameAB">
            <span>{{ t('setup.sameAB') }}</span>
          </label>
          <div v-if="!sameAB && scene !== 'pcs_multi'" class="mode-row" style="margin-top:var(--sp-3)">
            <span class="ch-label">{{ t('common.channelB') }}:</span>
            <div v-for="m in MODES" :key="m.value" class="mode-chip sm" :class="{selected: modeB === m.value}" @click="modeB = m.value">
              {{ t('setup.mode' + m.tKey) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Step 1: Strength + Confirm -->
      <div v-if="step === 1" class="step">
        <h2>{{ t('setup.strengthTitle') }}</h2>
        <div class="strength-section">
          <div class="field">
            <label>{{ sameAB ? t('setup.strengthLabel') : t('setup.strengthLabelA') }}: <strong class="accent">{{ strengthA }}</strong> / 200</label>
            <input type="range" v-model.number="strengthA" min="0" max="200" step="1">
            <p class="hint">{{ t('setup.strengthHint') }}</p>
          </div>
          <div class="field" v-if="!sameAB">
            <label>{{ t('setup.strengthLabelB') }}: <strong class="accent">{{ strengthB }}</strong> / 200</label>
            <input type="range" v-model.number="strengthB" min="0" max="200" step="1">
          </div>
        </div>

        <div class="summary-card">
          <h3>{{ t('setup.summary') }}</h3>
          <div class="summary-row"><span>{{ t('setup.summaryScene') }}:</span><span>{{ SCENES.find(s => s.id === scene)?.tKey ? t('setup.scene' + SCENES.find(s => s.id === scene)!.tKey) : t('setup.sceneCustom') }}</span></div>
          <div class="summary-row"><span>{{ t('setup.summaryMode') }}:</span><span>{{ t('setup.mode' + (MODES.find(m => m.value === modeA)?.tKey || 'Distance')) }}{{ !sameAB ? ' / ' + t('setup.mode' + (MODES.find(m => m.value === modeB)?.tKey || 'Distance')) : '' }}</span></div>
          <div class="summary-row"><span>{{ t('setup.summaryStrength') }}:</span><span>{{ strengthA }}{{ !sameAB ? ' / ' + strengthB : '' }}</span></div>
        </div>

        <p class="final-hint">{{ t('setup.finalHint') }}</p>
      </div>

      <!-- Nav -->
      <div class="wizard-nav">
        <button class="btn btn-ghost" v-if="step > 0" @click="step--">{{ t('setup.prevStep') }}</button>
        <div class="spacer"></div>
        <button class="btn btn-primary" v-if="step < totalSteps - 1" :disabled="!canProceed()" @click="step++">
          {{ t('setup.nextStep') }}
        </button>
        <button class="btn btn-primary" v-if="step === totalSteps - 1" :disabled="saving" @click="save">
          {{ saving ? t('setup.saving') : '✓ ' + t('setup.saveAndStart') }}
        </button>
      </div>
      <div v-if="errMsg" class="err">{{ errMsg }}</div>
    </div>
  </div>

  <!-- Done -->
  <div class="wizard-page" v-else>
    <div class="wizard-card done-card">
      <div class="done-icon">✓</div>
      <h2 class="gradient-text">{{ t('setup.doneTitle') }}</h2>
      <p>{{ t('setup.doneMsg') }}</p>
    </div>
  </div>
</template>

<style scoped>
.wizard-page { display: flex; align-items: center; justify-content: center; min-height: 80vh; }
.wizard-card {
  width: 100%; max-width: 600px;
  background: var(--bg-card);
  backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--sp-8);
}
.wizard-header { text-align: center; margin-bottom: var(--sp-4); }
.wizard-logo { font-size: 2em; filter: drop-shadow(0 0 10px rgba(139,92,246,0.5)); }
.wizard-header h1 { font-size: var(--text-2xl); margin-top: var(--sp-2); }
.wizard-sub { color: var(--text-muted); font-size: var(--text-sm); margin-top: var(--sp-1); }

/* Progress */
.progress { display: flex; justify-content: center; gap: var(--sp-5); margin-bottom: var(--sp-6); }
.progress-step { display: flex; flex-direction: column; align-items: center; gap: var(--sp-1); }
.progress-dot { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); font-weight: 700; background: var(--bg-tertiary); color: var(--text-muted); border: 2px solid var(--border); transition: all var(--transition); }
.progress-step.active .progress-dot { background: var(--accent); color: #fff; border-color: var(--accent); box-shadow: 0 0 12px rgba(139,92,246,0.4); }
.progress-step.done .progress-dot { background: var(--success); color: #fff; border-color: var(--success); }
.progress-label { font-size: 10px; color: var(--text-muted); }
.progress-step.active .progress-label { color: var(--accent); }

.step h2 { font-size: var(--text-lg); margin-bottom: var(--sp-4); }

/* Scenes */
.scene-grid { display: flex; flex-direction: column; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.scene-card { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-4); border: 1px solid var(--border); border-radius: var(--radius-md); cursor: pointer; transition: all var(--transition); }
.scene-card:hover { border-color: var(--border-hover); }
.scene-card.selected { border-color: var(--accent); background: rgba(139,92,246,0.08); box-shadow: var(--glow-sm); }
.scene-icon { font-size: 1.5em; flex-shrink: 0; }
.scene-name { font-size: var(--text-sm); font-weight: 600; }
.scene-desc { font-size: var(--text-xs); color: var(--text-muted); margin-top: 1px; }

.custom-section { margin-bottom: var(--sp-4); }
.custom-section label { display: block; font-size: var(--text-sm); color: var(--text-muted); margin-bottom: var(--sp-2); }
.custom-section textarea { width: 100%; font-family: var(--font-mono); font-size: var(--text-xs); resize: vertical; }

/* Mode */
.mode-section { margin-top: var(--sp-4); padding-top: var(--sp-4); border-top: 1px solid var(--border); }
.mode-section h3 { font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); }
.mode-row { display: flex; gap: var(--sp-2); flex-wrap: wrap; align-items: center; }
.mode-chip { padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border); border-radius: var(--radius-md); cursor: pointer; font-size: var(--text-sm); font-weight: 500; transition: all var(--transition); position: relative; }
.mode-chip:hover { border-color: var(--border-hover); }
.mode-chip.selected { border-color: var(--accent); background: rgba(139,92,246,0.1); color: var(--accent); }
.mode-chip-desc { display: none; }
.mode-chip.selected .mode-chip-desc { display: block; font-size: var(--text-xs); font-weight: 400; color: var(--text-muted); margin-top: 2px; }
.mode-chip.sm { font-size: var(--text-xs); padding: var(--sp-1) var(--sp-2); }
.ch-label { font-size: var(--text-xs); color: var(--text-muted); }
.same-check { display: flex; align-items: center; gap: var(--sp-2); margin-top: var(--sp-3); font-size: var(--text-xs); color: var(--text-muted); cursor: pointer; }
.same-check input { accent-color: var(--accent); }

/* Strength */
.strength-section { margin-bottom: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.accent { color: var(--accent); }

.summary-card { background: var(--bg-tertiary); border-radius: var(--radius-md); padding: var(--sp-4); margin-bottom: var(--sp-3); }
.summary-card h3 { font-size: var(--text-sm); margin-bottom: var(--sp-2); color: var(--text-secondary); }
.summary-row { display: flex; justify-content: space-between; font-size: var(--text-sm); padding: var(--sp-1) 0; color: var(--text-secondary); }
.summary-row span:last-child { color: var(--text); font-weight: 500; }
.final-hint { font-size: var(--text-xs); color: var(--text-muted); text-align: center; line-height: 1.8; }

/* Nav */
.wizard-nav { display: flex; align-items: center; margin-top: var(--sp-6); }
.spacer { flex: 1; }
.err { color: var(--danger); font-size: var(--text-sm); margin-top: var(--sp-3); text-align: center; }

/* Done */
.done-card { text-align: center; padding: var(--sp-12) var(--sp-8); }
.done-icon { font-size: 3em; color: var(--success); margin-bottom: var(--sp-3); }
.done-card h2 { font-size: var(--text-2xl); margin-bottom: var(--sp-2); }
.done-card p { color: var(--text-muted); }
</style>
