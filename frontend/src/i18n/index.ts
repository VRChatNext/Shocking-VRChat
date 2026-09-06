import { ref } from 'vue'
import zh from './zh'
import en from './en'

export type Locale = 'zh' | 'en'
type Messages = typeof zh

const messages: Record<Locale, Messages> = { zh, en }

const currentLocale = ref<Locale>((localStorage.getItem('locale') as Locale) || 'zh')

export function useI18n() {
  function t(key: string, params?: Record<string, string | number>): string {
    const keys = key.split('.')
    let val: any = messages[currentLocale.value]
    for (const k of keys) {
      if (val === undefined || val === null) return key
      val = val[k]
    }
    if (typeof val !== 'string') return key
    if (params) {
      return val.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? ''))
    }
    return val
  }

  function setLocale(locale: Locale) {
    currentLocale.value = locale
    localStorage.setItem('locale', locale)
  }

  return {
    t,
    locale: currentLocale,
    setLocale,
    locales: ['zh', 'en'] as Locale[],
  }
}
