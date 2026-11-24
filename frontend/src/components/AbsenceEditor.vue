<template>
  <div class="space-y-2">
    <div v-for="a in list" :key="a.id" class="flex items-center gap-2 text-sm">
      <span class="whitespace-nowrap shrink-0" :class="a.current ? 'text-amber-700 dark:text-amber-400 font-medium' : 'text-slate-600 dark:text-slate-300'">
        {{ fmt(a.start_date) }} – {{ fmt(a.end_date) }}<template v-if="a.current"> (jetzt)</template></span>
      <span class="text-xs text-slate-500 truncate min-w-0" :title="a.note">{{ a.deputy ? `Vertretung: ${a.deputy.full_name || a.deputy.username}${a.deputy_is_default ? ' (Standard)' : ''}` : 'ohne Vertretung' }}{{ a.note ? ` · ${a.note}` : '' }}</span>
      <span v-if="a.readonly" class="ml-auto shrink-0 whitespace-nowrap text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300" :title="`Kommt aus ${a.source_label} – dort ändern oder löschen`">aus {{ a.source_label }}</span>
      <button v-else type="button" class="ml-auto shrink-0 text-xs text-red-600 hover:underline dark:text-red-400" @click="remove(a)">löschen</button>
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
      <span v-if="err" class="text-xs text-red-500 dark:text-red-400">{{ err }}</span>
    </div>
    <div class="flex items-end gap-2 pt-1">
      <div class="flex-1"><label :class="lbl">Standard-Vertretung</label>
        <select v-model="stdDeputy" :class="inp" @change="saveStd"><option :value="null">keine</option>
          <option v-for="u in deputies" :key="u.id" :value="u.id">{{ u.full_name || u.username }}</option></select></div>
      <span v-if="stdMsg" class="text-xs text-green-600 dark:text-green-400 pb-2">{{ stdMsg }}</span>
    </div>
    <p class="text-xs text-slate-400">Die Standard-Vertretung gilt für Abwesenheiten aus OpenPlan und wird beim Eintragen vorgeschlagen.</p>
    <p class="text-xs text-slate-400">Im Zeitraum gehen deine E-Mail-Benachrichtigungen an die Vertretung (wenn sie dafür berechtigt ist), und sie sieht deine
      zugewiesenen Aufträge unter „Meine Aufgaben“. Zuweisungen selbst bleiben bei dir.</p>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText, getUser } from '../api.js'
import { inp, lbl, btnGhost } from '../ui.js'

/** Abwesenheiten pflegen – eigene (ohne ``userId``) oder als Administrator für einen anderen Benutzer. */
const props = defineProps({ userId: { type: Number, default: null } })
const emit = defineEmits(['changed'])
const list = ref([]), deputies = ref([]), err = ref(''), stdDeputy = ref(null), stdMsg = ref('')
const f = reactive({ start_date: '', end_date: '', deputy_id: null, note: '' })
const fmt = s => s.split('-').reverse().join('.')

async function load() {
  try { list.value = props.userId ? await api.userAbsences(props.userId) : (await api.myAbsences()).absences } catch (e) { err.value = errText(e) }
}
async function add() {
  err.value = ''
  try {
    props.userId ? await api.addUserAbsence(props.userId, { ...f }) : await api.addMyAbsence({ ...f })
    Object.assign(f, { start_date: '', end_date: '', deputy_id: stdDeputy.value, note: '' }); await load(); emit('changed')
  } catch (e) { err.value = errText(e) }
}
async function remove(a) {
  try { props.userId ? await api.deleteUserAbsence(props.userId, a.id) : await api.deleteMyAbsence(a.id); await load(); emit('changed') }
  catch (e) { err.value = errText(e) }
}
async function saveStd() {
  err.value = ''; stdMsg.value = ''
  try {
    props.userId ? await api.setUserDeputy(props.userId, stdDeputy.value) : await api.setMyDeputy(stdDeputy.value)
    if (!f.deputy_id) f.deputy_id = stdDeputy.value
    stdMsg.value = 'gespeichert'; await load(); emit('changed')
  } catch (e) { err.value = errText(e) }
}
onMounted(async () => {
  load()
  try {
    const d = (props.userId ? await api.userDeputy(props.userId) : await api.myDeputy()).deputy
    stdDeputy.value = f.deputy_id = d?.id ?? null
  } catch { /* ohne Standard */ }
  try { deputies.value = (await api.directoryUsers()).filter(u => u.id !== (props.userId ?? getUser().id)) } catch { /* ohne Liste keine Auswahl */ }
})
</script>
