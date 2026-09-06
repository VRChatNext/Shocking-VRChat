import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './assets/global.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/Dashboard.vue') },
    { path: '/mode/shock', component: () => import('./views/ModeShock.vue') },
    { path: '/mode/distance', component: () => import('./views/ModeDistance.vue') },
    { path: '/mode/touch', component: () => import('./views/ModeTouch.vue') },
    { path: '/mode/combo', component: () => import('./views/ComboEditor.vue') },
    { path: '/params', component: () => import('./views/ParamMap.vue') },
    { path: '/recorder', component: () => import('./views/Recorder.vue') },
    { path: '/setup', component: () => import('./views/SetupWizard.vue') },
    { path: '/settings', component: () => import('./views/Settings.vue') },
    { path: '/strength', component: () => import('./views/StrengthLimit.vue') },
    { path: '/overlimit-rules', component: () => import('./views/OverlimitRules.vue') },
    { path: '/wave-test', component: () => import('./views/WaveTest.vue') },
    { path: '/logs', component: () => import('./views/Logs.vue') },
    { path: '/chatbox', component: () => import('./views/Chatbox.vue') },
    // Legacy redirects
    { path: '/curve', redirect: '/mode/distance' },
    { path: '/combo', redirect: '/mode/combo' },
    { path: '/mode/curve', redirect: '/mode/distance' },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
