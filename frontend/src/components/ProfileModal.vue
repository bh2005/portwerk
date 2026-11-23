<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4" @click.self="$emit('close')">
    <div class="w-full max-w-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden"
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
          <label v-for="[k, l] in NOTIFY" :key="k" class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 cursor-pointer">
            <input type="checkbox" :checked="notify[k]" @change="setNotify(k, $event.target.checked)" /> {{ l }}</label>
          <p class="text-xs text-slate-400">{{ me.email ? `an ${me.email}` : 'Keine E-Mail-Adresse hinterlegt – es kommen keine Mails.' }}
            Ob überhaupt Mails verschickt werden, legt die Verwaltung fest.</p>
          <p v-if="notifyMsg" class="text-xs text-green-600">{{ notifyMsg }}</p>
        </div>

        <hr v-if="notify" class="border-slate-100 dark:border-slate-700" />

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
            <p v-if="confirm && next !== confirm" class="text-[11px] text-red-500 mt-1">Passwörter stimmen nicht überein</p>
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
import { api, setToken, getUser, errText } from '../api.js'
import { inp, lbl, btnPrimary, roleLabel } from '../ui.js'
import HelpHint from './HelpHint.vue'

const emit = defineEmits(['close'])
const MIN_LEN = 8      // wie im Backend (OPP_MIN_PASSWORD_LEN)

const me = ref({ ...getUser() })
const current = ref(''), next = ref(''), confirm = ref('')
const show = ref(false), saving = ref(false), msg = ref(''), msgErr = ref(false)
const firstField = ref(null)
const NOTIFY = [['confirm_suggest', 'Aufträge zur Bestätigung vorgeschlagen (Freigeber)'], ['assigned', 'Mir wurde ein Auftrag zugewiesen']]
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
  try { const m = await api.me(); me.value = { ...me.value, ...m }; notify.value = m.notify || null } catch {}
  await nextTick()
  firstField.value?.focus()
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
