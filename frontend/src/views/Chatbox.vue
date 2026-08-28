<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const enabled = ref(false)
const targetHost = ref('127.0.0.1')
const targetPort = ref(9000)
const intervalSeconds = ref(3.0)
const sendNotification = ref(true)
const triggerSfx = ref(false)
const messageTemplate = ref('Shocking VRChat ⚡ A:{strength_a} B:{strength_b}')

const msg = ref('')
const msgErr = ref(false)
const testMsg = ref('')
const testMsgErr = ref(false)

const availableVars = [
  { key: '{strength_a}', desc: 'chatbox.varStrengthA' },
  { key: '{strength_b}', desc: 'chatbox.varStrengthB' },
  { key: '{mode_a}', desc: 'chatbox.varModeA' },
  { key: '{mode_b}', desc: 'chatbox.varModeB' },
  { key: '{device_count}', desc: 'chatbox.varDeviceCount' },
  { key: '{app_version}', desc: 'chatbox.varAppVersion' },
]

const previewMessage = computed(() => {
  let msg = messageTemplate.value
  const demoVars: Record<string, string> = {
    strength_a: '35',
    strength_b: '20',
    strength_limit_a: '100',
    strength_limit_b: '100',
    mode_a: 'distance',
    mode_b: 'shock',
    device_count: '1',
    app_version: '0.6.3',
  }
  try {
    for (const [k, v] of Object.entries(demoVars)) {
      msg = msg.split(`{${k}}`).join(v)
    }
  } catch {}
  return msg
})

async function load() {
  const data = await api('/api/v1/chatbox')
  enabled.value = data.enabled ?? false
  targetHost.value = data.target_host ?? '127.0.0.1'
  targetPort.value = data.target_port ?? 9000
  intervalSeconds.value = data.interval_seconds ?? 3.0
  sendNotification.value = data.send_notification ?? true
  triggerSfx.value = data.trigger_sfx ?? false
  messageTemplate.value = data.message_template ?? 'Shocking VRChat ⚡ A:{strength_a} B:{strength_b}'
}

async function save() {
  try {
    const data = await apiPost('/api/v1/chatbox', {
      enabled: enabled.value,
      target_host: targetHost.value,
      target_port: targetPort.value,
      interval_seconds: intervalSeconds.value,
      send_notification: sendNotification.value,
      trigger_sfx: triggerSfx.value,
      message_template: messageTemplate.value,
    })
    if (data.success) {
      msg.value = t('common.saved')
      msgErr.value = false
    } else {
      msg.value = t('common.saveFailed')
      msgErr.value = true
    }
  } catch {
    msg.value = t('common.saveFailed')
    msgErr.value = true
  }
  setTimeout(() => msg.value = '', 3000)
}

async function sendTest() {
  try {
    const data = await apiPost('/api/v1/chatbox/test', {
      message: previewMessage.value,
      target_host: targetHost.value,
      target_port: targetPort.value,
    })
    if (data.success) {
      testMsg.value = t('chatbox.testSent')
      testMsgErr.value = false
    } else {
      testMsg.value = data.error || t('chatbox.testFailed')
      testMsgErr.value = true
    }
  } catch {
    testMsg.value = t('chatbox.testFailed')
    testMsgErr.value = true
  }
  setTimeout(() => testMsg.value = '', 3000)
}

function insertVar(varKey: string) {
  messageTemplate.value += varKey
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">{{ t('chatbox.title') }}</h2>
    <p class="page-desc">{{ t('chatbox.desc') }}</p>

    <!-- Enable toggle -->
    <div class="card">
      <div class="card-title">{{ t('chatbox.enableTitle') }}</div>
      <div class="form-group" style="display: flex; align-items: center; gap: 12px;">
        <label class="toggle">
          <input type="checkbox" v-model="enabled" />
          <span class="toggle-slider"></span>
        </label>
        <span>{{ enabled ? t('common.enabled') : t('common.disabled') }}</span>
      </div>
    </div>

    <!-- Message Template -->
    <div class="card">
      <div class="card-title">{{ t('chatbox.templateTitle') }}</div>
      <p class="card-desc">{{ t('chatbox.templateDesc') }}</p>
      <div class="form-group">
        <label class="form-label">{{ t('chatbox.templateLabel') }}</label>
        <textarea
          class="form-input"
          v-model="messageTemplate"
          rows="3"
          style="resize: vertical; font-family: monospace;"
        ></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('chatbox.availableVars') }}</label>
        <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px;">
          <button
            v-for="v in availableVars"
            :key="v.key"
            class="btn"
            style="font-size: 12px; padding: 2px 8px;"
            @click="insertVar(v.key)"
            :title="t(v.desc)"
          >
            {{ v.key }}
          </button>
        </div>
        <p class="form-hint">{{ t('chatbox.varClickHint') }}</p>
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('chatbox.preview') }}</label>
        <div class="preview-box">{{ previewMessage }}</div>
      </div>
    </div>

    <!-- OSC Settings -->
    <div class="card">
      <div class="card-title">{{ t('chatbox.oscTitle') }}</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">{{ t('chatbox.targetHost') }}</label>
          <input class="form-input" v-model="targetHost" style="width: 160px;" />
          <p class="form-hint">{{ t('chatbox.targetHostHint') }}</p>
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('chatbox.targetPort') }}</label>
          <input class="form-input" type="number" v-model.number="targetPort" style="width: 100px;" />
          <p class="form-hint">{{ t('chatbox.targetPortHint') }}</p>
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('chatbox.interval') }}</label>
          <input class="form-input" type="number" v-model.number="intervalSeconds" step="0.5" min="0.5" style="width: 100px;" />
          <p class="form-hint">{{ t('chatbox.intervalHint') }}</p>
        </div>
      </div>
      <div class="form-group" style="display: flex; align-items: center; gap: 12px; margin-top: 8px;">
        <label class="toggle">
          <input type="checkbox" v-model="sendNotification" />
          <span class="toggle-slider"></span>
        </label>
        <span>{{ t('chatbox.sendNotification') }}</span>
      </div>
      <p class="form-hint">{{ t('chatbox.sendNotificationHint') }}</p>
      <div class="form-group" style="display: flex; align-items: center; gap: 12px; margin-top: 8px;">
        <label class="toggle">
          <input type="checkbox" v-model="triggerSfx" />
          <span class="toggle-slider"></span>
        </label>
        <span>{{ t('chatbox.triggerSfx') }}</span>
      </div>
    </div>

    <!-- Actions -->
    <div class="card">
      <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
        <button class="btn btn-primary" @click="save">{{ t('chatbox.save') }}</button>
        <button class="btn" @click="sendTest">{{ t('chatbox.testSend') }}</button>
        <button class="btn" @click="load">{{ t('common.reload') }}</button>
      </div>
      <p v-if="msg" :class="msgErr ? 'msg-err' : 'msg-ok'" style="margin-top: 8px;">{{ msg }}</p>
      <p v-if="testMsg" :class="testMsgErr ? 'msg-err' : 'msg-ok'" style="margin-top: 8px;">{{ testMsg }}</p>
    </div>

    <!-- Info -->
    <div class="card">
      <div class="card-title">{{ t('chatbox.infoTitle') }}</div>
      <ul class="info-list">
        <li>{{ t('chatbox.info1') }}</li>
        <li>{{ t('chatbox.info2') }}</li>
        <li>{{ t('chatbox.info3') }}</li>
        <li>{{ t('chatbox.info4') }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.preview-box {
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: var(--radius-md);
  padding: var(--sp-3) var(--sp-4);
  font-family: monospace;
  font-size: var(--text-sm);
  color: var(--text);
  word-break: break-all;
  min-height: 24px;
}
.form-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.info-list {
  margin: 0;
  padding-left: 20px;
  color: var(--text-muted);
  font-size: var(--text-sm);
  line-height: 1.8;
}
</style>
