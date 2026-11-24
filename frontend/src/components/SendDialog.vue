<template>
  <ModalDialog wide :title="title" :error="error" @close="$emit('close')">
    <div v-if="result" class="space-y-2">
      <p class="text-sm text-green-600 dark:text-green-400">Gesendet an: {{ result.sent_to.join(', ') }} ({{ result.items }} Positionen).</p>
      <p v-if="result.skipped_no_email.length" class="text-sm text-amber-600 dark:text-amber-400">Ohne E-Mail-Adresse übersprungen: {{ result.skipped_no_email.join(', ') }}</p>
    </div>
    <template v-else>
      <div>
        <label :class="lbl">An Benutzer</label>
        <input v-model="q" :class="inp" placeholder="Benutzer suchen …" />
        <div class="mt-1 max-h-44 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
          <label v-for="u in shownUsers" :key="u.id" class="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40">
            <input type="checkbox" :checked="picked.has(u.id)" @change="toggle(u.id)" />
            <span class="text-slate-800 dark:text-slate-100">{{ u.full_name || u.username }}</span><span class="text-xs text-slate-400">{{ u.username }}<template v-if="u.roles.length"> · {{ u.roles.map(roleLabel).join(', ') }}</template></span>
            <span v-if="!u.has_email" class="ml-auto text-[11px] text-amber-600 dark:text-amber-400">keine E-Mail-Adresse</span>
          </label>
          <p v-if="!shownUsers.length" class="px-3 py-3 text-sm text-slate-400">Keine Benutzer gefunden.</p>
        </div>
        <p class="text-[11px] text-slate-400 mt-1">Es werden nur Benutzer angeboten, die den Auftrag sehen dürfen.</p>
      </div>
      <div><label :class="lbl">Weitere E-Mail-Adressen (eine pro Zeile oder mit Komma)</label>
        <textarea v-model="emails" rows="2" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="extern@example.test"></textarea></div>
      <div><label :class="lbl">Nachricht (optional)</label><textarea v-model="message" rows="3" :class="inp" placeholder="z. B. Bitte bis Freitag in Etage 2 patchen."></textarea></div>
      <div class="flex gap-5 flex-wrap text-sm text-slate-600 dark:text-slate-300">
        <label class="flex items-center gap-2"><input type="checkbox" v-model="attachPdf" /> Arbeitsanweisung als PDF anhängen</label>
        <label class="flex items-center gap-2"><input type="checkbox" v-model="attachCsv" /> Arbeitsliste als CSV anhängen</label>
        <label class="flex items-center gap-2"><input type="checkbox" v-model="includeList" /> Positionen im Text auflisten</label>
      </div>
    </template>
    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ result ? 'Schließen' : 'Abbrechen' }}</button>
      <button v-if="!result" :class="btnPrimary" :disabled="busy || (!picked.size && !emailList.length)" @click="send">{{ busy ? 'Sende …' : 'Senden' }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost, roleLabel } from '../ui.js'

const props = defineProps({
  title: { type: String, default: 'Per E-Mail senden' },
  workorderId: { type: Number, default: null },       // für die Auswahl der Benutzer mit Zugriff
  submit: { type: Function, required: true },          // body -> Promise (Antwort des Servers)
})
defineEmits(['close'])

const users = ref([]), q = ref(''), picked = ref(new Set()), emails = ref(''), message = ref('')
const attachCsv = ref(true), attachPdf = ref(true), includeList = ref(true)
const busy = ref(false), error = ref(''), result = ref(null)

const emailList = computed(() => emails.value.split(/[\n,;\s]+/).map(x => x.trim()).filter(Boolean))
const shownUsers = computed(() => users.value.filter(u => !q.value.trim() || `${u.username} ${u.full_name}`.toLowerCase().includes(q.value.trim().toLowerCase())))
function toggle(id) { const s = new Set(picked.value); s.has(id) ? s.delete(id) : s.add(id); picked.value = s }

async function send() {
  busy.value = true; error.value = ''
  try { result.value = await props.submit({ user_ids: [...picked.value], emails: emailList.value, message: message.value, attach_csv: attachCsv.value, attach_pdf: attachPdf.value, include_list: includeList.value }) }
  catch (e) { error.value = errText(e) } finally { busy.value = false }
}
onMounted(async () => { try { users.value = await api.directoryUsers(props.workorderId) } catch (e) { error.value = errText(e) } })
</script>
