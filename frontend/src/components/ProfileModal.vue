<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4" @click.self="$emit('close')">
    <div class="w-full max-w-lg max-h-[92vh] overflow-y-auto bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden"
         role="dialog" aria-modal="true" aria-label="Mein Profil">

      <div class="flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-slate-700">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Mein Profil</h2>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Schließen (Esc)">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="px-5 py-4 space-y-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-ks-600 text-white flex items-center justify-center text-base font-semibold flex-shrink-0">
            {{ (me.username || '?')[0].toUpperCase() }}
          </div>
          <div class="min-w-0">
            <div class="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
              {{ me.username }}<span v-if="me.full_name" class="text-slate-400 font-normal"> · {{ me.full_name }}</span>
            </div>
            <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span v-for="r in me.roles || []" :key="r" class="text-[11px] px-2 py-0.5 rounded-full"
                :class="r === 'admin' ? 'bg-ks-100 text-ks-700 dark:bg-ks-900/40 dark:text-ks-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'">{{ roleLabel(r) }}</span>
              <span v-if="me.email" class="text-xs text-slate-400 truncate">{{ me.email }}</span>
            </div>
          </div>
        </div>

        <hr class="border-slate-100 dark:border-slate-700" />

        <div v-if="notify" class="space-y-2">
          <h3 class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">E-Mail-Benachrichtigungen</h3>
          <label v-for="[k, l] in notifyShown" :key="k" class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 cursor-pointer">
            <input type="checkbox" :checked="notify[k]" @change="setNotify(k, $event.target.checked)" /> {{ l }}</label>
          <p class="text-xs text-slate-400">{{ me.email ? `an ${me.email}` : 'Keine E-Mail-Adresse hinterlegt – es kommen keine Mails.' }}
            Ob überhaupt Mails verschickt werden, legt die Verwaltung fest.</p>
          <p v-if="notifyMsg" class="text-xs text-green-600 dark:text-green-400">{{ notifyMsg }}</p>
        </div>

        <hr v-if="notify" class="border-slate-100 dark:border-slate-700" />

        <div v-if="me.id" class="space-y-2">
          <h3 class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Abwesenheit und Vertretung</h3>
          <p v-if="represents.length" class="text-xs text-sky-700 dark:text-sky-300">Du vertrittst gerade: {{ represents.map(u => u.full_name || u.username).join(', ') }}</p>
          <AbsenceEditor @changed="refreshMe" />
        </div>

        <hr v-if="me.id" class="border-slate-100 dark:border-slate-700" />

        <div v-if="prefs" class="space-y-2">
          <h3 class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Persönliche Einstellungen</h3>
          <div class="grid grid-cols-2 gap-2">
            <div><label :class="lbl">Standard-Standort</label>
              <select v-model="prefs.default_site_id" :class="inp" @change="savePrefs"><option :value="null">keiner (alle)</option>
                <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
            <div><label :class="lbl">Startseite</label>
              <select v-model="prefs.start_page" :class="inp" @change="savePrefs"><option v-for="[k, l] in START_PAGES" :key="k" :value="k">{{ l }}</option></select></div>
          </div>
          <p class="text-xs text-slate-400">Der Standard-Standort belegt die Filter in Kapazität, Soll/Ist, Zeitreise und VLANs vor. Gilt auf allen Geräten.</p>
          <div v-if="sessions" class="flex items-center justify-between gap-2 text-sm pt-1">
            <span class="text-slate-600 dark:text-slate-300">{{ sessions.active }} aktive Anmeldung(en)</span>
            <button type="button" class="text-xs text-red-600 hover:underline dark:text-red-400" :disabled="sessions.active < 2" @click="logoutOthers">Alle anderen abmelden</button>
          </div>
          <p v-if="prefsMsg" class="text-xs text-green-600 dark:text-green-400">{{ prefsMsg }}</p>
        </div>

        <hr v-if="prefs" class="border-slate-100 dark:border-slate-700" />

        <div class="space-y-3">
          <h3 class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide flex items-center gap-1.5">
            Passwort ändern
            <HelpHint text="Beim Ändern werden alle anderen Sitzungen dieses Kontos beendet, du bleibst hier angemeldet." />
          </h3>

          <p v-if="msg" class="text-sm rounded-lg px-3 py-2"
             :class="msgErr ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300' : 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'">{{ msg }}</p>

          <div>
            <label :class="lbl">Aktuelles Passwort</label>
            <input ref="firstField" v-model="current" :type="show ? 'text' : 'password'" autocomplete="current-password" :class="inp" @keyup.enter="save" />
          </div>
          <div>
            <label :class="lbl">Neues Passwort</label>
            <input v-model="next" :type="show ? 'text' : 'password'" autocomplete="new-password" :class="inp" @keyup.enter="save" />
            <p class="text-[11px] mt-1" :class="next && next.length < MIN_LEN ? 'text-red-500' : 'text-slate-400'">Mindestens {{ MIN_LEN }} Zeichen</p>
          </div>
          <div>
            <label :class="lbl">Neues Passwort bestätigen</label>
            <input v-model="confirm" :type="show ? 'text' : 'password'" autocomplete="new-password"
              :class="[inp, confirm && next !== confirm ? 'border-red-400 dark:border-red-500' : '']" @keyup.enter="save" />
            <p v-if="confirm && next !== confirm" class="text-[11px] text-red-500 mt-1 dark:text-red-400">Passwörter stimmen nicht überein</p>
          </div>
          <label class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 cursor-pointer select-none">
            <input v-model="show" type="checkbox" class="rounded border-slate-300 text-ks-600 focus:ring-ks-500" /> Passwörter anzeigen
          </label>
        </div>
      </div>

      <div class="flex items-center justify-end gap-3 px-5 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800">
        <button @click="$emit('close')" class="text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">Schließen</button>
        <button @click="save" :disabled="!canSave" :class="btnPrimary">{{ saving ? 'Speichern…' : 'Passwort ändern' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { api, setToken, setUser, getUser, errText } from '../api.js'
import { inp, lbl, btnPrimary, roleLabel } from '../ui.js'
import HelpHint from './HelpHint.vue'
import AbsenceEditor from './AbsenceEditor.vue'

const emit = defineEmits(['close'])
const MIN_LEN = 8      // wie im Backend (OPP_MIN_PASSWORD_LEN)

const me = ref({ ...getUser() })
const current = ref(''), next = ref(''), confirm = ref('')
const show = ref(false), saving = ref(false), msg = ref(''), msgErr = ref(false)
const firstField = ref(null)
const NOTIFY = [['assigned', 'Mir wurde ein Auftrag zugewiesen'], ['my_orders', 'Mein Auftrag wurde freigegeben, abgelehnt, auf Nacharbeit gesetzt oder bestätigt'],
  ['lldp_problem', 'LLDP meldet eine Abweichung bei einem Auftrag, den ich ausgeführt habe'], ['reservation_expiry', 'Meine Reservierung läuft in 3 Tagen ab'],
  ['confirm_suggest', 'Aufträge zur Bestätigung vorgeschlagen (Freigeber)'], ['new_user', 'Ein neuer Benutzer ohne Rechte hat sich angemeldet (globale Administratoren)'],
  ['cleanup_report', 'Wöchentlicher Aufräumbericht (globale Administratoren)']]
const ADMIN_ONLY = ['new_user', 'cleanup_report']
const notifyShown = computed(() => NOTIFY.filter(([k]) => !ADMIN_ONLY.includes(k) || (me.value.roles || []).includes('admin')))     // nur für globale Administratoren
const START_PAGES = [['', 'automatisch (Übersicht, Techniker am Handy: mobil)'], ['dashboard', 'Übersicht'], ['workorders', 'Patchaufträge'],
  ['m', 'Meine Aufträge (mobil)'], ['racks', 'Racks'], ['capacity', 'Kapazität']]
const prefs = ref(null), sites = ref([]), sessions = ref(null), prefsMsg = ref(''), represents = ref([])
async function refreshMe() { try { const m = await api.me(); me.value = { ...me.value, ...m }; setUser({ ...getUser(), absent: m.absent }) } catch {} }
async function savePrefs() {
  prefsMsg.value = ''
  try {
    const p = await api.setMyPreferences({ default_site_id: prefs.value.default_site_id || null, start_page: prefs.value.start_page })
    prefs.value = p; setUser({ ...getUser(), prefs: p }); prefsMsg.value = 'Gespeichert.'
  } catch (e) { msgErr.value = true; msg.value = errText(e) }
}
async function logoutOthers() {
  if (!confirm('Alle anderen Anmeldungen (andere Geräte und Browser) beenden?')) return
  try {
    const r = await api.logoutOthers(); setToken(r.token)
    sessions.value = { active: 1 }; prefsMsg.value = r.ended ? `${r.ended} andere Anmeldung(en) beendet.` : 'Es gab keine anderen Anmeldungen.'
  } catch (e) { msgErr.value = true; msg.value = errText(e) }
}
const notify = ref(null), notifyMsg = ref('')
async function setNotify(key, on) {
  notifyMsg.value = ''
  try { notify.value = await api.setMyNotifications({ [key]: on }); notifyMsg.value = 'Gespeichert.' }
  catch (e) { msgErr.value = true; msg.value = errText(e) }
}

const canSave = computed(() => !saving.value && !!current.value && next.value.length >= MIN_LEN && next.value === confirm.value)

async function save() {
  if (!canSave.value) return
  msg.value = ''
  if (next.value === current.value) { msgErr.value = true; msg.value = 'Das neue Passwort muss sich vom aktuellen unterscheiden'; return }
  saving.value = true
  try {
    const res = await api.changePassword(current.value, next.value)
    if (res.token) setToken(res.token)
    current.value = next.value = confirm.value = ''
    show.value = false
    msgErr.value = false; msg.value = 'Passwort geändert. Alle anderen Sitzungen wurden beendet.'
  } catch (e) {
    msgErr.value = true; msg.value = errText(e, 'Fehler beim Ändern des Passworts')
  } finally { saving.value = false }
}

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(async () => {
  window.addEventListener('keydown', onKey)
  try { const m = await api.me(); me.value = { ...me.value, ...m }; notify.value = m.notify || null; prefs.value = { ...m.prefs } } catch {}
  try { sites.value = await api.sites() } catch {}
  try { sessions.value = await api.mySessions() } catch {}
  try { represents.value = (await api.myAbsences()).represents } catch {}
  await nextTick()
  firstField.value?.focus()
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
