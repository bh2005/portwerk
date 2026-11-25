<template>
  <ModalDialog wide :title="siteId ? `Struktur ergänzen – ${siteLabel}` : 'Assistent: Neuer Standort'" :error="error" @close="$emit('close')">
    <!-- Fortschritt -->
    <ol class="flex items-center gap-2 text-xs mb-1">
      <li v-for="(l, i) in steps" :key="l" class="flex items-center gap-2">
        <span class="w-5 h-5 rounded-full flex items-center justify-center font-semibold"
          :class="i === step ? 'bg-ks-600 text-white' : i < step ? 'bg-green-500 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-500'">{{ i < step ? '✓' : i + 1 }}</span>
        <span :class="i === step ? 'text-slate-800 dark:text-slate-100 font-medium' : 'text-slate-400'">{{ l }}</span>
        <span v-if="i < steps.length - 1" class="text-slate-300">—</span>
      </li>
    </ol>

    <!-- 1: Standort -->
    <div v-if="stepKey === 'site'" class="space-y-3">
      <p class="text-sm text-slate-500">{{ $t('Ein Standort ist der oberste Punkt der Ortsstruktur (z. B. ein Werk oder eine Niederlassung).') }}</p>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Code *') }}</label><input v-model="site.code" :class="inp" :placeholder="$t('z. B. WERK1')" autofocus />
          <p class="text-[11px] text-slate-400 mt-1">{{ $t('Kurz, eindeutig; steht vor jedem Pfad (WERK1 / Haus 1 / …).') }}</p></div>
        <div><label :class="lbl">{{ $t('Name *') }}</label><input v-model="site.name" :class="inp" :placeholder="$t('z. B. Werk Musterstadt')" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Adresse') }}</label><input v-model="site.address" :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="site.note" :class="inp" /></div>
    </div>

    <!-- 2: Struktur -->
    <div v-if="stepKey === 'tree'" class="space-y-3">
      <div class="flex items-center justify-between gap-3">
        <p class="text-sm text-slate-500">{{ $t('Baue die Struktur:') + ' ' }}<b>{{ $t('Gebäude → Etage → Raum → Rack') }}</b>{{ $t('. Ebenen darfst du auslassen (z. B. Raum direkt am Standort). Anlagen/Maschinen und mobile Maschinen (Lader) können Schaltschränke enthalten; Racks, Wandgehäuse und Schaltschränke nehmen Geräte auf.') }}</p>
        <button v-if="!tree.length" :class="btnGhost" class="shrink-0" @click="quickStart">{{ $t('Schnellstart') }}</button>
      </div>
      <p v-if="!tree.length" class="text-xs text-slate-400">{{ $t('Noch leer. „Schnellstart“ legt ein Gebäude mit Serverraum und einem Rack (42 HE) an; sonst unten hinzufügen. Die Struktur kann auch leer bleiben und später ergänzt werden.') }}</p>
      <LocNodeList :nodes="tree" :parent-rank="parentRank" />
    </div>

    <!-- 3: Prüfen -->
    <div v-if="stepKey === 'check'" class="space-y-3">
      <p v-if="busy" class="text-sm text-slate-400">{{ $t('Prüfe …') }}</p>
      <template v-else-if="preview">
        <div class="flex flex-wrap gap-2 text-xs">
          <span v-if="preview.site.new" class="px-2 py-1 rounded-full bg-ks-50 dark:bg-ks-900/30 text-ks-700 dark:text-ks-300">{{ $t('1 Standort:') }} {{ preview.site.code }}</span>
          <span v-for="[k, l] in COUNTS" :key="k" v-show="preview.counts[k]" class="px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">{{ preview.counts[k] }} {{ l }}</span>
          <span v-if="!preview.items.length" class="text-slate-400">{{ $t('Keine Locations – es wird nur der Standort angelegt.') }}</span>
        </div>
        <ul v-if="preview.items.length" class="text-xs font-mono max-h-64 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg p-2 space-y-0.5">
          <li v-for="(it, i) in preview.items" :key="i" :style="{ paddingLeft: it.depth * 14 + 'px' }" class="text-slate-700 dark:text-slate-200">
            <span class="text-slate-400">{{ LABEL[it.kind] }}</span> {{ it.name }}<span v-if="it.rack_units" class="text-slate-400"> · {{ it.rack_units }} {{ $t('HE') }}</span>
          </li>
        </ul>
        <p class="text-xs text-slate-400">{{ $t('Beim Anlegen wird alles in einem Schritt gespeichert – bei einem Fehler wird nichts angelegt. Dieser Assistent schreibt direkt in die Stammdaten (Patchaufträge gibt es nur für Kabeländerungen).') }}</p>
      </template>
    </div>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ $t('Abbrechen') }}</button>
      <button v-if="step > 0" :class="btnGhost" :disabled="busy" @click="back">{{ $t('Zurück') }}</button>
      <button v-if="stepKey !== 'check'" :class="btnPrimary" :disabled="!canNext" @click="next">{{ $t('Weiter') }}</button>
      <button v-else :class="btnPrimary" :disabled="busy || !preview" @click="create">{{ busy ? '…' : 'Anlegen' }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, computed } from 'vue'
import ModalDialog from './ModalDialog.vue'
import LocNodeList, { makeNode } from './LocNodeList.vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const props = defineProps({ siteId: { type: Number, default: null }, siteLabel: { type: String, default: '' } })
const emit = defineEmits(['close', 'done'])

const LABEL = { building: t('Gebäude'), floor: t('Etage'), room: t('Raum'), machine: t('Anlage/Maschine'), vehicle: t('Mobile Maschine'), rack: t('Rack'), wallrack: t('Wandgehäuse'), cabinet: t('Schaltschrank') }
const COUNTS = [['building', t('Gebäude')], ['floor', t('Etagen')], ['room', t('Räume')], ['machine', t('Anlagen/Maschinen')], ['vehicle', t('mobile Maschinen')], ['rack', t('Racks')], ['wallrack', t('Wandgehäuse')], ['cabinet', t('Schaltschränke')]]
const parentRank = -1

const steps = computed(() => props.siteId ? [t('Struktur'), t('Prüfen')] : [t('Standort'), t('Struktur'), t('Prüfen')])
const step = ref(0)
const stepKey = computed(() => (props.siteId ? ['tree', 'check'] : ['site', 'tree', 'check'])[step.value])
const site = ref({ code: '', name: '', address: '', note: '' })
const tree = ref([])
const preview = ref(null), busy = ref(false), error = ref('')

const canNext = computed(() => stepKey.value !== 'site' || (site.value.code.trim() && site.value.name.trim()))

function quickStart() {
  const b = makeNode('building', t('Gebäude 1')), r = makeNode('room', t('Serverraum')), k = makeNode('rack', t('Rack 1'))
  r.children.push(k); b.children.push(r); tree.value.push(b)
}

const strip = n => ({ kind: n.kind, name: n.name, rack_units: ['rack', 'wallrack', 'cabinet'].includes(n.kind) ? (n.rack_units || null) : null, note: n.note, children: n.children.map(strip) })
const payload = dry => ({
  ...(props.siteId ? { site_id: props.siteId } : { site: { ...site.value } }),
  tree: tree.value.map(strip), dry_run: dry,
})

async function next() {
  error.value = ''
  step.value++
  if (stepKey.value === 'check') {
    busy.value = true; preview.value = null
    try { preview.value = await api.siteWizard(payload(true)) }
    catch (e) { error.value = errText(e); step.value = (e.response?.status === 409 && !props.siteId) ? 0 : step.value - 1 }   // Standortcode doppelt -> zurück zu Schritt 1, sonst zur Struktur
    finally { busy.value = false }
  }
}
function back() { error.value = ''; step.value-- }

async function create() {
  busy.value = true; error.value = ''
  try {
    const r = await api.siteWizard(payload(false))
    emit('done', r.site.id)
  } catch (e) { error.value = errText(e) }
  finally { busy.value = false }
}
</script>
