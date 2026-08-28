<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from '@/i18n'

const { t, locale, setLocale } = useI18n()
const sidebarOpen = ref(true)

interface NavItem {
  path?: string
  key?: string
  label: string
  icon: string
  children?: NavItem[]
}

const navItems = computed<NavItem[]>(() => [
  { path: '/dashboard', label: t('nav.dashboard'), icon: '⚡' },
  { path: '/params', label: t('nav.params'), icon: '🎛' },
  { path: '/strength', label: t('nav.strength'), icon: '🔋' },
  { path: '/overlimit-rules', label: t('nav.overlimit'), icon: '⚡' },
  {
    key: MODES_GROUP_KEY, label: t('nav.modes'), icon: '🎮',
    children: [
      { path: '/mode/shock', label: t('nav.modeShock'), icon: '💥' },
      { path: '/mode/distance', label: t('nav.modeDistance'), icon: '📏' },
      { path: '/mode/touch', label: t('nav.modeTouch'), icon: '🤚' },
      { path: '/mode/combo', label: t('nav.modeCombo'), icon: '🔀' },
    ],
  },
  { path: '/wave-test', label: t('nav.waveTest'), icon: '🧪' },
  { path: '/logs', label: t('nav.logs'), icon: '📋' },
  { path: '/recorder', label: t('nav.recorder'), icon: '🎙' },
  { path: '/chatbox', label: t('nav.chatbox'), icon: '💬' },
  { path: '/settings', label: t('nav.settings'), icon: '⚙' },
])

const expandedGroups = ref<Set<string>>(new Set())

// Auto-expand modes group (use nav key as stable identifier)
const MODES_GROUP_KEY = 'nav.modes'
expandedGroups.value.add(MODES_GROUP_KEY)

function toggleGroup(key: string) {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
}

async function shutdownApp() {
  if (!confirm(t('nav.shutdownConfirm'))) return
  try {
    await fetch('/api/v1/shutdown', { method: 'POST' })
  } catch {}
}
</script>

<template>
  <div class="shell">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ closed: !sidebarOpen }">
      <div class="sidebar-brand">
        <span class="brand-glow">⚡</span>
        <span class="brand-name gradient-text">Shocking</span>
      </div>
      <nav class="nav">
        <template v-for="item in navItems" :key="item.label">
          <!-- Group with children -->
          <template v-if="item.children">
            <button
              class="nav-link nav-group-toggle"
              :class="{ expanded: expandedGroups.has(item.key || item.label) }"
              @click="toggleGroup(item.key || item.label)"
            >
              <span class="nav-ico">{{ item.icon }}</span>
              <span class="nav-txt">{{ item.label }}</span>
              <span class="nav-arrow">{{ expandedGroups.has(item.key || item.label) ? '▾' : '▸' }}</span>
            </button>
            <div class="nav-children" v-show="expandedGroups.has(item.key || item.label)">
              <router-link
                v-for="child in item.children" :key="child.path"
                :to="child.path!"
                class="nav-link nav-child"
                active-class="active"
              >
                <span class="nav-ico">{{ child.icon }}</span>
                <span class="nav-txt">{{ child.label }}</span>
              </router-link>
            </div>
          </template>
          <!-- Normal link -->
          <router-link
            v-else
            :to="item.path!"
            class="nav-link"
            active-class="active"
          >
            <span class="nav-ico">{{ item.icon }}</span>
            <span class="nav-txt">{{ item.label }}</span>
          </router-link>
        </template>
      </nav>
      <div class="lang-switcher">
        <button class="lang-btn" :class="{ active: locale === 'zh' }" @click="setLocale('zh')">中</button>
        <button class="lang-btn" :class="{ active: locale === 'en' }" @click="setLocale('en')">EN</button>
      </div>
      <button class="shutdown-btn" @click="shutdownApp">⏻ {{ t('nav.shutdown') }}</button>
      <button class="toggle-btn" @click="sidebarOpen = !sidebarOpen">
        {{ sidebarOpen ? '‹' : '›' }}
      </button>
    </aside>

    <!-- Main -->
    <main class="main">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 200px 1fr;
  min-height: 100vh;
  transition: grid-template-columns 250ms ease;
}
.shell:has(.sidebar.closed) {
  grid-template-columns: 56px 1fr;
}

/* Sidebar */
.sidebar {
  background: rgba(15, 12, 24, 0.95);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: var(--sp-4) 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
  transition: all 250ms ease;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) var(--sp-6);
}
.brand-glow {
  font-size: 1.4em;
  filter: drop-shadow(0 0 6px rgba(139,92,246,0.5));
}
.brand-name {
  font-size: var(--text-lg);
  font-weight: 800;
  letter-spacing: -0.03em;
}
.sidebar.closed .brand-name { opacity: 0; width: 0; }
.sidebar.closed .nav-txt { opacity: 0; width: 0; }

.nav { flex: 1; padding: 0 var(--sp-2); display: flex; flex-direction: column; gap: 2px; }
.nav-link {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-3);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--transition);
  position: relative;
  overflow: hidden;
}
.nav-link::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--gradient-btn);
  opacity: 0;
  transition: opacity var(--transition);
}
.nav-link:hover {
  color: var(--text);
  text-decoration: none;
}
.nav-link:hover::before { opacity: 0.06; }
.nav-link.active {
  color: var(--text);
  background: rgba(139, 92, 246, 0.12);
  box-shadow: inset 0 0 0 1px rgba(139, 92, 246, 0.2);
}
.nav-link.active::before { opacity: 0.1; }
.nav-ico { font-size: 1.1em; width: 24px; text-align: center; flex-shrink: 0; position: relative; z-index: 1; }
.nav-txt { position: relative; z-index: 1; white-space: nowrap; transition: opacity 200ms; }
.nav-arrow { margin-left: auto; font-size: 0.7em; color: var(--text-muted); position: relative; z-index: 1; transition: opacity 200ms; }
.nav-group-toggle { width: 100%; text-align: left; background: none; border: none; cursor: pointer; font: inherit; }
.nav-children { padding-left: 12px; display: flex; flex-direction: column; gap: 1px; }
.nav-child { font-size: calc(var(--text-sm) - 0.5px); padding: var(--sp-2) var(--sp-3); }
.sidebar.closed .nav-arrow { opacity: 0; width: 0; }

.toggle-btn {
  margin: var(--sp-2) var(--sp-3);
  padding: var(--sp-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-base);
  transition: all var(--transition);
}
.toggle-btn:hover { color: var(--text); border-color: var(--border-hover); }

.lang-switcher { display: flex; gap: 4px; padding: var(--sp-2) var(--sp-3); justify-content: center; }
.lang-btn { padding: 2px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 11px; font-weight: 600; transition: all var(--transition); }
.lang-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(139,92,246,0.1); }
.lang-btn:hover { border-color: var(--border-hover); color: var(--text); }
.shutdown-btn { margin: var(--sp-2) var(--sp-3); padding: var(--sp-2); width: calc(100% - 2 * var(--sp-3)); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; font-size: var(--text-xs); transition: all var(--transition); }
.shutdown-btn:hover { color: var(--danger); border-color: var(--danger); background: rgba(239,68,68,0.06); }

/* Main content */
.main {
  padding: var(--sp-8);
  max-width: 1100px;
  width: 100%;
}

/* Page transitions */
.page-enter-active { transition: opacity 150ms ease, transform 150ms ease; }
.page-leave-active { transition: opacity 100ms ease; }
.page-enter-from { opacity: 0; transform: translateY(8px); }
.page-leave-to { opacity: 0; }

/* Mobile */
@media (max-width: 768px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar {
    position: fixed; left: 0; top: 0; z-index: 100;
    width: 200px;
    transform: translateX(-100%);
    box-shadow: 4px 0 32px rgba(0,0,0,0.7);
  }
  .sidebar:not(.closed) { transform: translateX(0); }
  .main { padding: var(--sp-4); }
}
</style>
