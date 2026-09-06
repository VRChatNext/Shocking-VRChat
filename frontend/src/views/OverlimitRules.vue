<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, apiPost } from '@/api'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface Rule {
  name: string
  channel: 'a' | 'b' | 'both'
  limit_value: number
  condition: {
    param: string
    operator: string
    value: number
  }
  enabled: boolean
}

const rules = ref<Rule[]>([])
const effective = ref<{ A: number; B: number }>({ A: 0, B: 0 })
const msg = ref('')
const msgType = ref<'ok' | 'err'>('ok')

const operators = ['==', '!=', '>', '<', '>=', '<=']

async function load() {
  const data = await api('/api/v1/overlimit_rules')
  rules.value = data.rules || []
  effective.value = data.effective || { A: 0, B: 0 }
}

function addRule() {
  rules.value.push({
    name: `${t('overlimit.rulePrefix')} ${rules.value.length + 1}`,
    channel: 'both',
    limit_value: 30,
    condition: {
      param: '/avatar/parameters/',
      operator: '==',
      value: 1,
    },
    enabled: true,
  })
}

async function save() {
  const data = await apiPost('/api/v1/overlimit_rules', { rules: rules.value })
  if (data.success) {
    msg.value = t('overlimit.savedSuccess')
    msgType.value = 'ok'
    rules.value = data.rules
  } else {
    msg.value = t('overlimit.saveFailed')
    msgType.value = 'err'
  }
  setTimeout(() => msg.value = '', 3000)
}

async function removeRule(index: number) {
  rules.value.splice(index, 1)
  await save()
}

function moveUp(index: number) {
  if (index <= 0) return
  const tmp = rules.value[index]
  rules.value[index] = rules.value[index - 1]
  rules.value[index - 1] = tmp
}

function moveDown(index: number) {
  if (index >= rules.value.length - 1) return
  const tmp = rules.value[index]
  rules.value[index] = rules.value[index + 1]
  rules.value[index + 1] = tmp
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="gradient-text page-title">{{ t('overlimit.title') }}</h1>
    <p class="page-desc">{{ t('overlimit.desc') }}</p>

    <div class="status-bar">
      <span class="status-label">{{ t('overlimit.currentEffective') }}</span>
      <span class="status-chip" :class="{ active: effective.A > 0 }">A: {{ effective.A > 0 ? effective.A : '—' }}</span>
      <span class="status-chip" :class="{ active: effective.B > 0 }">B: {{ effective.B > 0 ? effective.B : '—' }}</span>
      <button class="btn btn-ghost btn-sm" @click="load" :title="t('overlimit.refreshStatus')">↻</button>
    </div>

    <div class="rules-list">
      <div v-for="(rule, i) in rules" :key="i" class="rule-card card" :class="{ disabled: !rule.enabled }">
        <div class="rule-header">
          <input type="text" v-model="rule.name" class="rule-name" :placeholder="t('overlimit.ruleName')">
          <label class="toggle">
            <input type="checkbox" v-model="rule.enabled">
            <span class="toggle-label">{{ rule.enabled ? t('common.enable') : t('common.disable') }}</span>
          </label>
          <div class="rule-actions">
            <button class="btn-icon" @click="moveUp(i)" :disabled="i === 0" :title="t('overlimit.moveUp')">↑</button>
            <button class="btn-icon" @click="moveDown(i)" :disabled="i === rules.length - 1" :title="t('overlimit.moveDown')">↓</button>
            <button class="btn-icon danger" @click="removeRule(i)" :title="t('common.delete')">✕</button>
          </div>
        </div>

        <div class="rule-body">
          <div class="condition-row">
            <span class="cond-label">{{ t('overlimit.when') }}</span>
            <input type="text" v-model="rule.condition.param" class="cond-param" placeholder="/avatar/parameters/...">
            <select v-model="rule.condition.operator" class="cond-op">
              <option v-for="op in operators" :key="op" :value="op">{{ op }}</option>
            </select>
            <input type="number" v-model.number="rule.condition.value" class="cond-value" step="0.01">
          </div>
          <div class="effect-row">
            <span class="cond-label">{{ t('overlimit.then') }}</span>
            <select v-model="rule.channel" class="effect-channel">
              <option value="a">{{ t('overlimit.channelAOption') }}</option>
              <option value="b">{{ t('overlimit.channelBOption') }}</option>
              <option value="both">{{ t('overlimit.channelBothOption') }}</option>
            </select>
            <span class="effect-text">{{ t('overlimit.limitBoostTo') }}</span>
            <input type="number" v-model.number="rule.limit_value" min="0" max="200" class="effect-value">
          </div>
        </div>
      </div>

      <div v-if="rules.length === 0" class="empty-state">
        <p>{{ t('overlimit.emptyState') }}</p>
      </div>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" @click="addRule">{{ t('overlimit.addRule') }}</button>
      <button class="btn btn-primary" @click="save">{{ t('overlimit.saveAll') }}</button>
      <button class="btn btn-ghost" @click="load">{{ t('overlimit.reloadAll') }}</button>
      <span class="msg" :class="{ ok: msgType === 'ok', err: msgType === 'err' }">{{ msg }}</span>
    </div>

    <div class="info-card card">
      <h3>{{ t('overlimit.infoTitle') }}</h3>
      <ul>
        <li><strong>{{ t('overlimit.infoCondition') }}</strong>：{{ t('overlimit.infoConditionDesc') }}</li>
        <li><strong>{{ t('overlimit.infoEffect') }}</strong>：{{ t('overlimit.infoEffectDesc') }}</li>
        <li><strong>{{ t('overlimit.infoMultiRule') }}</strong>：{{ t('overlimit.infoMultiRuleDesc') }}</li>
        <li><strong>{{ t('overlimit.infoPriority') }}</strong>：{{ t('overlimit.infoPriorityDesc') }}</li>
        <li><strong>{{ t('overlimit.infoRecover') }}</strong>：{{ t('overlimit.infoRecoverDesc') }}</li>
      </ul>
      <h3 style="margin-top:var(--sp-3)">{{ t('overlimit.infoExampleTitle') }}</h3>
      <ul>
        <li><code>/avatar/parameters/pcs/smash-intense == 1</code> → {{ t('overlimit.infoExample1') }}</li>
        <li><code>/avatar/parameters/pcs/contact/enterPass >= 0.9</code> → {{ t('overlimit.infoExample2') }}</li>
        <li><code>/avatar/parameters/Shock/OverrideMax == 1</code> → {{ t('overlimit.infoExample3') }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.status-bar { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-4); padding: var(--sp-3) var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.status-label { font-size: var(--text-sm); color: var(--text-muted); }
.status-chip { font-size: var(--text-sm); padding: var(--sp-1) var(--sp-3); border-radius: var(--radius-full); background: var(--bg-tertiary); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.status-chip.active { background: rgba(139,92,246,0.15); color: var(--accent); border: 1px solid rgba(139,92,246,0.3); }
.rules-list { display: flex; flex-direction: column; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.rule-card { padding: var(--sp-4); transition: opacity 0.2s; }
.rule-card.disabled { opacity: 0.5; }
.rule-header { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-3); }
.rule-name { flex: 1; font-weight: 600; font-size: var(--text-sm); }
.toggle { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--text-xs); color: var(--text-muted); cursor: pointer; white-space: nowrap; }
.toggle input[type="checkbox"] { accent-color: var(--accent); }
.toggle-label { user-select: none; }
.rule-actions { display: flex; gap: var(--sp-1); }
.btn-icon { background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-muted); font-size: var(--text-sm); transition: all 0.15s; }
.btn-icon:hover { border-color: var(--border-hover); color: var(--text); }
.btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-icon.danger:hover { border-color: var(--danger); color: var(--danger); }
.rule-body { display: flex; flex-direction: column; gap: var(--sp-2); }
.condition-row, .effect-row { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.cond-label { font-size: var(--text-sm); color: var(--accent); font-weight: 600; min-width: 24px; }
.cond-param { flex: 1; min-width: 200px; font-size: var(--text-sm); }
.cond-op { width: 64px; text-align: center; font-size: var(--text-sm); }
.cond-value { width: 80px; text-align: center; font-size: var(--text-sm); }
.effect-channel { width: 100px; font-size: var(--text-sm); }
.effect-text { font-size: var(--text-sm); color: var(--text-secondary); }
.effect-value { width: 80px; text-align: center; font-size: var(--text-sm); font-weight: 600; }
.empty-state { text-align: center; padding: var(--sp-6); color: var(--text-muted); font-size: var(--text-sm); }
.save-bar { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-5); padding: var(--sp-4); background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.msg { font-size: var(--text-sm); color: var(--text-muted); }
.msg.ok { color: var(--success); }
.msg.err { color: var(--danger); }
.info-card { font-size: var(--text-sm); color: var(--text-secondary); }
.info-card h3 { font-size: var(--text-base); margin-bottom: var(--sp-2); color: var(--text); }
.info-card ul { padding-left: var(--sp-4); }
.info-card li { margin-bottom: var(--sp-2); line-height: 1.6; }
.info-card code { background: var(--bg-tertiary); padding: 2px 6px; border-radius: var(--radius-sm); font-size: var(--text-xs); }
.info-card em { color: var(--accent); font-style: normal; font-weight: 500; }
</style>
