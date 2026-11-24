<template>
  <ModalDialog huge title="Geräte aus OpenPlan übernehmen" :error="error" @close="$emit('close')">
    <!-- Ergebnis -->
    <div v-if="result" class="space-y-2 text-sm">
      <p class="text-green-700 dark:text-green-400">{{ result.created.length }} Gerät(e) als „geplant“ angelegt, {{ result.linked.length }} verknüpft.</p>
      <ul v-if="result.created.length" class="list-disc pl-5">
        <li v-for="d in result.created" :key="d.id"><router-link :to="`/devices/${d.id}`" class="text-ks-600 dark:text-ks-400 hover:underline font-mono" @click="$emit('close')">{{ d.hostname }}</router-link>
          <span class="text-slate-500">{{ d.ports ? ` · ${d.ports} Ports aus dem Katalog` : '' }}{{ d.rack_position ? ` · HE ${d.rack_position}` : '' }}</span></li>
      </ul>
      <p v-for="s in result.skipped" :key="'s' + s.task_id" class="text-amber-700 dark:text-amber-300">{{ s.hostname }}: {{ s.why }}</p>
      <p v-for="w in result.warnings" :key="w" class="text-amber-700 dark:text-amber-300">{{ w }}</p>
    </div>

    <div v-else class="space-y-3">
      <div class="flex items-end gap-3 flex-wrap">
        <div class="w-80"><label :class="lbl">OpenPlan-Projekt</label>
          <select v-model="pid" :class="inp" @change="load"><option :value="null" disabled>wählen …</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
        <p v-if="data" class="text-sm text-slate-500 dark:text-slate-400 pb-2">
          {{ data.items.length }} Gerät(e): {{ data.counts.new }} neu · {{ data.counts.exists }} schon vorhanden · {{ data.counts.linked }} übernommen
          <template v-if="data.counts.no_site"> · {{ data.counts.no_site }} ohne Standort</template></p>
      </div>
      <p class="text-xs text-slate-400">Geräte-Vorgänge aus Geräte-Rollouts in OpenPlan. Neue Geräte entstehen als <b>geplant</b> – mit Ports aus dem Katalogmodell und auf der
        angegebenen HE, wenn sie frei ist. Vorhandene Geräte gleichen Namens werden nur verknüpft. In OpenPlan bekommt der Vorgang einen Verweis auf das Gerät.</p>
      <p v-if="busy && !data" class="text-sm text-slate-400">Lade …</p>

      <div v-if="data && data.items.length" class="overflow-x-auto max-h-[55vh] border border-slate-200 dark:border-slate-700 rounded-lg">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-slate-50 dark:bg-slate-800"><tr>
            <th :class="th"><input type="checkbox" :checked="allPicked" :indeterminate.prop="somePicked && !allPicked" @change="toggleAll" /></th>
            <th :class="th">Gerät</th><th :class="th">Typ / Modell</th><th :class="th">Standort</th><th :class="th">Ort in Portwerk</th><th :class="th">Hinweis</th></tr></thead>
          <tbody>
            <tr v-for="i in data.items" :key="i.task_id" class="border-t border-slate-100 dark:border-slate-700 align-top" :class="selectable(i) ? '' : 'opacity-60'">
              <td :class="td"><input v-if="selectable(i)" v-model="picked[i.task_id]" type="checkbox" /></td>
              <td :class="td"><div class="font-mono">{{ i.hostname }}</div>
                <div class="text-xs text-slate-400">{{ [i.ip, i.serial].filter(Boolean).join(' · ') }}</div></td>
              <td :class="td">
                <select v-if="i.state === 'new'" v-model="types[i.task_id]" :class="inp" class="!py-1 !text-xs !w-36">
                  <option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ l }}</option></select>
                <span v-else>{{ typeLabel(i.type) }}</span>
                <div class="text-xs" :class="i.model_id ? 'text-green-700 dark:text-green-400' : 'text-slate-400'" :title="i.model_id ? 'Katalogmodell gefunden – Ports werden angelegt' : 'nicht im Katalog'">{{ i.model_label || i.modell || '–' }}</div></td>
              <td :class="td" class="text-xs">{{ i.site || i.loc || i.standort || '–' }}</td>
              <td :class="td">
                <template v-if="i.state === 'new'">
                  <select v-model="places[i.task_id]" :class="inp" class="!py-1 !text-xs !w-56" @change="picked[i.task_id] = true">
                    <option :value="null">– Ort wählen –</option>
                    <option v-for="p in data.places[i.site_id] || []" :key="p.id" :value="p.id">{{ p.path }}</option></select>
                  <div v-if="i.rack_position && places[i.task_id] === i.location_id" class="text-xs text-slate-500">HE {{ i.rack_position }}</div>
                  <div v-else-if="i.rack" class="text-xs text-slate-400">OpenPlan: {{ [i.raum, i.rack].filter(Boolean).join(' / ') }}</div>
                </template>
                <router-link v-else-if="i.device" :to="`/devices/${i.device.id}`" class="text-xs text-ks-600 dark:text-ks-400 hover:underline" @click="$emit('close')">
                  {{ i.device.hostname }} ({{ statusLabel(i.device.status) }})</router-link>
              </td>
              <td :class="td" class="text-xs">
                <span :class="BADGE[i.state][1]" class="inline-block px-1.5 py-0.5 rounded mr-1">{{ BADGE[i.state][0] }}</span>
                <span class="text-slate-500">{{ i.hint }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="data" class="text-sm text-slate-500">Das Projekt enthält keine Geräte-Vorgänge (Import einer Geräteliste in OpenPlan).</p>
    </div>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ result ? 'Schließen' : 'Abbrechen' }}</button>
      <button v-if="!result" :class="btnPrimary" :disabled="busy || !pickCount" @click="apply">{{ pickCount }} übernehmen</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { api, errText } from '../api.js'
import { inp, lbl, th, td, btnPrimary, btnGhost, DEVICE_TYPES, typeLabel, statusLabel } from '../ui.js'

/** Geräte-Vorgänge eines OpenPlan-Projekts als geplante Geräte anlegen bzw. vorhandene verknüpfen. */
const props = defineProps({ projectId: { type: Number, default: null } })
const emit = defineEmits(['close', 'done'])
const BADGE = {
  new: ['neu', 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'],
  exists: ['vorhanden', 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300'],
  linked: ['übernommen', 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'],
  no_site: ['kein Standort', 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'],
}
const projects = ref([]), pid = ref(props.projectId), data = ref(null), result = ref(null), error = ref(''), busy = ref(false)
const picked = reactive({}), places = reactive({}), types = reactive({})

const selectable = i => i.state === 'new' || i.state === 'exists'
const ready = i => i.state === 'exists' || (i.state === 'new' && !!places[i.task_id])
const pickCount = computed(() => data.value ? data.value.items.filter(i => selectable(i) && picked[i.task_id]).length : 0)
const allPicked = computed(() => data.value && data.value.items.filter(selectable).every(i => picked[i.task_id]))
const somePicked = computed(() => pickCount.value > 0)
function toggleAll(e) { for (const i of data.value.items.filter(selectable)) picked[i.task_id] = e.target.checked }

async function load() {
  if (!pid.value) return
  busy.value = true; error.value = ''; data.value = null
  try {
    data.value = await api.openplanDevices(pid.value)
    for (const i of data.value.items) {
      places[i.task_id] = i.location_id; types[i.task_id] = i.type
      picked[i.task_id] = selectable(i) && ready(i)                   // vorausgewählt: alles, was ohne Nacharbeit übernommen werden kann
    }
  } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
async function apply() {
  const items = data.value.items.filter(i => selectable(i) && picked[i.task_id])
  const missing = items.filter(i => !ready(i))
  if (missing.length) { error.value = `Bitte einen Ort wählen: ${missing.map(i => i.hostname).join(', ')}`; return }
  busy.value = true; error.value = ''
  try {
    result.value = await api.importOpenplanDevices(pid.value, items.map(i => ({ task_id: i.task_id, location_id: places[i.task_id] ?? null, type: types[i.task_id] })))
    emit('done')
  } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
onMounted(async () => {
  try {
    projects.value = await api.openplanProjects()
    if (!pid.value) { const s = await api.openplanStatus(); pid.value = Number(s.default_project_id) || null }
    if (!pid.value && projects.value.length === 1) pid.value = projects.value[0].id          // nur ein Projekt sichtbar: gleich nehmen
    load()
  } catch (e) { error.value = errText(e) }
})
</script>
