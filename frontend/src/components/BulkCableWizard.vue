<template>
  <ModalDialog wide :title="$t('Assistent: Massenverkabelung')" :error="error" @close="$emit('close')">
    <ol class="flex items-center gap-2 text-xs mb-1 flex-wrap">
      <li v-for="(l, i) in STEPS" :key="l" class="flex items-center gap-2">
        <span class="w-5 h-5 rounded-full flex items-center justify-center font-semibold"
          :class="i === step ? 'bg-ks-600 text-white' : i < step ? 'bg-green-500 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-500'">{{ i < step ? '✓' : i + 1 }}</span>
        <span :class="i === step ? 'text-slate-800 dark:text-slate-100 font-medium' : 'text-slate-400'">{{ l }}</span>
        <span v-if="i < STEPS.length - 1" class="text-slate-300">—</span>
      </li>
    </ol>

    <!-- 1: Methode und Quellen -->
    <div v-if="step === 0" class="space-y-3">
      <div class="grid md:grid-cols-4 gap-2">
        <button v-for="m in METHODS" :key="m.k" type="button" @click="chooseMethod(m.k)" class="text-left p-3 rounded-lg border text-sm transition-colors"
          :class="method === m.k ? 'border-ks-500 bg-ks-50 dark:bg-ks-900/30' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/40'">
          <span class="font-medium text-slate-800 dark:text-slate-100">{{ m.title }}</span><span class="block text-[11px] text-slate-400 mt-0.5">{{ m.text }}</span></button>
      </div>

      <template v-if="method && method !== 'list'">
        <div class="grid md:grid-cols-2 gap-3">
          <PortSourcePicker :key="'a' + method" :label="$t('Seite A')" :initial-mode="cfg.a.mode" :initial-side="cfg.a.side" :initial-types="cfg.a.types" :preset-device-id="presetDeviceId" @update:ports="portsA = $event" />
          <PortSourcePicker :key="'b' + method" :label="$t('Seite B')" :initial-mode="cfg.b.mode" :initial-side="cfg.b.side" :initial-types="cfg.b.types" @update:ports="portsB = $event" />
        </div>
        <p class="text-xs text-slate-400">{{ $t('Die Ports beider Seiten werden der Reihe nach einander zugeordnet (natürliche Sortierung). Im nächsten Schritt prüfst du die Zuordnung und kannst Versatz einstellen oder Zeilen auslassen.') }}</p>
      </template>

      <template v-if="method === 'list'">
        <p class="text-sm text-slate-500">{{ $t('Liste aus Excel einfügen oder als CSV laden. Spalten:') + ' ' }}<b>{{ $t('Gerät A; Port A; Gerät B; Port B; Kabelnummer') }}</b>{{ ' ' + $t('(Kabelnummer optional, Kopfzeile erlaubt, Trennzeichen') + ' ' }}<code>;</code>{{ ' ' + $t('oder Tab).') }}</p>
        <textarea v-model="listText" rows="7" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="pf-rz;P1-back;pf-e1;P1-back;TR-01&#10;pf-rz;P2-back;pf-e1;P2-back;TR-02"></textarea>
        <div class="flex items-center gap-3">
          <input type="file" accept=".csv,.txt,.tsv" class="text-xs" @change="loadFile" />
          <button type="button" :class="btnGhost" :disabled="!listText.trim() || busy" @click="parseList">{{ $t('Liste prüfen') }}</button>
        </div>
        <div v-if="parsed">
          <p class="text-sm" :class="parsed.pairs.length ? 'text-green-600' : 'text-red-500'">{{ $t('{a} von {b} Zeilen gültig', { a: parsed.pairs.length, b: parsed.total }) }}</p>
          <ul v-if="parsed.errors.length" class="text-xs text-red-500 max-h-28 overflow-y-auto mt-1 dark:text-red-400"><li v-for="e in parsed.errors" :key="e.line">{{ $t('Zeile {n}:', { n: e.line }) }} {{ e.message }}</li></ul>
        </div>
      </template>
    </div>

    <!-- 2: Zuordnung -->
    <div v-if="step === 1" class="space-y-3">
      <div v-if="method !== 'list'" class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">{{ $t('Seite A überspringen (Ports)') }}</label><input v-model.number="offsetA" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Seite B überspringen (Ports)') }}</label><input v-model.number="offsetB" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Höchstens (Anzahl)') }}</label><input v-model.number="maxCount" type="number" min="1" :class="inp" :placeholder="$t('alle')" /></div>
      </div>
      <p class="text-sm text-slate-500">{{ $t('{n} Kabel', { n: included.length }) }}<template v-if="excluded.size"> ({{ $t('{n} ausgelassen', { n: excluded.size }) }})</template>
        <template v-if="method !== 'list' && (portsA.length - offsetA > rows.length || portsB.length - offsetB > rows.length)"> · {{ $t('nicht zugeordnet:') }} A {{ Math.max(0, portsA.length - offsetA - rows.length) }}, B {{ Math.max(0, portsB.length - offsetB - rows.length) }}</template></p>
      <div class="max-h-80 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg">
        <table class="w-full text-xs">
          <thead class="sticky top-0 bg-slate-50 dark:bg-slate-800"><tr><th class="px-2 py-1.5 text-left w-8"></th><th class="px-2 py-1.5 text-left">{{ $t('Nr') }}</th><th class="px-2 py-1.5 text-left">{{ $t('Seite A') }}</th><th class="px-2 py-1.5 text-left">{{ $t('Seite B') }}</th><th class="px-2 py-1.5 text-left">{{ $t('Kabelnummer') }}</th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.key" class="border-t border-slate-100 dark:border-slate-700" :class="excluded.has(r.key) ? 'opacity-40 line-through' : ''">
              <td class="px-2 py-1"><input type="checkbox" :checked="!excluded.has(r.key)" @change="toggle(r.key)" /></td>
              <td class="px-2 py-1 text-slate-400">{{ r.i + 1 }}</td>
              <td class="px-2 py-1 font-mono">{{ r.aLabel }}</td><td class="px-2 py-1 font-mono">{{ r.bLabel }}</td>
              <td class="px-2 py-1 font-mono text-slate-500">{{ labelOf(r) }}</td>
            </tr>
            <tr v-if="!rows.length"><td colspan="5" class="px-2 py-4 text-center text-slate-400">{{ $t('Keine Zuordnung – wähle auf beiden Seiten Ports (oder prüfe die Liste).') }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3: Kabel -->
    <div v-if="step === 2" class="space-y-3">
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">{{ $t('Kabelart') }}</label><select v-model="form.cable_type" :class="inp"><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
        <div><label :class="lbl">{{ $t('Länge (m)') }}</label><input v-model.number="form.length_m" type="number" min="0" step="0.5" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Farbe') }}</label><input v-model="form.color" :class="inp" /></div>
        <div v-if="countLabel(form.cable_type)"><label :class="lbl">{{ countLabel(form.cable_type) }}</label><input v-model.number="form.fiber_count" type="number" min="1" :class="inp" /></div>
      </div>
      <div class="grid grid-cols-3 gap-3">
        <div class="col-span-2"><label :class="lbl">{{ $t('Kabelnummer-Muster') }} {{ method === 'list' ? $t('(nur für Zeilen ohne Kabelnummer)') : '' }}</label><input v-model="pattern" :class="inp" />
          <p class="text-[11px] text-slate-400 mt-1">{{ $t('{n} laufende Nummer, {nn} zweistellig, {a} und {b} Portnamen, {hostA} und {hostB} Hostnamen') }}</p></div>
        <div><label :class="lbl">{{ $t('Erste Nummer') }}</label><input v-model.number="startNumber" type="number" min="0" :class="inp" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="form.note" :class="inp" /></div>
      <p class="text-xs text-slate-400">{{ $t('Beispiel:') }} {{ labelOf(included[0] || rows[0] || { i: 0, aHost: 'a', bHost: 'b', aPort: '1', bPort: '1' }) }}</p>
    </div>

    <!-- 4: Umsetzung -->
    <div v-if="step === 3" class="space-y-3">
      <div v-if="canDirect && canOrder" class="space-y-1">
        <label :class="lbl">{{ $t('Umsetzung') }}</label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="workorder" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>{{ $t('Als Patchauftrag mit Arbeitsliste') }}</b>{{ ' ' + $t('– ein Auftrag, eine Position je Kabel. Die Ausführenden haken die Liste ab (auch mehrere auf einmal), Export und Druck sind möglich.') }}</span></label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="direct" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>{{ $t('Sofort anlegen') }}</b>{{ ' ' + $t('– alle Kabel werden in einem Schritt in den Bestand geschrieben (alles oder nichts).') }}</span></label>
      </div>
      <p v-else class="text-sm text-slate-500">{{ $t('Umsetzung:') + ' ' }}<b>{{ canOrder && !canDirect ? $t('als Patchauftrag') : $t('sofort') }}</b></p>
      <div v-if="form.mode === 'workorder'" class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Patchauftrag') }}</label>
          <select v-model="form.workorder_id" :class="inp" @change="check"><option :value="null">{{ $t('Neuen Auftrag anlegen') }}</option>
            <option v-for="w in openOrders" :key="w.id" :value="w.id">{{ w.number }} · {{ w.title }}</option></select></div>
        <div v-if="!form.workorder_id"><label :class="lbl">{{ $t('Titel des neuen Auftrags') }}</label><input v-model="form.workorder_title" :class="inp" :placeholder="$t('z. B. Trunk RZ ↔ Etage 1')" @change="check" /></div>
      </div>

      <div v-if="conflict" class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3 space-y-2">
        <p class="text-sm font-medium text-amber-800 dark:text-amber-300">{{ conflict.code === 'port_reserved' ? `${conflict.conflicts.length} Ports sind reserviert bzw. schon verplant` : `${conflict.conflicts.length} Ports sind belegt` }}</p>
        <p class="text-sm text-amber-900 dark:text-amber-200">{{ conflict.message }}</p>
        <div class="flex gap-2"><button :class="btnPrimary" @click="resolve(true)">{{ conflict.code === 'port_reserved' ? $t('Ja, trotzdem verwenden') : $t('Ja, zurückbauen') }}</button><button :class="btnGhost" @click="resolve(false)">{{ $t('Nein, Zuordnung ändern') }}</button></div>
      </div>

      <p v-if="busy" class="text-sm text-slate-400">{{ $t('Prüfe …') }}</p>
      <div v-else-if="preview" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-sm space-y-1">
        <div><b>{{ preview.count }} × {{ preview.type }}</b> <span class="text-slate-400">· {{ preview.via }}</span></div>
        <div class="text-slate-500 font-mono text-xs">{{ preview.cables[0].from }} ↔ {{ preview.cables[0].to }}<template v-if="preview.cables[0].label"> ({{ preview.cables[0].label }})</template>
          <template v-if="preview.cables.length > 1"> … {{ preview.cables[1].from }} ↔ {{ preview.cables[1].to }}<template v-if="preview.cables[1].label"> ({{ preview.cables[1].label }})</template></template></div>
        <div v-if="preview.workorder" class="text-slate-500">{{ $t('Patchauftrag:') }} {{ preview.workorder.existing ? $t('Positionen in {n}', { n: preview.workorder.existing }) : $t('neu „{t}“', { t: preview.workorder.new }) }}</div>
        <div v-if="preview.skipped.length" class="text-slate-500">{{ $t('{n} bestehende Verbindung(en) werden übersprungen.', { n: preview.skipped.length }) }}</div>
        <div v-if="preview.removals" class="text-amber-700 dark:text-amber-400">{{ $t('Rückbau') }} ({{ $t(preview.removals.via) }}): {{ $t('{n} alte Patches', { n: preview.removals.count }) }}<span v-if="form.mode === 'workorder'">{{ ' ' + $t('– der neue Auftrag startet erst nach bestätigtem Rückbau.') }}</span></div>
        <div v-for="w in preview.warnings" :key="w" class="text-amber-600 dark:text-amber-400">⚠ {{ w }}</div>
      </div>
    </div>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ $t('Abbrechen') }}</button>
      <button v-if="step > 0" :class="btnGhost" :disabled="busy" @click="back">{{ $t('Zurück') }}</button>
      <button v-if="step < STEPS.length - 1" :class="btnPrimary" :disabled="!canNext" @click="next">{{ $t('Weiter') }}</button>
      <button v-else :class="btnPrimary" :disabled="busy || !preview || !!conflict" @click="create">{{ busy ? '…' : `${included.length} Kabel anlegen` }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, reactive, computed, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import PortSourcePicker from './PortSourcePicker.vue'
import { api, errText, conflictOf, canWriteMaster, hasRole } from '../api.js'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const props = defineProps({ presetDeviceId: { type: Number, default: null } })
const emit = defineEmits(['close', 'done'])

const STEPS = [t('Methode & Quellen'), t('Zuordnung'), t('Kabel'), t('Umsetzung')]
const METHODS = [
  { k: 'trunk', title: t('Patchfeld ↔ Patchfeld'), text: t('Alle Ports zwischen zwei Patchfeldern (z. B. RZ ↔ Etage 1) verkabeln.') },
  { k: 'outlets', title: t('Datendosen → Patchfeld/Switch'), text: t('Alle Dosen einer Location der Reihe nach auf ein Patchfeld oder einen Switch patchen.') },
  { k: 'free', title: t('Freie Wahl'), text: t('Zwei beliebige Port-Mengen paarweise verbinden.') },
  { k: 'list', title: t('Aus Liste (Excel/CSV)'), text: t('Fertige Zuordnungsliste einfügen oder laden.') },
]
const CONFIGS = {
  trunk:   { a: { mode: 'device', side: 'back', types: 'outlet' }, b: { mode: 'device', side: 'back', types: 'outlet' }, pattern: '{hostA}-{nn}' },
  outlets: { a: { mode: 'location', side: 'all', types: 'outlet' }, b: { mode: 'device', side: 'front', types: 'outlet' }, pattern: '{hostA}' },
  free:    { a: { mode: 'device', side: 'all', types: 'outlet' }, b: { mode: 'device', side: 'all', types: 'outlet' }, pattern: '{hostA}-{nn}' },
}
const step = ref(0), error = ref(''), busy = ref(false)
const method = ref(props.presetDeviceId ? 'trunk' : null)
const cfg = computed(() => CONFIGS[method.value] || CONFIGS.free)
const portsA = ref([]), portsB = ref([])
const offsetA = ref(0), offsetB = ref(0), maxCount = ref(null)
const excluded = ref(new Set())
const listText = ref(''), parsed = ref(null)
const pattern = ref('{hostA}-{nn}'), startNumber = ref(1)
const openOrders = ref([]), preview = ref(null), conflict = ref(null)
const canDirect = canWriteMaster(), canOrder = hasRole('planer')

const form = reactive({ cable_type: 'Cat6A', length_m: null, fiber_count: null, color: '', note: '', mode: canOrder ? 'workorder' : 'direct', remove_old: false, use_reserved: false, workorder_id: null, workorder_title: '' })

function chooseMethod(k) { method.value = k; pattern.value = (CONFIGS[k] || CONFIGS.free).pattern; portsA.value = []; portsB.value = []; parsed.value = null; excluded.value = new Set() }

const rows = computed(() => {
  if (method.value === 'list') {
    return (parsed.value?.pairs || []).map((p, i) => ({ key: `l${i}`, i, aId: p.port_a_id, bId: p.port_b_id, aLabel: p.a, bLabel: p.b, given: p.cable_label,
      aHost: p.a.split(':')[0], aPort: p.a.split(':').slice(1).join(':'), bHost: p.b.split(':')[0], bPort: p.b.split(':').slice(1).join(':') }))
  }
  const a = portsA.value.slice(offsetA.value || 0), b = portsB.value.slice(offsetB.value || 0)
  const n = Math.min(a.length, b.length, maxCount.value || Infinity)
  return Array.from({ length: n }, (_, i) => ({ key: `${a[i].id}-${b[i].id}`, i, aId: a[i].id, bId: b[i].id, aLabel: `${a[i].hostname}:${a[i].name}`, bLabel: `${b[i].hostname}:${b[i].name}`,
    given: '', aHost: a[i].hostname, aPort: a[i].name, bHost: b[i].hostname, bPort: b[i].name }))
})
const included = computed(() => rows.value.filter(r => !excluded.value.has(r.key)))
const toggle = k => { const s = new Set(excluded.value); s.has(k) ? s.delete(k) : s.add(k); excluded.value = s }
function labelOf(r) {
  if (r.given) return r.given
  const n = (Number(startNumber.value) || 0) + Math.max(0, included.value.findIndex(x => x.key === r.key) < 0 ? (r.i || 0) : included.value.findIndex(x => x.key === r.key))
  return pattern.value.replaceAll('{hostA}', r.aHost).replaceAll('{hostB}', r.bHost).replaceAll('{a}', r.aPort).replaceAll('{b}', r.bPort)
    .replaceAll('{nn}', String(n).padStart(2, '0')).replaceAll('{n}', String(n))
}

async function loadFile(e) { const f = e.target.files?.[0]; if (f) { listText.value = await f.text(); parsed.value = null } }
async function parseList() {
  busy.value = true; error.value = ''
  try { parsed.value = await api.bulkParse(listText.value); excluded.value = new Set() } catch (e) { error.value = errText(e) } finally { busy.value = false }
}

const canNext = computed(() => {
  if (step.value === 0) return method.value === 'list' ? !!parsed.value?.pairs.length : (portsA.value.length > 0 && portsB.value.length > 0)
  if (step.value === 1) return included.value.length > 0
  return true
})

const payload = dry => ({
  ...form, pairs: included.value.map(r => ({ port_a_id: r.aId, port_b_id: r.bId, cable_label: labelOf(r) })),
  fiber_count: countLabel(form.cable_type) ? form.fiber_count : null, workorder_id: form.mode === 'workorder' ? form.workorder_id : null, dry_run: dry,
})
function handleError(e) { const c = conflictOf(e); if (c) { conflict.value = c; error.value = ''; preview.value = null } else error.value = errText(e) }
async function check() {
  busy.value = true; preview.value = null; error.value = ''
  try { preview.value = await api.bulkCables(payload(true)); conflict.value = null } catch (e) { handleError(e) } finally { busy.value = false }
}
async function resolve(yes) { if (!yes) { conflict.value = null; step.value = 1; return } if (conflict.value.code === 'port_reserved') form.use_reserved = true; else form.remove_old = true; conflict.value = null; await check() }
async function modeChanged() { conflict.value = null; await check() }

async function next() {
  error.value = ''
  step.value++
  if (step.value === 3) {
    if (!canDirect) form.mode = 'workorder'
    form.remove_old = false; form.use_reserved = false
    if (canOrder) { try { openOrders.value = (await api.workorders()).filter(w => ['draft', 'rework'].includes(w.status)) } catch {} }
    await check()
  }
}
function back() { error.value = ''; conflict.value = null; preview.value = null; step.value-- }
async function create() {
  busy.value = true; error.value = ''
  try { emit('done', await api.bulkCables(payload(false))) } catch (e) { handleError(e) } finally { busy.value = false }
}

onMounted(() => loadCableTypes())
</script>
