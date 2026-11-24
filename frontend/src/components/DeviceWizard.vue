<template>
  <ModalDialog wide :title="title" :error="error" @close="$emit('close')">
    <!-- Fortschritt -->
    <ol class="flex items-center gap-2 text-xs mb-1 flex-wrap">
      <li v-for="(l, i) in STEPS" :key="l" class="flex items-center gap-2">
        <span class="w-5 h-5 rounded-full flex items-center justify-center font-semibold"
          :class="i === step ? 'bg-ks-600 text-white' : i < step ? 'bg-green-500 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-500'">{{ i < step ? '✓' : i + 1 }}</span>
        <span :class="i === step ? 'text-slate-800 dark:text-slate-100 font-medium' : 'text-slate-400'">{{ l }}</span>
        <span v-if="i < STEPS.length - 1" class="text-slate-300">—</span>
      </li>
    </ol>

    <!-- 1: Modell -->
    <div v-if="stepKey === 'model'" class="space-y-3">
      <p class="text-sm text-slate-500">{{ placeholder
        ? 'Platzhalter belegen Rackplatz ohne Ports, z. B. Kabelführung, Blindblende oder Fachboden. Die Vorlagen stehen im Katalog.'
        : (isPanel ? 'Wähle eine Patchfeld-Vorlage (Cat6A oder LWL, 8/12/24 Ports). Jeder Port hat Vorder- und Rückseite, bereits miteinander verknüpft.'
          : 'Wähle ein Modell aus dem Katalog – die Ports werden daraus erzeugt. Fehlt das Modell, lege es unter „Katalog“ an oder nutze eigene Ports.') }}</p>
      <input v-model="q" :class="inp" placeholder="Suchen (Hersteller, Modell, Artikelnr.) …" @input="loadModels" />
      <div class="max-h-64 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
        <button v-for="m in models" :key="m.id" type="button" @click="pickModel(m)"
          class="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/40"
          :class="form.model_id === m.id ? 'bg-ks-50 dark:bg-ks-900/30' : ''">
          <span class="font-medium text-slate-800 dark:text-slate-100">{{ m.vendor }} {{ m.model }}</span>
          <span class="text-xs text-slate-400"> · {{ typeLabel(m.type) }} · {{ m.height_u }} HE<template v-if="!placeholder"> · {{ portSummary(m) }}</template></span>
          <span v-if="m.description" class="block text-xs text-slate-400">{{ m.description }}</span>
        </button>
        <p v-if="!models.length" class="px-3 py-4 text-sm text-slate-400">Keine Modelle gefunden.</p>
      </div>
      <template v-if="!placeholder">
        <button type="button" class="text-xs text-ks-600 dark:text-ks-400 hover:underline" @click="pickCustom">Ohne Katalog: eigene Ports angeben</button>
        <div v-if="custom && isPanel" class="grid grid-cols-4 gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/40">
          <div><label :class="lbl">Hersteller</label><input v-model="form.vendor" :class="inp" /></div>
          <div><label :class="lbl">Modell</label><input v-model="form.model" :class="inp" /></div>
          <div><label :class="lbl">Höhe (HE)</label><input v-model.number="form.height_u" type="number" min="1" max="50" :class="inp" /></div>
          <div></div>
          <div><label :class="lbl">Ports (je Vorder- + Rückseite)</label><input v-model.number="custom.count" type="number" min="1" max="96" :class="inp" /></div>
          <div><label :class="lbl">Medium</label><select v-model="custom.medium" :class="inp"><option value="RJ45">Kupfer (RJ45)</option><option value="LWL">LWL</option></select></div>
        </div>
        <div v-else-if="custom" class="grid grid-cols-4 gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/40">
          <div><label :class="lbl">Hersteller</label><input v-model="form.vendor" :class="inp" /></div>
          <div><label :class="lbl">Modell</label><input v-model="form.model" :class="inp" /></div>
          <div><label :class="lbl">Höhe (HE)</label><input v-model.number="form.height_u" type="number" min="1" max="50" :class="inp" /></div>
          <div></div>
          <div><label :class="lbl">Kupferports (RJ45)</label><input v-model.number="custom.rj45" type="number" min="0" max="512" :class="inp" /></div>
          <div><label :class="lbl">SFP-Ports</label><input v-model.number="custom.sfp" type="number" min="0" max="64" :class="inp" /></div>
          <div><label :class="lbl">SFP+-Ports</label><input v-model.number="custom.sfpp" type="number" min="0" max="64" :class="inp" /></div>
        </div>
      </template>
      <p v-if="selection" class="text-sm text-green-600 dark:text-green-400">Gewählt: {{ selection }}</p>
    </div>

    <!-- 2: Ort -->
    <div v-if="stepKey === 'place'" class="space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Standort</label>
          <select v-model="siteId" :class="inp" @change="loadLocations"><option :value="null" disabled>wählen …</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
        <div><label :class="lbl">Rack / Location</label>
          <select v-model="form.location_id" :class="inp" @change="onLocation"><option :value="null" disabled>wählen …</option>
            <option v-for="l in locations" :key="l.id" :value="l.id">{{ kindLabel(l.kind) }}: {{ l.path }}<template v-if="l.rack_units"> ({{ l.rack_units }} HE)</template></option></select></div>
      </div>
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">Einbau</label>
          <select v-model="form.orientation" :class="inp" @change="mountChanged"><option v-for="[k, l] in orientationOptions" :key="k" :value="k">{{ l }}</option></select></div>
        <div v-if="loc?.kind === 'rack' && form.orientation !== 'din_rail'"><label :class="lbl">Seite</label>
          <select v-model="form.mount_side" :class="inp" @change="mountChanged"><option value="front">Vorderseite</option><option value="rear">Rückseite</option>
            <option v-if="form.orientation === 'horizontal'" value="both">beide Seiten (durchgehend)</option></select></div>
        <div v-if="form.orientation === 'vertical'"><label :class="lbl">Seitenkanal</label>
          <select v-model="form.side_slot" :class="inp" @change="mountChanged"><option value="left">links</option><option value="right">rechts</option></select>
          <p class="text-[11px] text-slate-400 mt-1">aus Sicht der {{ form.mount_side === 'rear' ? 'Rückseite' : 'Vorderseite' }}</p></div>
      </div>
      <p v-if="form.orientation === 'vertical' && form.location_id && loc?.kind !== 'rack'" class="text-xs text-red-500 dark:text-red-400">Hochkant-Geräte brauchen ein Rack.</p>
      <div v-if="isRack">
        <label :class="lbl">{{ form.orientation === 'vertical' ? 'Beginnt bei HE (Länge höchstens bis zur Rackhöhe)' : 'Position im Rack (unterste HE)' }}</label>
        <div class="flex gap-3 items-center flex-wrap">
          <select v-model="form.rack_position" :class="inp" class="!w-48" @change="conflict = null"><option :value="null">ohne Position</option>
            <option v-for="p in startChoices" :key="p" :value="p">HE {{ p }}<template v-if="heightU > 1"> – {{ p + heightU - 1 }}</template><template v-if="!slots.free_starts.includes(p)"> (belegt)</template></option></select>
          <span class="text-xs text-slate-400">{{ slots.free_starts?.length ? `${slots.free_starts.length} freie Positionen für ${heightU} HE` : 'Keine freie Position für diese Höhe' }}</span>
        </div>
        <p class="text-[11px] text-slate-400 mt-1">Ist die gewählte HE belegt, fragt der Assistent später, ob das alte Gerät zurückgebaut werden soll.</p>
        <div class="mt-2 text-xs text-slate-500" v-if="slots.devices?.length">Belegt:
          <span v-for="d in slots.devices" :key="d.id" class="inline-block mr-2" :class="d.pending_removal ? 'line-through opacity-60' : ''">{{ d.hostname }} (HE {{ d.rack_position }}<template v-if="d.height_u > 1">–{{ d.rack_position + d.height_u - 1 }}</template>)</span></div>
      </div>
      <p v-else-if="form.location_id" class="text-xs text-slate-400">Hier gibt es keine HE-Teilung – das Gerät wird auf Hutschiene/Montageplatte bzw. frei in „{{ loc?.name }}“ montiert und bekommt keine HE-Position.</p>
    </div>

    <!-- 3: Gerät -->
    <div v-if="stepKey === 'device'" class="space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Hostname {{ passive ? '(optional)' : '*' }}</label><input v-model="form.hostname" :class="inp" :placeholder="passive ? 'leer = automatischer Name (z. B. KF-R1-HE5)' : (isPanel ? 'z. B. PF-R1-HE1' : 'z. B. sw-eg-01')" />
          <p v-if="nameTaken" class="text-xs text-red-500 mt-1 dark:text-red-400">Dieser Hostname existiert bereits.</p></div>
        <div v-if="!passive && !isPanel"><label :class="lbl">Mgmt-IP</label><input v-model="form.mgmt_ip" :class="inp" /></div>
        <div v-if="!passive && !isPanel"><label :class="lbl">Seriennummer</label><input v-model="form.serial" :class="inp" /></div>
        <div><label :class="lbl">Status</label>
          <select v-model="form.status" :class="inp"><option value="active">aktiv (eingebaut)</option><option value="planned">geplant</option></select>
          <p class="text-[11px] text-slate-400 mt-1">Bei Umsetzung per Patchauftrag ist das Gerät immer „geplant“, bis der Auftrag bestätigt ist.</p></div>
      </div>
      <div><label :class="lbl">Notiz</label><input v-model="form.note" :class="inp" /></div>
    </div>

    <!-- 4: Verkabelung -->
    <div v-if="stepKey === 'cable'" class="space-y-3">
      <p v-if="!portNames.length" class="text-sm text-slate-500">Dieses Gerät hat keine Ports – es gibt nichts zu verkabeln.</p>
      <PortMappingEditor v-else-if="isPanel" v-model="mappings" :front-names="frontNames" :back-names="backNames" :hostname="form.hostname.trim()" :site-id="siteId" />
      <template v-else>
        <label class="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="withUplink" /> Einen Port gleich verbinden (z. B. Uplink zum Patchfeld oder Core)</label>
        <template v-if="withUplink">
          <div class="grid grid-cols-2 gap-3">
            <div><label :class="lbl">Port am neuen Gerät</label>
              <select v-model="uplink.port_name" :class="inp"><option v-for="n in portNames" :key="n" :value="n">{{ n }}</option></select></div>
            <div><label :class="lbl">Zielgerät suchen</label><input v-model="targetQ" :class="inp" placeholder="Hostname (mind. 2 Zeichen)" @input="searchTargets" /></div>
          </div>
          <div v-if="targets.length" class="max-h-32 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
            <button v-for="d in targets" :key="d.id" type="button" @click="pickTarget(d)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/40"
              :class="target?.id === d.id ? 'bg-ks-50 dark:bg-ks-900/30' : ''">{{ d.hostname }} <span class="text-xs text-slate-400">· {{ typeLabel(d.type) }} · {{ d.location_path }}</span></button>
          </div>
          <div v-if="target"><label :class="lbl">Zielport an {{ target.hostname }}</label>
            <select v-model="uplink.target_port_id" :class="inp" @change="conflict = null"><option :value="null" disabled>wählen …</option>
              <option v-for="p in targetPorts" :key="p.id" :value="p.id">{{ p.name }}{{ p.cable ? ` – belegt (${p.cable.device_hostname}:${p.cable.port_name})` : '' }}</option></select>
            <p class="text-[11px] text-slate-400 mt-1">Ein belegter Port ist wählbar: Der Assistent fragt dann, ob der alte Patch zurückgebaut werden soll.</p></div>
          <div class="grid grid-cols-3 gap-3">
            <div><label :class="lbl">Kabelart</label><select v-model="uplink.cable_type" :class="inp"><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
            <div><label :class="lbl">Kabelnummer</label><input v-model="uplink.cable_label" :class="inp" /></div>
            <div><label :class="lbl">Länge (m)</label><input v-model.number="uplink.length_m" type="number" min="0" step="0.5" :class="inp" /></div>
            <div v-if="countLabel(uplink.cable_type)"><label :class="lbl">{{ countLabel(uplink.cable_type) }}</label><input v-model.number="uplink.fiber_count" type="number" min="1" :class="inp" /></div>
            <div><label :class="lbl">Farbe</label><input v-model="uplink.color" :class="inp" /></div>
          </div>
        </template>
      </template>
    </div>

    <!-- 5: Umsetzung und Prüfen -->
    <div v-if="stepKey === 'mode'" class="space-y-3">
      <div v-if="canDirect && canOrder" class="space-y-1">
        <label :class="lbl">Umsetzung</label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="direct" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>Sofort anlegen</b> – Gerät, Ports und Kabel werden direkt in den Bestand geschrieben.</span></label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="workorder" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>Per Patchauftrag</b> – das Gerät wird als „geplant“ angelegt; Einbau{{ (withUplink || panelLinks.links.length) ? ' und Kabel werden Positionen' : ' wird eine Position' }} im Auftrag (Freigabe → Ausführung → Bestätigung).</span></label>
      </div>
      <p v-else class="text-sm text-slate-500">Umsetzung: <b>{{ canOrder && !canDirect ? 'per Patchauftrag (du darfst Stammdaten nicht direkt ändern)' : 'sofort' }}</b></p>
      <div v-if="form.mode === 'workorder'" class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Patchauftrag</label>
          <select v-model="form.workorder_id" :class="inp" @change="check"><option :value="null">Neuen Auftrag anlegen</option>
            <option v-for="w in openOrders" :key="w.id" :value="w.id">{{ w.number }} · {{ w.title }}</option></select></div>
        <div v-if="!form.workorder_id"><label :class="lbl">Titel des neuen Auftrags</label><input v-model="form.workorder_title" :class="inp" :placeholder="`Einbau ${form.hostname || selection}`" @change="check" /></div>
      </div>

      <!-- Rückfrage bei Konflikt -->
      <div v-if="conflict" class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3 space-y-2">
        <p class="text-sm font-medium text-amber-800 dark:text-amber-300">{{ conflict.code === 'slot_busy' ? 'Die Höheneinheiten sind belegt' : conflict.code === 'port_reserved' ? 'Zielport reserviert bzw. schon verplant' : (conflict.conflicts.length > 1 ? `${conflict.conflicts.length} Zielports sind belegt` : 'Der Zielport ist belegt') }}</p>
        <p class="text-sm text-amber-900 dark:text-amber-200">{{ conflict.message }}</p>
        <div class="flex gap-2">
          <button :class="btnPrimary" @click="resolveConflict(true)">{{ conflict.code === 'port_reserved' ? 'Ja, trotzdem verwenden' : 'Ja, zurückbauen' }}</button>
          <button :class="btnGhost" @click="resolveConflict(false)">Nein, andere Wahl treffen</button>
        </div>
      </div>

      <p v-if="busy" class="text-sm text-slate-400">Prüfe …</p>
      <div v-else-if="preview" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-sm space-y-1">
        <div v-if="preview.device.temporary_hostname" class="text-xs text-amber-700 dark:text-amber-400">Das Gerät heißt bis zum Rückbau des alten Geräts „{{ preview.device.temporary_hostname }}“ und übernimmt den Namen „{{ preview.device.hostname }}“ danach automatisch.</div>
        <div><b>{{ preview.device.hostname }}</b> <span class="text-slate-400">· {{ [preview.device.vendor, preview.device.model].filter(Boolean).join(' ') || typeLabel(preview.device.type) }} · {{ preview.device.height_u }} HE · Status {{ statusLabel(preview.device.status) }}</span></div>
        <div class="text-slate-500">Ort: {{ preview.device.location_path }}<template v-if="preview.device.rack_position"> · HE {{ preview.device.rack_position }}<template v-if="preview.device.orientation === 'vertical'">–{{ preview.device.rack_position + preview.device.height_u - 1 }}</template></template>
          · {{ preview.device.orientation === 'vertical' ? `hochkant ${mountLabel(preview.device.mount_side)} ${preview.device.side_slot === 'left' ? 'links' : 'rechts'}` : mountLabel(preview.device.mount_side) }}</div>
        <div v-if="preview.ports.count" class="text-slate-500">{{ preview.ports.count }} Ports{{ isPanel ? ' (Vorder- und Rückseite)' : '' }}<template v-if="preview.ports.first.length"> ({{ preview.ports.first.join(', ') }}<template v-if="preview.ports.last.length"> … {{ preview.ports.last.join(', ') }}</template>)</template></div>
        <div v-if="preview.cables && preview.cables.length > 1" class="text-slate-500">{{ preview.cables.length }} Kabel ({{ preview.cables[0].via }}): {{ preview.cables[0].from }} ↔ {{ preview.cables[0].to }} … {{ preview.cables[preview.cables.length - 1].from }} ↔ {{ preview.cables[preview.cables.length - 1].to }} · {{ preview.cables[0].type }}</div>
        <div v-else-if="preview.cable" class="text-slate-500">Kabel ({{ preview.cable.via }}): {{ preview.cable.from }} ↔ {{ preview.cable.to }} · {{ preview.cable.type }}</div>
        <div v-if="preview.workorder" class="text-slate-500">Patchauftrag: {{ preview.workorder.existing ? `Positionen in ${preview.workorder.existing}` : `neu „${preview.workorder.new}“` }}</div>
        <div v-if="preview.removals" class="text-amber-700 dark:text-amber-400">Rückbau ({{ preview.removals.via }}):
          <span v-if="preview.removals.devices.length">Gerät {{ preview.removals.devices.join(', ') }}</span>
          <span v-if="preview.removals.cables.length"> Patch {{ preview.removals.cables.join(', ') }}</span>
          <span v-if="form.mode === 'workorder'"> – der neue Auftrag startet erst nach bestätigtem Rückbau.</span></div>
      </div>
    </div>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">Abbrechen</button>
      <button v-if="step > 0" :class="btnGhost" :disabled="busy" @click="back">Zurück</button>
      <button v-if="step < STEPS.length - 1" :class="btnPrimary" :disabled="!canNext" @click="next">Weiter</button>
      <button v-else :class="btnPrimary" :disabled="busy || !preview || !!conflict" @click="create">{{ busy ? '…' : 'Anlegen' }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import PortMappingEditor, { buildLinks } from './PortMappingEditor.vue'
import { api, errText, conflictOf, canWriteMaster, hasRole } from '../api.js'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'
import { inp, lbl, btnPrimary, btnGhost, typeLabel, statusLabel, PASSIVE_TYPES, mountLabel, PLACE_KINDS, CONTAINER_KINDS, kindLabel } from '../ui.js'

const props = defineProps({
  kind: { type: String, default: 'switch' },                 // 'switch' (Geräte mit Ports), 'patchpanel' (Patchfeld mit Vorder-/Rückseite) oder 'placeholder' (Kabelführung, Blindblende, Fachboden)
  title: { type: String, default: 'Assistent: Gerät platzieren' },
  locationId: { type: Number, default: null },               // Vorbelegung, z. B. aus der Rack-Ansicht
  rackPosition: { type: Number, default: null },
  mountSide: { type: String, default: '' },                  // Ansicht, aus der geplant wird (front | rear)
  sideSlot: { type: String, default: '' },                   // Seitenkanal (left | right) bei Hochkant-Einbau
})
const emit = defineEmits(['close', 'done'])

const placeholder = computed(() => props.kind === 'placeholder')
const isPanel = computed(() => props.kind === 'patchpanel')
const isVertical = computed(() => props.kind === 'vertical')
const STEPS = computed(() => placeholder.value ? ['Vorlage', 'Ort & Position', 'Platzhalter', 'Umsetzung']
  : isPanel.value ? ['Vorlage', 'Ort & Position', 'Patchfeld', 'Port-Zuordnung', 'Umsetzung'] : ['Modell', 'Ort & Position', 'Gerät', 'Verkabelung', 'Umsetzung'])
const keyOf = i => placeholder.value ? ['model', 'place', 'device', 'mode'][i] : ['model', 'place', 'device', 'cable', 'mode'][i]
const step = ref(0)
const stepKey = computed(() => keyOf(step.value))
const error = ref(''), busy = ref(false)
const q = ref(''), models = ref([]), custom = ref(null)
const sites = ref([]), siteId = ref(null), locations = ref([])
const slots = ref({ free_starts: [], devices: [] })
const withUplink = ref(false), targetQ = ref(''), targets = ref([]), target = ref(null), targetPorts = ref([])
const openOrders = ref([]), preview = ref(null), nameTaken = ref(false)
const picked = ref(null)
const conflict = ref(null)

const canDirect = canWriteMaster()
const canOrder = hasRole('planer')

const form = reactive({
  hostname: '', type: placeholder.value ? 'blank_panel' : (isPanel.value ? 'patchpanel' : 'switch'), model_id: null, vendor: '', model: '', height_u: null, location_id: props.locationId, rack_position: null,
  serial: '', mgmt_ip: '', note: '', status: 'active', mode: canDirect ? 'direct' : 'workorder', workorder_id: null, workorder_title: '',
  replace_devices: false, remove_old: false, use_reserved: false,
  // Einbaulage: Seite und Ausrichtung (hochkant = Seitenkanal, z. B. PDU)
  orientation: props.kind === 'vertical' ? 'vertical' : 'horizontal',
  mount_side: props.kind === 'vertical' ? (props.mountSide || 'rear') : (['placeholder', 'patchpanel'].includes(props.kind) ? (props.mountSide || 'front') : 'both'),
  side_slot: props.kind === 'vertical' ? (props.sideSlot || 'left') : '',
})
const uplink = reactive({ port_name: '', target_port_id: null, cable_type: 'Cat6', cable_label: '', length_m: null, fiber_count: null, color: '', note: '' })

const passive = computed(() => PASSIVE_TYPES.includes(form.type))
const mappings = ref([])
const backSuffix = computed(() => groups.value.find(g => g.dual)?.back_suffix || '-back')
const frontNames = computed(() => portNames.value.filter(n => !n.endsWith(backSuffix.value)))
const backNames = computed(() => portNames.value.filter(n => n.endsWith(backSuffix.value)))
const panelLinks = computed(() => isPanel.value ? buildLinks(mappings.value, { frontNames: frontNames.value, backNames: backNames.value, hostname: form.hostname.trim() || 'PF' }) : { links: [], error: '' })
const loc = computed(() => locations.value.find(l => l.id === form.location_id))
const isRack = computed(() => !!loc.value && CONTAINER_KINDS.includes(loc.value.kind) && !!loc.value.rack_units)      // Gehäuse mit HE-Teilung
const orientationOptions = computed(() => {
  const k = loc.value?.kind
  if (!k || k === 'rack') return [['horizontal', '19 Zoll (HE-Platz)'], ['vertical', 'Hochkant im Seitenkanal (0 HE, z. B. PDU)'], ['din_rail', 'Hutschiene / Montageplatte (ohne HE)']]
  if (k === 'wallrack' || k === 'cabinet') return [['horizontal', '19 Zoll (HE-Platz)'], ['din_rail', 'Hutschiene / Montageplatte (ohne HE)']]
  return [['din_rail', 'Montage in Anlage / Maschine / Raum (ohne HE)']]
})
const heightU = computed(() => form.height_u || picked.value?.height_u || 1)
const selection = computed(() => picked.value ? `${picked.value.vendor} ${picked.value.model}` : (custom.value ? 'eigene Ports' : ''))
const startChoices = computed(() => {
  const units = loc.value?.rack_units || 42
  return Array.from({ length: Math.max(0, units - heightU.value + 1) }, (_, i) => i + 1)
})

const portSummary = m => !m.ports.length ? 'keine Ports' : m.ports.map(g => `${g.count}× ${g.medium}${g.dual ? ' dual' : ''}`).join(', ')
const groups = computed(() => {
  if (picked.value) return picked.value.ports
  if (!custom.value) return []
  if (isPanel.value) return custom.value.count > 0 ? [{ prefix: custom.value.medium === 'LWL' ? 'F' : 'P', start: 1, count: custom.value.count, medium: custom.value.medium, speed_mbps: null, dual: true, back_suffix: '-back' }] : []
  const g = (prefix, n, medium, speed) => n > 0 ? [{ prefix, start: 1, count: n, medium, speed_mbps: speed, dual: false, back_suffix: '-back' }] : []
  return [...g('Port', custom.value.rj45, 'RJ45', 1000), ...g('SFP', custom.value.sfp, 'SFP', 1000), ...g('SFP+', custom.value.sfpp, 'SFP+', 10000)]
})
const portNames = computed(() => groups.value.flatMap(g => Array.from({ length: g.count }, (_, i) => g.prefix + (g.start + i)).flatMap(n => g.dual ? [n, n + g.back_suffix] : [n])))

async function loadModels() {
  try {
    models.value = await api.deviceModels(isVertical.value ? { orientation: 'vertical', q: q.value }
      : { type: placeholder.value ? 'cable_mgmt,blank_panel,shelf' : props.kind, q: q.value })
  } catch (e) { error.value = errText(e) }
}
function pickModel(m) {
  picked.value = m; custom.value = null; form.model_id = m.id; form.type = m.type; form.vendor = m.vendor; form.model = m.model; form.height_u = m.height_u
  form.orientation = m.orientation; form.mount_side = m.mount_side; form.side_slot = m.side_slot || (m.orientation === 'vertical' ? (props.sideSlot || 'left') : '')
  if (m.orientation === 'vertical' && props.sideSlot) form.side_slot = props.sideSlot              // Klick in den Kanal: dessen Seite gilt
  if (m.orientation === 'vertical' && props.mountSide && m.mount_side === 'both') form.mount_side = props.mountSide
  // Platzhalter und Patchfelder sind einseitig: Es gilt die Seite der Ansicht, aus der geplant wird (Rückseite: z. B. Kabelführung hinten)
  if (m.orientation === 'horizontal' && ['placeholder', 'patchpanel'].includes(props.kind) && props.mountSide && m.mount_side !== 'both') form.mount_side = props.mountSide
}
function pickCustom() {
  picked.value = null; form.model_id = null; form.height_u = form.height_u || 1
  custom.value = isPanel.value ? { count: 24, medium: 'RJ45' } : { rj45: 24, sfp: 0, sfpp: 0 }
}

async function loadLocations() {
  form.location_id = null; slots.value = { free_starts: [], devices: [] }
  locations.value = siteId.value ? (await api.locations(siteId.value)).filter(l => PLACE_KINDS.includes(l.kind)) : []
}
async function mountChanged() {
  conflict.value = null
  if (form.orientation === 'vertical') { if (form.mount_side === 'both') form.mount_side = props.mountSide || 'rear'; if (!form.side_slot) form.side_slot = 'left' }
  else form.side_slot = ''
  if (isRack.value) await refreshSlots(form.rack_position)
}
async function onLocation() {
  form.rack_position = null; conflict.value = null
  if (isRack.value) await refreshSlots()
}
async function refreshSlots(keepPosition) {
  try {
    slots.value = await api.rackSlots(form.location_id, heightU.value, { mount_side: form.mount_side, orientation: form.orientation, side_slot: form.side_slot })
    const want = keepPosition ?? props.rackPosition
    form.rack_position = want ?? slots.value.free_starts[0] ?? null
  } catch (e) { error.value = errText(e) }
}

let timer
async function searchTargets() {
  clearTimeout(timer)
  if (targetQ.value.trim().length < 2) { targets.value = []; return }
  timer = setTimeout(async () => { try { targets.value = (await api.devices({ q: targetQ.value.trim(), site_id: siteId.value || undefined, limit: 15 })).items } catch {} }, 250)
}
async function pickTarget(d) {
  target.value = d; uplink.target_port_id = null; conflict.value = null
  try { targetPorts.value = (await api.device(d.id)).ports } catch (e) { error.value = errText(e) }
}

watch(() => loc.value?.id, () => {                              // Einbau passend zur gewählten Location
  const opts = orientationOptions.value.map(o => o[0])
  if (!opts.includes(form.orientation)) form.orientation = opts[0]
  if (loc.value && loc.value.kind !== 'rack' && form.orientation !== 'vertical') { form.side_slot = ''; if (form.mount_side === 'rear') form.mount_side = 'front' }
  if (loc.value && ['wallrack', 'cabinet'].includes(loc.value.kind) && form.mount_side === 'both') form.mount_side = 'front'
  if (form.orientation === 'din_rail') form.rack_position = null
})
watch(() => form.hostname, async v => {
  try { nameTaken.value = v.trim().length > 0 && (await api.devices({ q: v.trim(), limit: 20 })).items.some(d => d.hostname.toLowerCase() === v.trim().toLowerCase()) } catch { nameTaken.value = false }
})
watch(withUplink, on => { conflict.value = null; if (on && !uplink.port_name) uplink.port_name = portNames.value[portNames.value.length - 1] || '' })

const canNext = computed(() => {
  switch (stepKey.value) {
    case 'model': return !!(picked.value || (custom.value && (isPanel.value ? custom.value.count > 0 : (custom.value.rj45 + custom.value.sfp + custom.value.sfpp) > 0)))
    case 'place': return !!form.location_id
    case 'device': return (passive.value || !!form.hostname.trim()) && !nameTaken.value
    case 'cable': return isPanel.value ? !panelLinks.value.error : (!withUplink.value || (!!uplink.port_name && !!uplink.target_port_id))
    default: return true
  }
})

const payload = dry => ({
  ...form, hostname: form.hostname.trim(), height_u: heightU.value, ports: picked.value ? [] : groups.value,
  uplink: (!isPanel.value && withUplink.value) ? { ...uplink, fiber_count: countLabel(uplink.cable_type) ? uplink.fiber_count : null } : null,
  links: isPanel.value ? panelLinks.value.links : [],
  workorder_id: form.mode === 'workorder' ? form.workorder_id : null, dry_run: dry,
})

/** Rückfrage-Antwort des Servers (belegte HE / belegter Port) erkennen; sonst normale Fehleranzeige. */
function handleError(e) {
  const c = conflictOf(e)
  if (c) { conflict.value = c; error.value = ''; preview.value = null } else error.value = errText(e)
}
async function check() {
  busy.value = true; preview.value = null; error.value = ''
  try { preview.value = await api.deviceWizard(payload(true)); conflict.value = null } catch (e) { handleError(e) } finally { busy.value = false }
}
async function resolveConflict(yes) {
  const c = conflict.value
  if (!yes) {                                              // andere Wahl: zurück zur Position bzw. zum Zielport
    conflict.value = null
    step.value = c.code === 'slot_busy' ? 1 : Array.from({ length: STEPS.value.length }, (_, i) => keyOf(i)).indexOf('cable')
    return
  }
  if (c.code === 'slot_busy') form.replace_devices = true
  else if (c.code === 'port_reserved') form.use_reserved = true
  else form.remove_old = true
  conflict.value = null
  await check()
}
async function modeChanged() { conflict.value = null; await check() }

async function next() {
  error.value = ''
  step.value++
  if (stepKey.value === 'place' && isRack.value) await refreshSlots(form.rack_position)
  if (stepKey.value === 'device' && isPanel.value && !form.hostname.trim() && loc.value) form.hostname = `PF-${loc.value.name.replace(/[^A-Za-z0-9]+/g, '')}${form.rack_position ? '-HE' + form.rack_position : ''}`
  if (stepKey.value === 'mode') {
    if (!canDirect) form.mode = 'workorder'
    if (canOrder) { try { openOrders.value = (await api.workorders()).filter(w => ['draft', 'rework'].includes(w.status)) } catch {} }
    form.replace_devices = false; form.remove_old = false; form.use_reserved = false
    await check()
  }
}
function back() { error.value = ''; conflict.value = null; preview.value = null; step.value-- }
async function create() {
  busy.value = true; error.value = ''
  try { emit('done', await api.deviceWizard(payload(false))) } catch (e) { handleError(e) } finally { busy.value = false }
}

onMounted(async () => {
  loadCableTypes(); loadModels()
  try {
    sites.value = await api.sites()
    if (props.locationId) {
      const all = await api.locations()
      const l = all.find(x => x.id === props.locationId)
      if (l) { siteId.value = l.site_id; locations.value = all.filter(x => x.site_id === l.site_id && PLACE_KINDS.includes(x.kind)); form.location_id = l.id; form.rack_position = props.rackPosition }
    } else if (sites.value.length === 1) { siteId.value = sites.value[0].id; await loadLocations() }
  } catch (e) { error.value = errText(e) }
})
</script>
