<template>
  <ModalDialog wide :title="`${wo.number} mit OpenPlan verbinden`" :error="error" @close="$emit('close')">
    <div class="inline-flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-600 text-sm">
      <button v-for="[k, l] in [['create', 'Neue Aufgabe anlegen'], ['link', 'Mit vorhandener Aufgabe verknüpfen']]" :key="k" type="button" @click="mode = k"
        class="px-3 py-1.5" :class="mode === k ? 'bg-ks-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300'">{{ $t(l) }}</button>
    </div>

    <div><label :class="lbl">{{ $t('OpenPlan-Projekt') }}</label>
      <select v-model="projectId" :class="inp" @change="loadTasks"><option :value="null" disabled>{{ $t('wählen …') }}</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }} (ID {{ p.id }})</option></select></div>

    <template v-if="projectId">
      <template v-if="mode === 'create'">
        <div><label :class="lbl">{{ $t('Unter Abschnitt') }}</label>
          <select v-model="parentId" :class="inp"><option :value="null">{{ $t('(oberste Ebene)') }}</option>
            <option v-for="t in sections" :key="t.id" :value="t.id">{{ t.suggested ? '★ ' : '' }}{{ t.wbs }} {{ t.name }}</option></select>
          <p class="text-[11px] text-slate-400 mt-1">{{ $t('★ = Abschnitt „Patchaufträge (aus Portwerk)“ der Projektvorlage.') }}</p></div>
        <div><label :class="lbl">{{ $t('Name der Aufgabe') }}</label><input v-model="name" :class="inp" :placeholder="`${wo.number} ${wo.title}`" /></div>
        <p class="text-xs text-slate-400">{{ $t('Dauer und frühester Beginn kommen aus dem Zeitraum des Auftrags. In OpenPlan erscheint die Referenz') + ' ' }}<code>portwerk: {{ wo.number }}</code>{{ ' ' + $t('mit Link zurück.') }}</p>
      </template>
      <template v-else>
        <input v-model="q" :class="inp" :placeholder="$t('Aufgabe suchen …')" @input="loadTasksSoon" />
        <div class="max-h-64 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
          <label v-for="t in leaves" :key="t.id" class="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40">
            <input type="radio" :value="t.id" v-model="taskId" /> <span class="text-xs text-slate-400 w-10">{{ t.wbs }}</span>
            <span class="text-slate-800 dark:text-slate-100 flex-1 truncate">{{ t.name }}</span>
            <span class="text-[11px] text-slate-400">{{ t.status }}<template v-if="t.percent"> · {{ t.percent }}%</template></span>
            <span v-if="t.refs.portwerk" class="text-[11px] text-amber-600 dark:text-amber-400">{{ $t('schon') }} {{ t.refs.portwerk }}</span></label>
          <p v-if="!leaves.length" class="px-3 py-3 text-sm text-slate-400">{{ $t('Keine Aufgaben gefunden.') }}</p>
        </div>
      </template>
    </template>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ $t('Abbrechen') }}</button>
      <button :class="btnPrimary" :disabled="busy || !projectId || (mode === 'link' && !taskId)" @click="submit">{{ busy ? '…' : (mode === 'create' ? $t('Aufgabe anlegen') : $t('Verknüpfen')) }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const props = defineProps({ wo: { type: Object, required: true } })
const emit = defineEmits(['close', 'done'])

const mode = ref('create'), projects = ref([]), projectId = ref(null), tasks = ref([]), q = ref('')
const parentId = ref(null), taskId = ref(null), name = ref('')
const busy = ref(false), error = ref('')
const sections = computed(() => [...tasks.value.filter(t => t.summary)].sort((a, b) => Number(b.suggested) - Number(a.suggested)))
const leaves = computed(() => tasks.value.filter(t => !t.summary))

async function loadTasks() {
  error.value = ''; taskId.value = null
  try {
    tasks.value = (await api.openplanTasks(projectId.value, q.value)).tasks
    parentId.value = (tasks.value.find(t => t.suggested) || {}).id ?? null
  } catch (e) { error.value = errText(e) }
}
let timer
function loadTasksSoon() { clearTimeout(timer); timer = setTimeout(async () => { try { tasks.value = (await api.openplanTasks(projectId.value, q.value)).tasks } catch (e) { error.value = errText(e) } }, 250) }

async function submit() {
  busy.value = true; error.value = ''
  try {
    emit('done', mode.value === 'create'
      ? await api.openplanCreate(props.wo.id, { project_id: projectId.value, parent_id: parentId.value, name: name.value })
      : await api.openplanLink(props.wo.id, { project_id: projectId.value, task_id: taskId.value }))
  } catch (e) { error.value = errText(e) } finally { busy.value = false }
}

onMounted(async () => {
  try {
    const [st, list] = await Promise.all([api.openplanStatus(), api.openplanProjects()])
    projects.value = list
    projectId.value = list.find(p => String(p.id) === String(st.default_project_id))?.id ?? list[0]?.id ?? null
    if (projectId.value) await loadTasks()
  } catch (e) { error.value = errText(e) }
})
</script>
