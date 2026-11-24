<template>
  <ModalDialog huge title="Arbeitsplatz einrichten" :error="error" @close="$emit('close')">
    <div v-if="result" class="space-y-2">
      <p class="text-sm text-green-700 dark:text-green-400">Auftrag {{ result.workorder.number }} {{ result.workorder.new ? 'angelegt' : 'ergänzt' }}:</p>
      <ul class="text-sm list-disc pl-5"><li v-for="(i, n) in result.items" :key="n">{{ i.text }}</li></ul>
      <router-link :to="`/workorders/${result.workorder.id}`" :class="btnPrimary" class="inline-block" @click="$emit('close')">Zum Auftrag</router-link>
    </div>
    <div v-else class="space-y-4">
      <!-- 1. Dose -->
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">Dose</label>
          <select v-model="outletId" :class="inp" :disabled="!!preset" @change="loadOutletPorts"><option :value="null" disabled>wählen …</option>
            <option v-for="d in outlets" :key="d.id" :value="d.id">{{ d.hostname }}{{ d.location_path ? ' · ' + d.location_path : '' }}</option></select></div>
        <div><label :class="lbl">Anschluss</label>
          <select v-model="f.outlet_port_id" :class="inp" :disabled="!!preset" @change="check"><option :value="null" disabled>wählen …</option>
            <option v-for="p in outletPorts" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
      </div>

      <template v-if="prev">
        <!-- 2. Strecke -->
        <div class="rounded-lg border p-3 text-sm" :class="prev.state === 'open' ? 'border-slate-200 dark:border-slate-700' : prev.state === 'connected' ? 'border-sky-300 bg-sky-50 dark:bg-sky-900/20' : 'border-amber-300 bg-amber-50 dark:bg-amber-900/20'">
          <p v-if="prev.state === 'open'">Die Dose führt bis <b class="font-mono">{{ prev.patch_point.label }}</b> – dort fehlt das Patchkabel zum Switch.</p>
          <p v-else-if="prev.state === 'connected'">{{ prev.why }}<template v-if="prev.switch_port"> (<b class="font-mono">{{ prev.switch_port.label }}</b>)</template>. Es wird nur die VLAN-Konfiguration geändert.</p>
          <p v-else class="text-amber-800 dark:text-amber-300">{{ prev.why }}. Bitte zuerst die Verkabelung Dose → Patchfeld erfassen (Kabel-Assistent).</p>
          <details class="mt-2"><summary class="cursor-pointer text-xs text-slate-500">Strecke anzeigen</summary><div class="mt-2"><PathGraphic :path="prev.path" /></div></details>
        </div>

        <template v-if="prev.state !== 'undocumented'">
          <!-- 3. Switchport -->
          <div v-if="prev.state === 'open'"><label :class="lbl">Switchport</label>
            <select v-model="f.switch_port_id" :class="inp" @change="check">
              <option v-for="c in prev.candidates" :key="c.port_id" :value="c.port_id">{{ c.hostname }}:{{ c.port }} · {{ c.distance_label }}{{ c.location ? ' (' + c.location + ')' : '' }}</option></select>
            <p class="text-xs text-slate-400 mt-1">Freie Ports (nicht belegt, reserviert oder verplant), zuerst im Rack des Patchfelds.</p></div>

          <!-- 4. Profil / VLAN -->
          <div class="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
            <div class="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">VLAN / Portprofil am Switchport</div>
            <PortConfigFields :cfg="cfg" :profiles="profiles" :vlans="vlans" />
          </div>

          <!-- Kabel, Endgerät -->
          <div v-if="prev.state === 'open'" class="grid sm:grid-cols-4 gap-3">
            <div><label :class="lbl">Kabelart</label><select v-model="f.cable_type" :class="inp"><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
            <div><label :class="lbl">Kabelnummer</label><input v-model="f.cable_label" :class="inp" /></div>
            <div><label :class="lbl">Länge (m)</label><input v-model.number="f.length_m" type="number" step="0.5" min="0" :class="inp" /></div>
            <div><label :class="lbl">Farbe</label><input v-model="f.color" :class="inp" /></div>
          </div>
          <div class="grid sm:grid-cols-2 gap-3">
            <div><label :class="lbl">Endgerät anschließen (optional)</label>
              <select v-model="endpointId" :class="inp" @change="loadEndpointPorts"><option :value="null">— nein —</option>
                <option v-for="d in endpoints" :key="d.id" :value="d.id">{{ d.hostname }}</option></select></div>
            <div v-if="endpointId"><label :class="lbl">Port am Endgerät</label>
              <select v-model="f.endpoint_port_id" :class="inp" @change="check"><option v-for="p in endpointPorts" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
          </div>

          <!-- 5. Auftrag -->
          <div class="grid sm:grid-cols-2 gap-3">
            <div><label :class="lbl">Patchauftrag</label>
              <select v-model="f.workorder_id" :class="inp"><option :value="null">neuer Auftrag</option>
                <option v-for="w in drafts" :key="w.id" :value="w.id">{{ w.number }} · {{ w.title }}</option></select></div>
            <div v-if="!f.workorder_id"><label :class="lbl">Titel</label><input v-model="f.workorder_title" :class="inp" :placeholder="prev.workorder?.new" /></div>
          </div>

          <div v-if="prev.items.length" class="rounded-lg bg-slate-50 dark:bg-slate-700/40 p-3 text-sm">
            <div class="text-xs uppercase tracking-wide text-slate-400 mb-1">Positionen</div>
            <div v-for="(i, n) in prev.items" :key="n" class="font-mono text-xs">{{ i.action === 'configure' ? '⚙' : '→' }} {{ i.text }}</div>
          </div>
          <p v-for="w in prev.warnings" :key="w" class="text-sm text-amber-600 dark:text-amber-400">{{ w }}</p>
        </template>
      </template>
      <p v-if="busy" class="text-sm text-slate-400">Prüfe …</p>
    </div>
    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ result ? 'Schließen' : 'Abbrechen' }}</button>
      <button v-if="!result" :class="btnPrimary" :disabled="busy || !canCreate" @click="create">Auftrag anlegen</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import PathGraphic from './PathGraphic.vue'
import PortConfigFields from './PortConfigFields.vue'
import { api, errText, conflictOf } from '../api.js'
import { cableTypes, loadCableTypes } from '../catalog.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

/** Arbeitsplatz-Assistent: Dose → Patchfeld → freier Switchport, Profil/VLAN → Patchauftrag. ``preset``: {deviceId, portId}. */
const props = defineProps({ preset: { type: Object, default: null } })
defineEmits(['close'])

const outlets = ref([]), outletPorts = ref([]), outletId = ref(props.preset?.deviceId ?? null)
const endpoints = ref([]), endpointPorts = ref([]), endpointId = ref(null)
const profiles = ref([]), vlans = ref([]), drafts = ref([])
const f = reactive({ outlet_port_id: props.preset?.portId ?? null, switch_port_id: null, endpoint_port_id: null, cable_type: 'Cat6', cable_label: '',
                     length_m: null, color: '', workorder_id: null, workorder_title: '', use_reserved: false })
const cfg = reactive({ port_mode: '', access_vid: null, voice_vid: null, native_vid: null, allowed_vids: '', profile_id: null })
const prev = ref(null), result = ref(null), error = ref(''), busy = ref(false)

const canCreate = computed(() => prev.value && (prev.value.state === 'open' || (prev.value.state === 'connected' && cfg.port_mode)))
const n = v => (v === '' ? null : v)
const payload = dry => ({ ...f, endpoint_port_id: endpointId.value ? f.endpoint_port_id : null, dry_run: dry,
  cfg: cfg.port_mode ? { ...cfg, access_vid: n(cfg.access_vid), voice_vid: n(cfg.voice_vid), native_vid: n(cfg.native_vid) } : null })

async function check() {
  if (!f.outlet_port_id) return
  busy.value = true; error.value = ''
  try {
    prev.value = await api.workplaceWizard(payload(true))
    if (!f.switch_port_id && prev.value.switch_port) f.switch_port_id = prev.value.switch_port.port_id
  } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
async function create() {
  busy.value = true; error.value = ''
  try { result.value = await api.workplaceWizard(payload(false)) }
  catch (e) {
    const c = conflictOf(e)
    if (c && c.code === 'port_reserved' && !f.use_reserved && confirm(c.message)) { f.use_reserved = true; busy.value = false; return create() }
    error.value = errText(e)
  } finally { busy.value = false }
}
async function loadOutletPorts() {
  f.outlet_port_id = null; prev.value = null
  outletPorts.value = outletId.value ? (await api.device(outletId.value)).ports : []
  const front = outletPorts.value.find(p => !p.name.toLowerCase().endsWith('-back'))
  if (front) { f.outlet_port_id = front.id; check() }
}
async function loadEndpointPorts() {
  endpointPorts.value = endpointId.value ? (await api.device(endpointId.value)).ports : []
  f.endpoint_port_id = endpointPorts.value[0]?.id ?? null
  check()
}
let timer
watch(cfg, () => { clearTimeout(timer); timer = setTimeout(check, 300) })

onMounted(async () => {
  loadCableTypes()
  const [o, e, p, v, w] = await Promise.all([api.devices({ type: 'outlet', limit: 1000 }), api.devices({ type: 'endpoint', limit: 1000 }),
    api.portProfiles(), api.vlans(), api.workorders()]).catch(err => { error.value = errText(err); return [{ items: [] }, { items: [] }, [], [], []] })
  outlets.value = o.items; endpoints.value = e.items; profiles.value = p; vlans.value = v
  drafts.value = w.filter(x => ['draft', 'rework'].includes(x.status))
  if (outletId.value) { outletPorts.value = (await api.device(outletId.value)).ports; check() }
})
</script>
