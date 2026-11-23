<template>
  <div class="space-y-2">
    <div v-for="a in list" :key="a.id" class="flex items-center gap-2 text-sm">
      <span :class="a.current ? 'text-amber-700 dark:text-amber-400 font-medium' : 'text-slate-600 dark:text-slate-300'">
        {{ fmt(a.start_date) }} – {{ fmt(a.end_date) }}<template v-if="a.current"> (jetzt)</template></span>
      <span class="text-xs text-slate-500 truncate">{{ a.deputy ? `Vertretung: ${a.deputy.full_name || a.deputy.username}` : 'ohne Vertretung' }}{{ a.note ? ` · ${a.note}` : '' }}</span>
      <button type="button" class="ml-auto text-xs text-red-600 hover:underline" @click="remove(a)">löschen</button>
    </div>
    <p v-if="!list.length" class="text-xs text-slate-400">Keine Abwesenheit eingetragen.</p>
    <div class="grid grid-cols-2 gap-2">
      <div><label :class="lbl">von</label><input v-model="f.start_date" type="date" :class="inp" /></div>
      <div><label :class="lbl">bis</label><input v-model="f.end_date" type="date" :class="inp" /></div>
      <div><label :class="lbl">Vertretung</label>
        <select v-model="f.deputy_id" :class="inp"><option :value="null">keine</option>
          <option v-for="u in deputies" :key="u.id" :value="u.id">{{ u.full_name || u.username }}{{ u.absent ? ' (selbst abwesend)' : '' }}</option></select></div>
      <div><label :class="lbl">Notiz</label><input v-model="f.note" :class="inp" placeholder="z. B. Urlaub" /></div>
    </div>
    <div class="flex items-center gap-2">
      <button type="button" :class="btnGhost" class="!py-1 !px-3 !text-xs" :disabled="!f.start_date || !f.end_date" @click="add">Abwesenheit eintragen</button>
      <span v-if="err" class="text-xs text-red-500">{{ err }}</span>
    </div>
    <p class="text-xs text-slate-400">Im Zeitraum gehen deine E-Mail-Benachrichtigungen an die Vertretung (wenn sie dafür berechtigt ist), und sie sieht deine
      zugewiesenen Aufträge unter „Meine Aufgaben“. Zuweisungen selbst bleiben bei dir.</p>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnGhost } from '../ui.js'

/** Abwesenheiten pflegen – eigene (ohne ``userId``) oder als Administrator für einen anderen Benutzer. */
const props = defineProps({ userId: { type: Number, default: null } })
const emit = defineEmits(['changed'])
const list = ref([]), deputies = ref([]), err = ref('')
const f = reactive({ start_date: '', end_date: '', deputy_id: null, note: '' })
const fmt = s => s.split('-').reverse().join('.')

async function load() {
  try { list.value = props.userId ? await api.userAbsences(props.userId) : (await api.myAbsences()).absences } catch (e) { err.value = errText(e) }
}
async function add() {
  err.value = ''
  try {
    props.userId ? await api.addUserAbsence(props.userId, { ...f }) : await api.addMyAbsence({ ...f })
    Object.assign(f, { start_date: '', end_date: '', deputy_id: null, note: '' }); await load(); emit('changed')
  } catch (e) { err.value = errText(e) }
}
async function remove(a) {
  try { props.userId ? await api.deleteUserAbsence(props.userId, a.id) : await api.deleteMyAbsence(a.id); await load(); emit('changed') }
  catch (e) { err.value = errText(e) }
}
onMounted(async () => {
  load()
  try { deputies.value = (await api.directoryUsers()).filter(u => u.id !== props.userId) } catch { /* ohne Liste keine Auswahl */ }
})
</script>
