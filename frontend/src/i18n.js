import { ref } from 'vue'
import { en } from './locales/en.js'
import { translateApi } from './locales/en.api.js'

/**
 * Mehrsprachigkeit ohne Fremdbibliothek (Muster wie in OpenPlan): Der deutsche Text ist zugleich der Schlüssel.
 * `t('Abmelden')` liefert bei Sprache „en“ den Eintrag aus locales/en.js; fehlt er, bleibt der deutsche Text stehen –
 * so lässt sich Ansicht für Ansicht umstellen. Platzhalter: `t('{n} Geräte', { n: 3 })`.
 * Die Sprache gehört zu den persönlichen Einstellungen (Profil, gilt auf allen Geräten); vor der Anmeldung merkt sich der Browser die Wahl.
 */
const LS_LANG = 'opp_lang'
const read = () => { try { return localStorage.getItem(LS_LANG) } catch { return null } }
const asLang = v => (v === 'en' ? 'en' : 'de')

export const lang = ref(asLang(read()))

export function t(s, params) {
  let out = (lang.value === 'en' && en[s]) || s
  if (params) for (const [k, v] of Object.entries(params)) out = out.split(`{${k}}`).join(String(v ?? ''))
  return out
}

/** Server-Meldung in der eingestellten Sprache (die API antwortet deutsch). */
export const tApi = msg => (lang.value === 'en' && typeof msg === 'string' ? translateApi(msg) : msg)

/** Locale für Datums- und Zahlenformate */
export const locale = () => (lang.value === 'en' ? 'en-GB' : 'de-DE')

export function setLang(l) {
  lang.value = asLang(l)
  try { localStorage.setItem(LS_LANG, lang.value) } catch { /* privat */ }
  document.documentElement.lang = lang.value
}

setLang(lang.value)
