<template>
  <ModalDialog wide title="Aufträge nach OpenPlan übertragen" :error="error" @close="$emit('close')">
    <div v-if="result" class="space-y-2 text-sm">
      <p v-if="result.url" class="text-green-600 dark:text-green-400">Projekt „{{ result.name }}“ angelegt: <a :href="result.url" target="_blank" rel="noopener" class="underline">in OpenPlan öffnen</a> ({{ result.tasks }} Vorgänge aus der Vorlage).</p>
      <p v-if="result.created.length" class="text-green-600 dark:text-green-400">{{ result.created.length }} Vorgang/Vorgänge für Patchaufträge angelegt: {{ result.created.map(c => c.number).join(', ') }}</p>
      <p v-if="result.skipped_linked.length" class="text-slate-500">Bereits verknüpft (übersprungen): {{ result.skipped_linked.join(', ') }}</p>
      <ul v-if="result.errors.length" class="text-red-500 list-disc pl-5 dark:text-red-400"><li v-for="(e, i) in result.errors" :key="i">{{ e.number || e.id }}: {{ e.message }}</li></ul>
    </div>
    <template v-else>
      <p class="text-sm text-slate-500">{{ ids.length }} Patchauftrag/Patchaufträge ausgewählt. Je Auftrag entsteht ein Vorgang in OpenPlan (Status und Fortschritt werden danach automatisch abgeglichen).</p>
      <div class="inline-flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-600 text-sm">
        <button v-for="[k, l] in [['tasks', 'In bestehendes Projekt'], ['project', 'Neues Projekt aus Vorlage']]" :key="k" type="button" @click="mode = k"
          class="px-3 py-1.5" :class="mode === k ? 'bg-ks-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300'">{{ l }}</button>
      </div>

      <template v-if="mode === 'tasks'">
        <div><label :class="lbl">OpenPlan-Projekt</label>
          <select v-model="projectId" :class="inp" @change="loadSections"><option :value="null" disabled>wählen …</option><option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }} (ID {{ p.id }})</option></select></div>
        <div v-if="projectId"><label :class="lbl">Unter Abschnitt</label>
          <select v-model="parentId" :class="inp"><option :value="null">(oberste Ebene)</option><option v-for="t in sections" :key="t.id" :value="t.id">{{ t.suggested ? '★ ' : '' }}{{ t.wbs }} {{ t.name }}</option></select></div>
      </template>

      <template v-else>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Projektname</label><input v-model="proj.name" :class="inp" placeholder="z. B. Patchfelder RZ ↔ Etage 1" /></div>
          <div><label :class="lbl">Startdatum</label><input v-model="proj.start_date" type="date" :class="inp" /></div>
        </div>
        <div><label :class="lbl">Beschreibung (optional)</label><input v-model="proj.description" :class="inp" /></div>
        <div><label :class="lbl">Weitere Beteiligte (OpenPlan-Benutzernamen, einer pro Zeile)</label>
          <textarea v-model="proj.members" rows="2" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="anna&#10;bernd"></textarea>
          <p class="text-[11px] text-slate-400 mt-1">Sie werden als Bearbeiter eingetragen. Das Projekt gehört dem OpenPlan-Dienstkonto; ein OpenPlan-Administrator kann die Verantwortung übertragen.</p></div>
        <p class="text-xs text-slate-400">Vorlage „Einbau Patchfelder / Verkabelung“: Planung, Beschaffung, Montage je Standort, Trunk und Patchung, Messung und Abnahme. Die Aufträge werden unter „Patchaufträge (aus Portwerk)“ angehängt.</p>
      </template>
    </template>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ result ? 'Schließen' : 'Abbrechen' }}</button>
      <button v-if="!result" :class="btnPrimary" :disabled="busy || !canSubmit" @click="submit">{{ busy ? '…' : (mode === 'tasks' ? 'Vorgänge anlegen' : 'Projekt anlegen') }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const props = defineProps({ ids: { type: Array, required: true } })
defineEmits(['close'])

const mode = ref('tasks'), projects = ref([]), projectId = ref(null), sections = ref([]), parentId = ref(null)
const proj = reactive({ name: '', start_date: nextMonday(), description: '', members: '' })
const busy = ref(false), error = ref(''), result = ref(null)
const canSubmit = computed(() => mode.value === 'tasks' ? !!projectId.value : !!proj.name.trim() && !!proj.start_date)

function nextMonday() { const d = new Date(); d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); return d.toISOString().slice(0, 10) }

async function loadSections() {
  error.value = ''
  try {
    sections.value = (await api.openplanTasks(projectId.value, '')).tasks.filter(t => t.summary).sort((a, b) => Number(b.suggested) - Number(a.suggested))
    parentId.value = sections.value.find(t => t.suggested)?.id ?? null
  } catch (e) { error.value = errText(e) }
}
async function submit() {
  busy.value = true; error.value = ''
  try {
    result.value = mode.value === 'tasks'
      ? await api.openplanOrders({ project_id: projectId.value, parent_id: parentId.value, workorder_ids: props.ids })
      : await api.openplanProject({ name: proj.name, description: proj.description, start_date: proj.start_date, kind: 'patchpanel',
          members: proj.members.split(/[\n,;\s]+/).map(x => x.trim()).filter(Boolean), workorder_ids: props.ids })
  } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
onMounted(async () => {
  try {
    const [st, list] = await Promise.all([api.openplanStatus(), api.openplanProjects()])
    projects.value = list
    projectId.value = list.find(p => String(p.id) === String(st.default_project_id))?.id ?? null
    if (projectId.value) await loadSections()
  } catch (e) { error.value = errText(e) }
})
</script>
