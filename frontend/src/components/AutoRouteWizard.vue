<template>
  <SidePanel :open="open" title="Autorouting" @close="$emit('close')">
    <template #title>
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Autorouting</h2>
      <p class="text-xs text-slate-500 dark:text-slate-400">Patchungen von der Quelle zum Ziel automatisch planen</p>
    </template>

    <template v-if="done">
      <div class="rounded-lg border border-green-300 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-4 space-y-2">
        <p class="text-sm font-medium text-green-700 dark:text-green-400">Patchauftrag angelegt</p>
        <p class="text-sm text-slate-700 dark:text-slate-200">{{ done.workorder.number }} – {{ done.workorder.title }}</p>
        <p class="text-xs text-slate-500 dark:text-slate-400">{{ done.route.summary }}<template v-if="done.device_id"> · Gerät als „geplant“ angelegt</template>. Die Ports sind verplant.</p>
        <router-link :to="`/workorders/${done.workorder.id}`" :class="btnPrimary" class="inline-block" @click="$emit('close')">Auftrag öffnen</router-link>
      </div>
    </template>

    <template v-else>
      <!-- 1. Quelle -->
      <section class="space-y-2">
        <h3 :class="lbl" class="!mb-0">1 · Quelle</h3>
        <div class="flex gap-4 text-sm">
          <label class="flex items-center gap-1.5"><input v-model="mode" type="radio" value="port" @change="reset" /> vorhandener Port</label>
          <label class="flex items-center gap-1.5"><input v-model="mode" type="radio" value="new" @change="reset" /> neues Gerät (als „geplant“ anlegen)</label>
        </div>
        <PortPicker v-if="mode === 'port'" :key="'src' + srcKey" v-model="srcPort" label="Gerät und Port" :preset-device-id="presetDeviceId" :preset-port-id="presetPortId" @select="p => { srcSel = p; reset() }" />
        <div v-else class="grid grid-cols-2 gap-3">
          <div class="col-span-2"><label :class="lbl">Hostname</label><input v-model="nd.hostname" :class="inp" placeholder="z. B. srv-db-07" @input="reset" /></div>
          <div class="col-span-2"><label :class="lbl">Rack / Schrank</label>
            <select v-model="nd.location_id" :class="inp" @change="reset"><option :value="null" disabled>Rack wählen …</option>
              <option v-for="l in racks" :key="l.id" :value="l.id">{{ l.path }}</option></select></div>
          <div><label :class="lbl">Typ</label><select v-model="nd.type" :class="inp" @change="reset"><option v-for="t in DEVICE_TYPES" :key="t[0]" :value="t[0]">{{ $t(t[1]) }}</option></select></div>
          <div><label :class="lbl">Höhe (HE) / Position</label>
            <div class="flex gap-2"><input v-model.number="nd.height_u" type="number" min="1" :class="inp" /><input v-model.number="nd.rack_position" type="number" min="1" :class="inp" placeholder="Pos." /></div></div>
          <div><label :class="lbl">Netzwerk-Ports</label>
            <div class="flex gap-2"><input v-model="nd.nic_prefix" :class="inp" /><input v-model.number="nd.nic_count" type="number" min="1" max="64" :class="inp" /></div></div>
          <div><label :class="lbl">Medium / Port für die Route</label>
            <div class="flex gap-2"><select v-model="nd.medium" :class="inp" @change="reset"><option v-for="m in ['RJ45', 'SFP', 'SFP+', 'LWL']" :key="m" :value="m">{{ m }}</option></select>
              <select v-model="nd.port_no" :class="inp" @change="reset"><option v-for="n in portNos" :key="n" :value="n">{{ nd.nic_prefix }}{{ n }}</option></select></div></div>
        </div>
      </section>

      <!-- 2. Ziel -->
      <section class="space-y-2">
        <h3 :class="lbl" class="!mb-0">2 · Ziel</h3>
        <PortPicker :key="'tgt' + tgtKey" v-model="tgtPort" label="Gerät und Port (z. B. Switchport)" @select="p => { tgtSel = p; reset() }" />
        <p v-if="tgtSel && ['patchpanel', 'outlet'].includes(tgtSel.device?.type)" class="text-xs text-red-500">Das Ziel muss ein aktives Gerät sein (nicht Patchfeld oder Dose).</p>
      </section>

      <button :class="btnPrimary" :disabled="!ready || !!busy" @click="search">{{ busy === 'search' ? 'Suche …' : 'Route suchen' }}</button>
      <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

      <!-- 3. Vorschläge -->
      <section v-if="result" class="space-y-3">
        <h3 :class="lbl" class="!mb-0">3 · Vorschlag</h3>
        <p v-if="!result.routes.length" class="text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2">Keine Route gefunden. {{ result.why }}</p>
        <label v-for="(r, i) in result.routes" :key="i" class="block rounded-lg border p-3 cursor-pointer"
               :class="pick === i ? 'border-ks-500 bg-ks-50/60 dark:bg-ks-900/20' : 'border-slate-200 dark:border-slate-700'">
          <div class="flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-100">
            <input v-model="pick" type="radio" :value="i" /> {{ i === 0 ? 'Empfohlen' : 'Alternative ' + i }}
            <span class="ml-auto text-xs font-normal text-slate-500">{{ r.summary }}</span>
          </div>
          <ol class="mt-2 space-y-1 text-xs">
            <li class="font-mono text-slate-700 dark:text-slate-200">● {{ r.steps[0].from }}</li>
            <li v-for="(s, k) in r.steps" :key="k" class="flex items-start gap-2">
              <span class="shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium" :class="STEP[s.type].cls">{{ STEP[s.type].label }}</span>
              <span class="font-mono text-slate-600 dark:text-slate-300">→ {{ s.to }}<span v-if="s.type === 'cord' && s.text.includes('Racks')" class="font-sans text-slate-400"> (zwischen Racks)</span></span>
            </li>
          </ol>
        </label>
        <template v-if="result.routes.length">
          <div><label :class="lbl">Titel des Patchauftrags</label><input v-model="title" :class="inp" :placeholder="defaultTitle" /></div>
          <div class="grid grid-cols-2 gap-3 items-end">
            <div><label :class="lbl">Kabelart der neuen Patchkabel</label>
              <select v-model="cableType" :class="inp"><option value="">automatisch ({{ result.cable_type }})</option><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
            <button :class="btnPrimary" :disabled="!!busy" @click="create()">{{ busy === 'create' ? 'Lege an …' : 'Patchauftrag anlegen' }}</button>
          </div>
          <p class="text-xs text-slate-400">Je neuem Patchkabel entsteht eine Position „herstellen“; bei einem neuen Gerät zusätzlich der Einbau. Das Gerät wird als <b>geplant</b> angelegt und gilt nach der Bestätigung des Auftrags als eingebaut.</p>
        </template>
      </section>
    </template>
  </SidePanel>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import SidePanel from './SidePanel.vue'
import PortPicker from './PortPicker.vue'
import { api, errText, conflictOf } from '../api.js'
import { cableTypes, loadCableTypes } from '../catalog.js'
import { inp, lbl, btnPrimary, DEVICE_TYPES, CONTAINER_KINDS } from '../ui.js'

/** Autorouting: Quelle (vorhandener Port oder neues, als „geplant“ angelegtes Gerät) und Ziel wählen – Portwerk schlägt die Patchungen dazwischen
 *  vor (vorhandene Festverkabelung, Patchfelder) und legt daraus einen Patchauftrag an. */
const props = defineProps({ open: Boolean, presetPortId: { type: Number, default: null }, presetDeviceId: { type: Number, default: null },
                            presetLocationId: { type: Number, default: null }, startNew: Boolean })
const emit = defineEmits(['close', 'done'])

const STEP = { cord: { label: 'neu', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  cable: { label: 'vorhanden', cls: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300' },
  station: { label: 'Station', cls: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400' } }
const mode = ref('port'), srcPort = ref(''), srcSel = ref(null), tgtPort = ref(''), tgtSel = ref(null), srcKey = ref(0), tgtKey = ref(0)
const nd = reactive({ hostname: '', type: 'server', location_id: null, height_u: 1, rack_position: null, nic_prefix: 'NIC', nic_count: 2, medium: 'RJ45', port_no: 1 })
const racks = ref([]), result = ref(null), pick = ref(0), title = ref(''), cableType = ref(''), busy = ref(''), error = ref(''), done = ref(null)
const portNos = computed(() => Array.from({ length: Math.max(1, nd.nic_count || 1) }, (_, i) => i + 1))

const ready = computed(() => !!tgtSel.value && tgtSel.value.device && !['patchpanel', 'outlet'].includes(tgtSel.value.device.type) &&
  (mode.value === 'port' ? !!srcSel.value : nd.hostname.trim() && nd.location_id))
const defaultTitle = computed(() => result.value ? `Route ${result.value.source} → ${result.value.target}` : '')
function reset() { result.value = null; error.value = ''; pick.value = 0 }

watch(() => props.open, async o => {
  if (!o) return
  done.value = null; reset(); srcSel.value = tgtSel.value = null; srcPort.value = tgtPort.value = ''; srcKey.value++; tgtKey.value++
  mode.value = props.startNew ? 'new' : 'port'; Object.assign(nd, { hostname: '', location_id: props.presetLocationId, port_no: 1 })
  loadCableTypes()
  try { racks.value = (await api.locations()).filter(l => CONTAINER_KINDS.includes(l.kind)) } catch { racks.value = [] }
})

function body(dry) {
  const b = { target_port_id: tgtSel.value.id, dry_run: dry, cable_type: cableType.value }
  if (mode.value === 'port') return { ...b, source_port_id: srcSel.value.id }
  return { ...b, source_port_name: `${nd.nic_prefix}${nd.port_no}`, new_device: { hostname: nd.hostname.trim(), type: nd.type, location_id: nd.location_id,
    rack_position: nd.rack_position || null, height_u: nd.height_u || null, nic_prefix: nd.nic_prefix, nic_count: nd.nic_count, medium: nd.medium } }
}
async function search() {
  busy.value = 'search'; error.value = ''; result.value = null
  try { result.value = await api.routePlan(body(true)); pick.value = 0 } catch (e) { error.value = errText(e) } finally { busy.value = '' }
}
async function create(reserved = false) {
  busy.value = 'create'; error.value = ''
  try {
    done.value = await api.routePlan({ ...body(false), route_index: pick.value, workorder_title: title.value.trim(), use_reserved: reserved })
    emit('done', done.value)
  } catch (e) {
    const c = conflictOf(e)
    if (c && c.code === 'port_reserved' && !reserved && confirm(c.message)) { busy.value = ''; return create(true) }
    error.value = errText(e)
  } finally { busy.value = '' }
}
</script>
