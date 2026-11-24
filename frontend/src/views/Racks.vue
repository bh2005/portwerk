<template>
  <div class="max-w-6xl space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Racks &amp; Schränke</h1>
      <div class="flex items-center gap-3 flex-wrap">
        <div v-if="rack?.kind === 'rack'" class="inline-flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-600" role="group" aria-label="Ansicht">
          <button v-for="[k, l] in [['front', 'Vorderseite'], ['rear', 'Rückseite']]" :key="k" type="button" @click="view = k"
            class="px-3 py-1.5 text-sm transition-colors"
            :class="view === k ? 'bg-ks-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'">{{ l }}</button>
        </div>
        <select v-model="rackId" :class="inp" class="!w-72" @change="changeRack">
          <option :value="null" disabled>Rack wählen …</option>
          <option v-for="r in shownRacks" :key="r.id" :value="r.id">{{ kindLabel(r.kind) }}: {{ r.path }}<template v-if="r.rack_units"> ({{ r.rack_units }} HE)</template></option>
        </select>
      </div>
    </div>
    <!-- Filter für die Auswahl -->
    <div v-if="racks.length > 1" class="flex items-center gap-2 flex-wrap">
      <select v-model="fSite" :class="inp" class="!w-56" title="Standort"><option value="">alle Standorte</option><option v-for="s in siteChoices" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
      <select v-model="fKind" :class="inp" class="!w-48" title="Art"><option value="">alle Arten</option><option v-for="k in kindChoices" :key="k" :value="k">{{ kindLabel(k) }}</option></select>
      <input v-model="fText" :class="inp" class="!w-64" placeholder="Location suchen (Name, Pfad, Kennung) …" />
      <button v-if="fSite || fKind || fText" type="button" :class="btnLink" @click="fSite = ''; fKind = ''; fText = ''">Filter zurücksetzen</button>
      <span class="text-xs text-slate-400">{{ shownRacks.length }} von {{ racks.length }}</span>
    </div>
    <p v-if="loaded && racks.length && !shownRacks.length" class="text-sm text-slate-400">Keine Racks oder Schränke für diese Filter.</p>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <p v-if="notice" class="text-sm text-green-600">{{ notice }}</p>
    <p v-if="loaded && !racks.length" class="text-sm text-slate-400">Noch kein Rack, Schaltschrank oder keine Anlage angelegt. Lege unter „Standorte“ eine passende Location an.</p>

    <div v-if="rack" class="grid lg:grid-cols-5 gap-4">
      <!-- Schrank -->
      <!-- Ohne HE-Teilung (Anlage, Maschine, mobile Maschine, Schaltschrank ohne HE): Geräteliste -->
      <div v-if="!drawn" :class="card" class="p-4 lg:col-span-2">
        <div class="flex items-start justify-between gap-2 mb-1">
          <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ kindLabel(rack.kind) }} · {{ rack.path }}</h2>
          <button v-if="canPlace" type="button" :class="btnLink" @click="startList">+ Gerät platzieren</button>
        </div>
        <p class="text-xs text-slate-400 mb-3"><span v-if="rack.ident" class="font-mono text-slate-500">{{ rack.ident }} · </span>Keine HE-Teilung – die Geräte sind auf Hutschiene/Montageplatte bzw. frei montiert. Klick auf ein Gerät zeigt rechts die Portbelegung.</p>
        <p v-if="!devices.length" class="text-sm text-slate-400">Noch keine Geräte hier.</p>
        <ul class="text-sm divide-y divide-slate-100 dark:divide-slate-700">
          <li v-for="d in devices" :key="d.id"><button type="button" @click="select(d)" class="w-full text-left py-1.5 px-1 rounded hover:bg-slate-50 dark:hover:bg-slate-700/40"
            :class="selected?.id === d.id ? 'bg-ks-50 dark:bg-ks-900/30' : ''"><span class="font-medium text-slate-800 dark:text-slate-100">{{ d.hostname }}</span>
            <span class="text-xs text-slate-400"> · {{ typeLabel(d.type) }}<template v-if="d.status === 'planned'"> · geplant</template></span></button></li>
        </ul>
      </div>

      <div v-if="drawn" :class="card" class="p-4 lg:col-span-2">
        <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-1">{{ kindLabel(rack.kind) }} · {{ rack.path }}<template v-if="rack.kind === 'rack'"> · {{ view === 'front' ? 'Vorderseite' : 'Rückseite' }}</template></h2>
        <p v-if="rack.ident" class="text-xs font-mono text-slate-500 mb-1">{{ rack.ident }}</p>
        <p class="text-xs text-slate-400 mb-3">Klick auf ein Gerät zeigt rechts die Portbelegung.<template v-if="canPlace"> Klick auf einen freien Platz platziert ein neues Gerät, Klick in einen Seitenkanal ein Hochkant-Gerät (z. B. PDU).</template>
          Links/rechts gelten aus Sicht dieser Ansicht.</p>
        <div class="flex border-2 border-slate-400 dark:border-slate-500 rounded bg-slate-100 dark:bg-slate-900 min-w-[300px]">
          <!-- Seitenkanal links -->
          <div class="relative w-9 shrink-0 border-r border-slate-300 dark:border-slate-600 bg-slate-200/60 dark:bg-slate-800/60"
            :style="{ height: total * UNIT + 'px' }" :class="canPlace ? 'cursor-pointer hover:bg-ks-50 dark:hover:bg-ks-900/20' : ''" :title="canPlace ? 'Seitenkanal links – Hochkant-Gerät platzieren' : ''"
            @click.self="askVertical('left')">
            <button v-for="d in channel('left')" :key="d.id" type="button" @click.stop="select(d)" :title="`${d.hostname} (hochkant)`"
              class="absolute inset-x-0.5 rounded text-[10px] font-medium text-white overflow-hidden flex items-center justify-center"
              :class="[deviceColor(d), selected?.id === d.id ? 'ring-2 ring-ks-300' : '']" :style="vStyle(d)">
              <span class="[writing-mode:vertical-rl] rotate-180 whitespace-nowrap">{{ d.hostname }}</span></button>
          </div>

          <!-- 19-Zoll-Bereich -->
          <div class="flex-1 min-w-0">
            <div v-for="row in rows" :key="row.u" class="flex border-b border-slate-200 dark:border-slate-700 last:border-b-0" :style="{ height: row.span * UNIT + 'px' }">
              <div class="w-8 text-[10px] text-slate-400 text-right pr-1.5 pt-0.5 flex-shrink-0 border-r border-slate-200 dark:border-slate-700">{{ row.u }}</div>
              <button v-if="row.device" type="button" @click="select(row.device)"
                class="flex-1 px-2 flex items-center text-xs font-medium text-white overflow-hidden whitespace-nowrap text-left transition-colors"
                :class="[deviceColor(row.device), selected?.id === row.device.id ? 'ring-2 ring-offset-1 ring-ks-400 dark:ring-offset-slate-900' : '']">
                {{ row.device.hostname }} <span class="ml-2 opacity-70 font-normal">{{ typeLabel(row.device.type) }} · {{ row.device.height_u }} HE<template v-if="row.device.mount_side === 'both'"> · durchgehend</template><template v-if="row.device.status === 'planned'"> · geplant</template></span>
              </button>
              <button v-else-if="canPlace" type="button" @click="askPlace(row.u)" title="Freier Platz – neues Gerät platzieren"
                class="flex-1 text-left px-2 text-[11px] text-transparent hover:text-ks-600 hover:bg-ks-50 dark:hover:bg-ks-900/20 transition-colors">+ Gerät platzieren</button>
              <div v-else class="flex-1"></div>
            </div>
          </div>

          <!-- Seitenkanal rechts -->
          <div class="relative w-9 shrink-0 border-l border-slate-300 dark:border-slate-600 bg-slate-200/60 dark:bg-slate-800/60"
            :style="{ height: total * UNIT + 'px' }" :class="canPlace ? 'cursor-pointer hover:bg-ks-50 dark:hover:bg-ks-900/20' : ''" :title="canPlace ? 'Seitenkanal rechts – Hochkant-Gerät platzieren' : ''"
            @click.self="askVertical('right')">
            <button v-for="d in channel('right')" :key="d.id" type="button" @click.stop="select(d)" :title="`${d.hostname} (hochkant)`"
              class="absolute inset-x-0.5 rounded text-[10px] font-medium text-white overflow-hidden flex items-center justify-center"
              :class="[deviceColor(d), selected?.id === d.id ? 'ring-2 ring-ks-300' : '']" :style="vStyle(d)">
              <span class="[writing-mode:vertical-rl] rotate-180 whitespace-nowrap">{{ d.hostname }}</span></button>
          </div>
        </div>
      </div>

      <!-- Rechts: Portbelegung des gewählten Geräts bzw. Geräte ohne Position -->
      <div class="lg:col-span-3 space-y-4">
        <div v-if="selected" :class="card" class="p-4">
          <div class="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ selected.hostname }}</h2>
              <p class="text-xs text-slate-400">{{ typeLabel(selected.type) }} · {{ [selected.vendor, selected.model].filter(Boolean).join(' ') || 'kein Modell' }} · {{ mountText(selected) }}
                <template v-if="selected.mgmt_ip"> · {{ selected.mgmt_ip }}</template></p>
            </div>
            <div class="flex gap-3 items-center">
              <a v-if="checkmkUrl(selected)" :href="checkmkUrl(selected)" target="_blank" rel="noopener" :class="btnLink" title="Host-Seite in Checkmk öffnen">In Checkmk öffnen ↗</a>
              <router-link :to="`/devices/${selected.id}`" :class="btnLink">Details öffnen →</router-link>
              <button :class="btnLink" @click="selected = null; ports = []">Schließen</button>
            </div>
          </div>
          <p v-if="portsLoading" class="text-sm text-slate-400 mt-3">Lade Ports …</p>
          <p v-else-if="!ports.length" class="text-sm text-slate-400 mt-3">Dieses Gerät hat keine Ports.</p>
          <template v-else>
            <div class="flex items-center gap-3 mt-3 text-xs">
              <span class="text-slate-500">{{ usedPorts }} von {{ ports.length }} Ports belegt</span>
              <span class="flex-1 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"><span class="block h-full bg-ks-500" :style="{ width: (100 * usedPorts / ports.length) + '%' }"></span></span>
              <select v-model="portFilter" :class="inp" class="!w-28 !py-1 !text-xs"><option value="all">alle</option><option value="used">belegt</option><option value="free">frei</option></select>
            </div>
            <div class="mt-2 max-h-[28rem] overflow-y-auto">
              <table class="w-full text-sm">
                <thead class="sticky top-0 bg-white dark:bg-slate-800"><tr><th :class="th">Port</th><th :class="th">Medium</th><th :class="th">Verbunden mit</th><th :class="th">Kabel</th></tr></thead>
                <tbody>
                  <tr v-for="p in shownPorts" :key="p.id" class="border-t border-slate-100 dark:border-slate-700">
                    <td :class="td" class="font-mono text-xs">{{ p.name }}</td>
                    <td :class="td" class="text-xs text-slate-500">{{ p.medium }}<template v-if="p.speed_mbps"> · {{ fmtSpeed(p.speed_mbps) }}</template></td>
                    <td :class="td">
                      <template v-if="p.cable"><router-link :to="`/devices/${p.cable.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ p.cable.device_hostname }}</router-link><span class="font-mono text-xs text-slate-500">:{{ p.cable.port_name }}</span></template>
                      <span v-else-if="p.peer_port_name" class="text-xs text-slate-400">durchgeschleift: {{ p.peer_port_name }}</span>
                      <span v-else class="text-xs text-green-600 dark:text-green-400">frei</span>
                      <button v-if="!p.cable && canPlace" type="button" :class="btnLink" class="ml-2" @click="startCable(p)">verbinden …</button>
                    </td>
                    <td :class="td" class="text-xs text-slate-500"><template v-if="p.cable"><span class="font-mono text-slate-700 dark:text-slate-200">{{ p.cable.cable_label }}</span> {{ p.cable.cable_type }}<template v-if="p.cable.length_m"> · {{ p.cable.length_m }} m</template></template></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>

        <div :class="card" class="p-4">
          <template v-if="drawn && onRail.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Auf Hutschiene / Montageplatte</h2>
            <ul class="text-sm space-y-1 mb-4">
              <li v-for="x in onRail" :key="x.id"><button type="button" class="text-ks-600 dark:text-ks-400 hover:underline" @click="select(x)">{{ x.hostname }}</button>
                <span class="text-xs text-slate-400"> · {{ typeLabel(x.type) }}</span></li>
            </ul>
          </template>
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Ohne Position</h2>
          <p v-if="!loose.length" class="text-sm text-slate-400">Alle Geräte haben eine HE-Position{{ drawn ? '' : ' bzw. keine HE-Teilung' }}.</p>
          <ul class="text-sm space-y-1">
            <li v-for="x in loose" :key="x.id"><button type="button" class="text-ks-600 dark:text-ks-400 hover:underline" @click="select(x)">{{ x.hostname }}</button>
              <span class="text-xs text-slate-400"> · {{ typeLabel(x.type) }}</span></li>
          </ul>
          <p v-if="drawn" class="text-xs text-slate-400 mt-3">{{ used }} von {{ rack.rack_units || '?' }} HE{{ rack.kind === 'rack' ? ` (${view === 'front' ? 'Vorderseite' : 'Rückseite'})` : '' }} belegt.</p>
        </div>
      </div>
    </div>

    <!-- Frage: freien Platz belegen -->
    <ModalDialog v-if="place" :title="place.slot ? `Seitenkanal ${place.slot === 'left' ? 'links' : 'rechts'} (${view === 'front' ? 'vorne' : 'hinten'})` : `HE ${place.u} ist frei (${view === 'front' ? 'Vorderseite' : 'Rückseite'})`" @close="place = null">
      <p class="text-sm text-slate-600 dark:text-slate-300">{{ place.slot ? 'Soll hier ein Hochkant-Gerät (z. B. PDU) platziert werden?' : 'Soll hier ein neues Gerät platziert werden?' }}</p>
      <template #footer>
        <button :class="btnGhost" @click="place = null">Nein</button>
        <template v-if="place.slot">
          <button :class="btnPrimary" @click="startWizard('vertical')">Ja, Hochkant-Gerät platzieren</button>
        </template>
        <template v-else>
          <button :class="btnGhost" @click="startWizard('placeholder')">Platzhalter (Kabelführung, Blindblende …)</button>
          <button :class="btnGhost" @click="startWizard('patchpanel')">Patchfeld</button>
          <button :class="btnPrimary" @click="startWizard('switch')">Ja, Gerät platzieren</button>
        </template>
      </template>
    </ModalDialog>

    <CableWizard v-if="cableWiz" :preset-device-id="selected.id" :preset-port-id="cableWiz.portId" @close="cableWiz = null" @done="cableDone" />

    <DeviceWizard v-if="wizard" :kind="wizard.kind" :location-id="rackId" :rack-position="wizard.u" :mount-side="view" :side-slot="wizard.slot || ''"
      :title="{ switch: 'Assistent: Gerät platzieren', patchpanel: 'Assistent: Patchfeld platzieren', placeholder: 'Assistent: Platzhalter einplanen', vertical: 'Assistent: Hochkant-Gerät (PDU …) platzieren' }[wizard.kind]"
      @close="wizard = null" @done="wizardDone" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import DeviceWizard from '../components/DeviceWizard.vue'
import CableWizard from '../components/CableWizard.vue'
import { api, errText, canWriteMaster, hasRole } from '../api.js'
import { checkmkUrl, loadCheckmk } from '../checkmk.js'
import { inp, card, th, td, btnPrimary, btnGhost, btnLink, typeLabel, fmtSpeed, PASSIVE_TYPES, mountLabel, PLACE_KINDS, CONTAINER_KINDS, kindLabel } from '../ui.js'

const UNIT = 26                      // Pixel pro Höheneinheit
const view = ref('front')            // Ansicht: Vorderseite oder Rückseite
const racks = ref([]), rackId = ref(null), devices = ref([])
const sites = ref([]), fSite = ref(''), fKind = ref(''), fText = ref('')
const siteChoices = computed(() => sites.value.filter(s => racks.value.some(r => r.site_id === s.id)))
const kindChoices = computed(() => [...new Set(racks.value.map(r => r.kind))])
const shownRacks = computed(() => {
  const q = fText.value.trim().toLowerCase()
  return racks.value.filter(r => (!fSite.value || r.site_id === fSite.value) && (!fKind.value || r.kind === fKind.value) &&
    (!q || `${r.path} ${r.ident || ''} ${r.name}`.toLowerCase().includes(q)))
})
// Wird das gewählte Rack ausgefiltert, springt die Auswahl auf den ersten Treffer
watch(shownRacks, async l => { if (l.length && !l.some(r => r.id === rackId.value)) { rackId.value = l[0].id; await changeRack() } })
const error = ref(''), notice = ref(''), loaded = ref(false)
const rack = computed(() => racks.value.find(r => r.id === rackId.value) || null)
const selected = ref(null), ports = ref([]), portsLoading = ref(false), portFilter = ref('all')
const place = ref(null), wizard = ref(null), cableWiz = ref(null)
const canPlace = canWriteMaster() || hasRole('planer')

// Was in der gewählten Ansicht sichtbar ist: Geräte dieser Seite und durchgehende
const inView = d => d.mount_side === view.value || d.mount_side === 'both'
const drawn = computed(() => !!rack.value && CONTAINER_KINDS.includes(rack.value.kind) && !!rack.value.rack_units)      // nur Gehäuse mit HE werden gezeichnet
const horizontal = computed(() => devices.value.filter(d => d.orientation === 'horizontal'))
const onRail = computed(() => devices.value.filter(d => d.orientation === 'din_rail'))
const placed = computed(() => horizontal.value.filter(x => x.rack_position && inView(x)))
const loose = computed(() => drawn.value ? horizontal.value.filter(x => !x.rack_position) : [])
const used = computed(() => placed.value.reduce((n, x) => n + x.height_u, 0))
const usedPorts = computed(() => ports.value.filter(p => p.cable).length)
const shownPorts = computed(() => ports.value.filter(p => portFilter.value === 'all' || (portFilter.value === 'used' ? p.cable : !p.cable)))
const total = computed(() => rack.value?.rack_units || Math.max(1, ...devices.value.filter(x => x.rack_position).map(x => x.rack_position + x.height_u - 1)))

const channel = slot => devices.value.filter(d => d.orientation === 'vertical' && d.side_slot === slot && inView(d))
// Hochkant-Gerät: Lage im Kanal (HE 1 unten); ohne Position über die ganze Höhe
const vStyle = d => {
  const pos = d.rack_position || 1, h = d.rack_position ? d.height_u : total.value
  return { top: (total.value - (pos + h - 1)) * UNIT + 'px', height: h * UNIT - 2 + 'px' }
}
const deviceColor = d => PASSIVE_TYPES.includes(d.type)
  ? 'bg-slate-400 hover:bg-slate-500 dark:bg-slate-600 dark:hover:bg-slate-500'
  : (d.status === 'planned' ? 'bg-amber-500 hover:bg-amber-600' : (d.type === 'pdu' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-ks-600 hover:bg-ks-700'))
const mountText = d => d.orientation === 'vertical'
  ? `hochkant, ${mountLabel(d.mount_side)} ${d.side_slot === 'left' ? 'links' : 'rechts'}${d.rack_position ? `, HE ${d.rack_position}–${d.rack_position + d.height_u - 1}` : ', volle Höhe'}`
  : `${d.rack_position ? `HE ${d.rack_position}${d.height_u > 1 ? '–' + (d.rack_position + d.height_u - 1) : ''}` : 'ohne HE'}, ${mountLabel(d.mount_side)}`

// Zeilen von oben (höchste HE) nach unten; ein mehrhöhiges Gerät belegt eine Zeile mit span > 1
const rows = computed(() => {
  const out = []
  for (let u = total.value; u >= 1; u--) {
    const dev = placed.value.find(x => x.rack_position + x.height_u - 1 === u)
    if (dev) { out.push({ u, device: dev, span: dev.height_u }); u -= dev.height_u - 1 }
    else out.push({ u, device: null, span: 1 })
  }
  return out
})

async function select(d) {
  if (selected.value?.id === d.id) { selected.value = null; ports.value = []; return }
  selected.value = d; portFilter.value = 'all'; portsLoading.value = true; ports.value = []
  try { ports.value = (await api.device(d.id)).ports } catch (e) { error.value = errText(e) } finally { portsLoading.value = false }
}

async function load() {
  try {
    const r = await api.devices({ location_id: rackId.value, limit: 1000 })
    // Geräte untergeordneter Locations gehören nicht in die Schrankansicht
    devices.value = r.items.filter(x => x.location_id === rackId.value)
    error.value = ''
  } catch (e) { error.value = errText(e) }
}
async function changeRack() { selected.value = null; ports.value = []; notice.value = ''; if (rack.value?.kind !== 'rack') view.value = 'front'; await load() }
function startList() { wizard.value = { kind: 'switch', u: null, slot: '' } }

function askPlace(u) { place.value = { u, slot: '' } }
function askVertical(slot) { if (canPlace) place.value = { u: 1, slot } }
function startWizard(kind) { wizard.value = { kind, u: place.value.slot ? 1 : place.value.u, slot: place.value.slot }; place.value = null }
async function wizardDone(r) {
  wizard.value = null
  notice.value = r.workorder
    ? `„${r.device.hostname}“ wurde als geplant angelegt – Patchauftrag ${r.workorder.number}${r.workorder.removal_order ? ` (Voraussetzung: Rückbau ${r.workorder.removal_order.number})` : ''}.`
    : `„${r.device.hostname}“ wurde angelegt${r.cable_ids?.length ? ` und mit ${r.cable_ids.length} Kabel(n) verkabelt` : ''}.`
  await load()
}
function startCable(p) { cableWiz.value = { portId: p.id } }
async function cableDone(r) {
  cableWiz.value = null
  notice.value = r.workorder ? `Kabel als Position in ${r.workorder.number} angelegt.` : 'Kabel angelegt.'
  if (selected.value) { portsLoading.value = true; try { ports.value = (await api.device(selected.value.id)).ports } finally { portsLoading.value = false } }
}

const route = useRoute()
// Sprung aus der Schnellsuche: /racks?device=ID wählt Rack und Gerät, /racks?location=ID das Rack
async function applyQuery() {
  const dev = Number(route.query.device), loc = Number(route.query.location)
  if (dev || loc) { fSite.value = ''; fKind.value = ''; fText.value = '' }                      // Sprungziel soll nicht durch einen Filter verdeckt sein
  try {
    if (dev) {
      const d = await api.device(dev)
      if (d.location_id && racks.value.some(r => r.id === d.location_id)) {
        if (rackId.value !== d.location_id) { rackId.value = d.location_id; selected.value = null; ports.value = []; await load() }
        if (d.mount_side === 'rear') view.value = 'rear'; else if (d.mount_side === 'front') view.value = 'front'
        const inRack = devices.value.find(x => x.id === dev)
        if (inRack) { selected.value = null; await select(inRack) }
      }
    } else if (loc && racks.value.some(r => r.id === loc) && rackId.value !== loc) { rackId.value = loc; await changeRack() }
  } catch (e) { error.value = errText(e) }
}
watch(() => [route.query.device, route.query.location], () => { if (racks.value.length) applyQuery() })

onMounted(async () => {
  loadCheckmk()
  try {
    try { sites.value = await api.sites() } catch { /* Filter ohne Standortnamen */ }
    racks.value = (await api.locations()).filter(l => PLACE_KINDS.includes(l.kind) && l.kind !== 'room')
    if (racks.value.length) { rackId.value = racks.value[0].id; await load(); await applyQuery() }
  } catch (e) { error.value = errText(e) }
  loaded.value = true
})
</script>
