<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const oscPort = ref(9001)
const oscHost = ref('127.0.0.1')
const wsPort = ref(28846)
const v4Enabled = ref(true)
const webPort = ref(8800)
const webHost = ref('127.0.0.1')
const githubMirror = ref('')
const logLevel = ref('INFO')
const msg = ref('')
const msgErr = ref(false)
const importMsg = ref('')
const importErr = ref(false)

async function load() {
  const data = await api('/api/v1/config')
  const adv = data.advanced || {}
  oscPort.value = adv.osc?.listen_port || 9001
  oscHost.value = adv.osc?.listen_host || '127.0.0.1'
  wsPort.value = adv.ws?.listen_port || 28846
  v4Enabled.value = adv.ws?.v4_enabled !== false
  webPort.value = adv.web_server?.listen_port || 8800
  webHost.value = adv.web_server?.listen_host || '127.0.0.1'
  logLevel.value = adv.log_level || 'INFO'
  githubMirror.value = adv.general?.github_mirror || ''
}

async function save() {
  const data = await apiPost('/api/v1/settings', {
    osc: { listen_port: oscPort.value, listen_host: oscHost.value },
    ws: { listen_port: wsPort.value, v4_enabled: v4Enabled.value },
    web_server: { listen_port: webPort.value, listen_host: webHost.value },
    log_level: logLevel.value,
    github_mirror: githubMirror.value,
  })
  if (data.success) {
    if (data.restart_needed?.length) {
      msg.value = t('settings.savedRestarting')
      msgErr.value = false
      // If web port changed, redirect to new port after delay
      const newPort = webPort.value
      const currentPort = window.location.port
      if (String(newPort) !== currentPort) {
        setTimeout(() => {
          window.location.href = `http://${window.location.hostname}:${newPort}/settings`
        }, 3000)
      } else {
        setTimeout(() => window.location.reload(), 3000)
      }
    } else {
      msg.value = data.message; msgErr.value = false
    }
  } else { msg.value = data.message || t('common.saveFailed'); msgErr.value = true }
  setTimeout(() => msg.value = '', 8000)
}

function exportConfig() {
  window.open('/api/v1/config/export', '_blank')
}

const importFileRef = ref<HTMLInputElement | null>(null)

function triggerImport() {
  importFileRef.value?.click()
}

async function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch('/api/v1/config/import', { method: 'POST', body: form })
    const data = await res.json()
    if (data.success) {
      importMsg.value = '✓ ' + data.message
      importErr.value = false
      setTimeout(() => window.location.reload(), 2000)
    } else {
      importMsg.value = '✗ ' + (data.detail || t('settings.importFailed'))
      importErr.value = true
    }
  } catch (err) {
    importMsg.value = t('settings.importFailed') + ': ' + err
    importErr.value = true
  }
  if (importFileRef.value) importFileRef.value.value = ''
  setTimeout(() => importMsg.value = '', 8000)
}

onMounted(load)

// --- Update check ---
const updateInfo = ref<any>(null)
const updateChecking = ref(false)
const updateApplying = ref(false)
const updateMsg = ref('')
const updateErr = ref(false)

async function checkUpdate() {
  updateChecking.value = true
  updateMsg.value = ''
  try {
    const data = await api('/api/v1/update/check')
    updateInfo.value = data
    if (data.error) {
      updateMsg.value = data.error
      updateErr.value = true
    }
  } catch (e) {
    updateMsg.value = t('settings.updateFailed')
    updateErr.value = true
  }
  updateChecking.value = false
}

async function applyUpdate() {
  if (!confirm(t('settings.updateConfirm'))) return
  updateApplying.value = true
  updateMsg.value = t('settings.updateDownloading')
  updateErr.value = false
  try {
    const res = await fetch('/api/v1/update/apply', { method: 'POST' })
    const data = await res.json()
    if (data.success) {
      updateMsg.value = '✓ ' + data.message + ' ' + t('settings.updateDone')
      updateErr.value = false
      // Poll until new server is ready, then reload
      pollForRestart()
    } else {
      updateMsg.value = '✗ ' + (data.detail || data.message || t('settings.updateFailed'))
      updateErr.value = true
      updateApplying.value = false
    }
  } catch (e) {
    updateMsg.value = t('settings.updateFailed') + ': ' + e
    updateErr.value = true
    updateApplying.value = false
  }
}

function pollForRestart() {
  let attempts = 0
  const maxAttempts = 15 // 15 × 2s = 30s max
  const interval = setInterval(async () => {
    attempts++
    try {
      const res = await fetch('/api/v1/status', { signal: AbortSignal.timeout(3000) })
      if (res.ok) {
        clearInterval(interval)
        window.location.reload()
      }
    } catch {
      // Server not ready yet
    }
    if (attempts >= maxAttempts) {
      clearInterval(interval)
      updateMsg.value = t('settings.updateDone')
      updateApplying.value = false
    }
  }, 2000)
}

onMounted(() => { checkUpdate() })
</script>

<template>
  <div>
    <h1 class="gradient-text page-title">{{ t('settings.title') }}</h1>
    <p class="page-desc">{{ t('settings.desc') }}</p>

    <div class="settings-grid">
      <section class="card">
        <h2>{{ t('settings.oscTitle') }}</h2>
        <div class="field">
          <label>{{ t('settings.oscPort') }}</label>
          <input type="number" v-model.number="oscPort" min="1024" max="65535">
          <p class="hint">{{ t('settings.oscPortHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('settings.oscHost') }}</label>
          <input type="text" v-model="oscHost">
          <p class="hint">{{ t('settings.oscHostHint') }}</p>
        </div>
      </section>

      <section class="card">
        <h2>{{ t('settings.wsTitle') }}</h2>
        <div class="field">
          <label>{{ t('settings.wsPort') }}</label>
          <input type="number" v-model.number="wsPort" min="1024" max="65535">
          <p class="hint">{{ t('settings.wsPortHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('settings.v4Title') }}</label>
          <label class="toggle-row">
            <input type="checkbox" v-model="v4Enabled">
            <span>{{ v4Enabled ? t('common.enabled') : t('common.disabled') }}</span>
          </label>
          <p class="hint">{{ t('settings.v4Hint') }}</p>
        </div>
      </section>

      <section class="card">
        <h2>{{ t('settings.webTitle') }}</h2>
        <div class="field">
          <label>{{ t('settings.webPort') }}</label>
          <input type="number" v-model.number="webPort" min="1024" max="65535">
          <p class="hint">{{ t('settings.webPortHint') }}</p>
        </div>
        <div class="field">
          <label>{{ t('settings.webHost') }}</label>
          <input type="text" v-model="webHost">
          <p class="hint">{{ t('settings.webHostHint') }}</p>
        </div>
      </section>

      <section class="card">
        <h2>{{ t('settings.logTitle') }}</h2>
        <div class="field">
          <label>{{ t('settings.logLevel') }}</label>
          <select v-model="logLevel">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <p class="hint">{{ t('settings.logLevelHint') }}</p>
        </div>
      </section>

      <section class="card">
        <h2>{{ t('settings.githubTitle') }}</h2>
        <div class="field">
          <label>{{ t('settings.githubMirror') }}</label>
          <input type="text" v-model="githubMirror" :placeholder="t('settings.githubMirrorPlaceholder')">
          <p class="hint">{{ t('settings.githubMirrorHint') }}</p>
          <div class="mirror-presets">
            <button class="preset-tag" @click="githubMirror = ''">{{ t('settings.githubDirect') }}</button>
            <button class="preset-tag" @click="githubMirror = 'https://mirror.ghproxy.com'">ghproxy</button>
            <button class="preset-tag" @click="githubMirror = 'https://ghfast.top'">ghfast</button>
            <button class="preset-tag" @click="githubMirror = 'https://gh-proxy.com'">gh-proxy</button>
          </div>
        </div>
      </section>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="save">{{ t('settings.saveSettings') }}</button>
      <button class="btn btn-ghost" @click="load">{{ t('settings.reloadSettings') }}</button>
      <span class="msg" :class="{ err: msgErr }">{{ msg }}</span>
    </div>

    <section class="card" style="margin-top:var(--sp-4)">
      <h2>{{ t('settings.configTitle') }}</h2>
      <p class="hint" style="margin-bottom:var(--sp-3)">{{ t('settings.configDesc') }}</p>
      <div class="ie-bar">
        <button class="btn btn-ghost" @click="exportConfig">{{ t('settings.exportConfig') }}</button>
        <button class="btn btn-ghost" @click="triggerImport">{{ t('settings.importConfig') }}</button>
        <input ref="importFileRef" type="file" accept=".json" hidden @change="handleImport">
        <span class="msg" :class="{ err: importErr }">{{ importMsg }}</span>
      </div>
    </section>

    <section class="card" style="margin-top:var(--sp-4)">
      <h2>{{ t('settings.updateTitle') }}</h2>
      <div class="update-info">
        <div class="update-row">
          <span class="update-label">{{ t('settings.updateCurrent') }}:</span>
          <span class="update-value">{{ updateInfo?.current || '...' }}</span>
        </div>
        <div class="update-row">
          <span class="update-label">{{ t('settings.updateLatest') }}:</span>
          <span class="update-value" :class="{ 'has-update': updateInfo?.update_available }">
            {{ updateInfo?.latest || (updateChecking ? t('settings.checking') : t('settings.unknown')) }}
            <span v-if="updateInfo?.update_available" class="update-badge">{{ t('settings.updateAvailable') }}</span>
          </span>
        </div>
        <div v-if="updateInfo?.release_name && updateInfo?.update_available" class="update-row">
          <span class="update-label">{{ t('settings.updateNotes') }}:</span>
          <span class="update-value update-notes">{{ updateInfo.release_name }}</span>
        </div>
      </div>
      <div class="ie-bar" style="margin-top:var(--sp-3)">
        <button class="btn btn-ghost" @click="checkUpdate" :disabled="updateChecking">{{ t('settings.updateCheck') }}</button>
        <button
          v-if="updateInfo?.update_available"
          class="btn btn-primary"
          @click="applyUpdate"
          :disabled="updateApplying"
        >{{ updateApplying ? t('settings.updateApplying') : t('settings.updateApply') }}</button>
        <span class="msg" :class="{ err: updateErr }">{{ updateMsg }}</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page-desc { color: var(--text-muted); font-size: var(--text-sm); margin-bottom: var(--sp-6); }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.field { margin-bottom: var(--sp-4); }
.field:last-child { margin-bottom: 0; }
.field label { display: block; font-size: var(--text-sm); color: var(--text-secondary); margin-bottom: var(--sp-2); font-weight: 500; }
.toggle-row { display: flex; align-items: center; gap: var(--sp-2); cursor: pointer; font-size: var(--text-sm); }
.toggle-row input[type="checkbox"] { width: auto; margin: 0; cursor: pointer; }
.field input, .field select { width: 100%; }
.hint { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--sp-1); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-top: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.ie-bar { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.msg { font-size: var(--text-sm); color: var(--success); }
.msg.err { color: var(--danger); }
.update-info { display: flex; flex-direction: column; gap: var(--sp-2); }
.update-row { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--text-sm); }
.update-label { color: var(--text-muted); min-width: 80px; }
.update-value { color: var(--text-secondary); }
.update-value.has-update { color: var(--accent); font-weight: 600; }
.update-badge { display: inline-block; margin-left: var(--sp-2); padding: 1px 8px; border-radius: 99px; background: rgba(139,92,246,0.15); color: var(--accent); font-size: var(--text-xs); font-weight: 600; }
.update-notes { font-size: var(--text-xs); color: var(--text-muted); max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mirror-presets { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); flex-wrap: wrap; }
.preset-tag { padding: 2px 10px; border: 1px solid var(--border); border-radius: 99px; background: transparent; color: var(--text-muted); font-size: var(--text-xs); cursor: pointer; transition: all var(--transition); }
.preset-tag:hover { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.06); }
@media (max-width: 768px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
