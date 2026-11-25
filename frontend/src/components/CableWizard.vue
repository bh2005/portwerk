<template>
  <ModalDialog wide :title="$t('Assistent: Kabel einbauen')" :error="error" @close="$emit('close')">
    <!-- Fortschritt -->
    <ol class="flex items-center gap-2 text-xs mb-1 flex-wrap">
      <li v-for="(l, i) in STEPS" :key="l" class="flex items-center gap-2">
        <span class="w-5 h-5 rounded-full flex items-center justify-center font-semibold"
          :class="i === step ? 'bg-ks-600 text-white' : i < step ? 'bg-green-500 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-500'">{{ i < step ? '✓' : i + 1 }}</span>
        <span :class="i === step ? 'text-slate-800 dark:text-slate-100 font-medium' : 'text-slate-400'">{{ l }}</span>
        <span v-if="i < STEPS.length - 1" class="text-slate-300">—</span>
      </li>
    </ol>

    <!-- 1: Kabelart -->
    <div v-if="step === 0" class="space-y-3">
      <p class="text-sm text-slate-500">{{ $t('Welche Kabelart wird verlegt? Die Liste stammt aus dem Katalog (Verwaltung → Katalog → Kabelarten) – neben Daten- und Glasfaserkabeln auch Strom, Koax (RG58 für NTP/DCF), seriell und Telefon.') }}</p>
      <div class="flex gap-2 flex-wrap">
        <button v-for="[k, l] in categories" :key="k" type="button" @click="category = k"
          class="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
          :class="category === k ? 'bg-ks-600 text-white border-ks-600' : 'border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'">{{ $t(l) }}</button>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
        <button v-for="t in typeChoices" :key="t.name" type="button" @click="pickType(t)"
          class="text-left px-3 py-2 rounded-lg border text-sm transition-colors"
          :class="form.cable_type === t.name ? 'border-ks-500 bg-ks-50 dark:bg-ks-900/30' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/40'">
          <span class="font-medium text-slate-800 dark:text-slate-100">{{ t.name }}</span>
          <span v-if="t.note" class="block text-[11px] text-slate-400">{{ t.note }}</span></button>
      </div>
    </div>

    <!-- 2: Ports -->
    <div v-if="step === 1" class="space-y-3">
      <div class="grid md:grid-cols-2 gap-5">
        <PortPicker :label="$t('Ende A')" v-model="form.port_a_id" :allowed="allowed" :preset-device-id="presetDeviceId" :preset-port-id="presetPortId" :locked="!!presetPortId" @select="a = $event" />
        <PortPicker :label="$t('Ende B')" v-model="form.port_b_id" :allowed="allowed" @select="b = $event" />
      </div>
      <p v-if="a && b && a.id === b.id" class="text-xs text-red-500 dark:text-red-400">{{ $t('Ein Port kann nicht mit sich selbst verbunden werden.') }}</p>
      <p v-for="w in mediumHints" :key="w" class="text-xs text-amber-600 dark:text-amber-400">⚠ {{ w }}</p>
      <p class="text-[11px] text-slate-400">{{ $t('Belegte Ports sind wählbar: Der Assistent fragt dann, ob der alte Patch zurückgebaut werden soll.') }}</p>
    </div>

    <!-- 3: Details -->
    <div v-if="step === 2" class="space-y-3">
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">{{ $t('Kabelnummer / Label') }}</label><input v-model="form.cable_label" :class="inp" :placeholder="$t('z. B. K-EG-001')" /></div>
        <div><label :class="lbl">{{ $t('Länge (m)') }}</label><input v-model.number="form.length_m" type="number" min="0" step="0.5" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Farbe') }}</label><input v-model="form.color" :class="inp" /></div>
        <div v-if="countLabel(form.cable_type)"><label :class="lbl">{{ countLabel(form.cable_type) }}</label><input v-model.number="form.fiber_count" type="number" min="1" :class="inp" /></div>
        <div v-if="canDirect"><label :class="lbl">{{ $t('Verlegt am') }}</label><input v-model="form.installed_at" type="date" :class="inp" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="form.note" :class="inp" /></div>
    </div>

    <!-- 4: Umsetzung und Prüfen -->
    <div v-if="step === 3" class="space-y-3">
      <div v-if="canDirect && canOrder" class="space-y-1">
        <label :class="lbl">{{ $t('Umsetzung') }}</label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="direct" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>{{ $t('Sofort anlegen') }}</b>{{ ' ' + $t('– das Kabel wird direkt in den Bestand geschrieben.') }}</span></label>
        <label class="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="radio" value="workorder" v-model="form.mode" @change="modeChanged" class="mt-1" />
          <span><b>{{ $t('Per Patchauftrag') }}</b>{{ ' ' + $t('– das Kabel wird eine Position (Freigabe → Ausführung → Bestätigung).') }}</span></label>
      </div>
      <p v-else class="text-sm text-slate-500">{{ $t('Umsetzung:') + ' ' }}<b>{{ canOrder && !canDirect ? $t('per Patchauftrag (du darfst Stammdaten nicht direkt ändern)') : 'sofort' }}</b></p>
      <div v-if="form.mode === 'workorder'" class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Patchauftrag') }}</label>
          <select v-model="form.workorder_id" :class="inp" @change="check"><option :value="null">{{ $t('Neuen Auftrag anlegen') }}</option>
            <option v-for="w in openOrders" :key="w.id" :value="w.id">{{ w.number }} · {{ w.title }}</option></select></div>
        <div v-if="!form.workorder_id"><label :class="lbl">{{ $t('Titel des neuen Auftrags') }}</label><input v-model="form.workorder_title" :class="inp" :placeholder="`Kabel ${a?.device.hostname} ↔ ${b?.device.hostname}`" @change="check" /></div>
      </div>

      <div v-if="conflict" class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3 space-y-2">
        <p class="text-sm font-medium text-amber-800 dark:text-amber-300">{{ conflict.code === 'port_reserved' ? $t('Reserviert bzw. schon verplant') : (conflict.conflicts.length > 1 ? $t('{n} Ports sind belegt', { n: conflict.conflicts.length }) : $t('Ein Port ist belegt')) }}</p>
        <p class="text-sm text-amber-900 dark:text-amber-200">{{ conflict.message }}</p>
        <div class="flex gap-2">
          <button :class="btnPrimary" @click="resolve(true)">{{ conflict.code === 'port_reserved' ? $t('Ja, trotzdem verwenden') : $t('Ja, zurückbauen') }}</button>
          <button :class="btnGhost" @click="resolve(false)">{{ $t('Nein, andere Ports wählen') }}</button>
        </div>
      </div>

      <p v-if="busy" class="text-sm text-slate-400">{{ $t('Prüfe …') }}</p>
      <div v-else-if="preview" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-sm space-y-1">
        <div><b>{{ preview.cable.from }}</b> ↔ <b>{{ preview.cable.to }}</b></div>
        <div class="text-slate-500">{{ preview.cable.type }}<template v-if="preview.cable.label"> · {{ $t('Kabelnummer') }} {{ preview.cable.label }}</template><template v-if="form.length_m"> · {{ form.length_m }} m</template> · {{ preview.cable.via }}</div>
        <div v-if="preview.workorder" class="text-slate-500">{{ $t('Patchauftrag:') }} {{ preview.workorder.existing ? $t('Position in {n}', { n: preview.workorder.existing }) : $t('neu „{t}“', { t: preview.workorder.new }) }}</div>
        <div v-if="preview.removals" class="text-amber-700 dark:text-amber-400">{{ $t('Rückbau') }} ({{ $t(preview.removals.via) }}): {{ preview.removals.cables.join(', ') }}<span v-if="form.mode === 'workorder'">{{ ' ' + $t('– der neue Auftrag startet erst nach bestätigtem Rückbau.') }}</span></div>
        <div v-for="w in preview.warnings" :key="w" class="text-amber-600 dark:text-amber-400">⚠ {{ w }}</div>
      </div>
    </div>

    <template #footer>
      <button :class="btnGhost" @click="$emit('close')">{{ $t('Abbrechen') }}</button>
      <button v-if="step > 0" :class="btnGhost" :disabled="busy" @click="back">{{ $t('Zurück') }}</button>
      <button v-if="step < STEPS.length - 1" :class="btnPrimary" :disabled="!canNext" @click="next">{{ $t('Weiter') }}</button>
      <button v-else :class="btnPrimary" :disabled="busy || !preview || !!conflict" @click="create">{{ busy ? '…' : $t('Anlegen') }}</button>
    </template>
  </ModalDialog>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, reactive, computed, onMounted } from 'vue'
import ModalDialog from './ModalDialog.vue'
import PortPicker from './PortPicker.vue'
import { api, errText, conflictOf, canWriteMaster, hasRole } from '../api.js'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'
import { inp, lbl, btnPrimary, btnGhost, CABLE_CATEGORIES, CATEGORY_MEDIA } from '../ui.js'

const props = defineProps({
  presetDeviceId: { type: Number, default: null },           // Ende A vorbelegen (z. B. aus der Geräteansicht)
  presetPortId: { type: Number, default: null },
})
const emit = defineEmits(['close', 'done'])

const STEPS = [t('Kabelart'), t('Ports'), t('Details'), t('Umsetzung')]
const step = ref(0)
const error = ref(''), busy = ref(false)
const category = ref('copper')
const a = ref(null), b = ref(null)
const openOrders = ref([]), preview = ref(null), conflict = ref(null)
const canDirect = canWriteMaster()
const canOrder = hasRole('planer')

const form = reactive({
  cable_type: 'Cat6', port_a_id: '', port_b_id: '', cable_label: '', length_m: null, fiber_count: null, color: '', installed_at: null, note: '',
  mode: canDirect ? 'direct' : 'workorder', remove_old: false, use_reserved: false, workorder_id: null, workorder_title: '',
})

const categories = computed(() => CABLE_CATEGORIES.filter(([k]) => cableTypes.value.some(t => t.category === k)))
const typeChoices = computed(() => cableTypes.value.filter(t => t.category === category.value))
const selectedType = computed(() => cableTypes.value.find(t => t.name === form.cable_type))
const allowed = computed(() => { const m = CATEGORY_MEDIA[selectedType.value?.category]; return m || null })
const mediumHints = computed(() => [a.value, b.value].filter(p => p && allowed.value && p.medium !== 'other' && !allowed.value.includes(p.medium))
  .map(p => t('{port} hat das Medium {m}, das normalerweise nicht zu „{c}“ passt', { port: `${p.device.hostname}:${p.name}`, m: p.medium, c: form.cable_type })))

function pickType(t) { form.cable_type = t.name; if (!t.count_label) form.fiber_count = null }

const canNext = computed(() => {
  if (step.value === 0) return !!selectedType.value
  if (step.value === 1) return !!(a.value && b.value && a.value.id !== b.value.id)
  return true
})

const payload = dry => ({ ...form, port_a_id: a.value.id, port_b_id: b.value.id, fiber_count: countLabel(form.cable_type) ? form.fiber_count : null,
  workorder_id: form.mode === 'workorder' ? form.workorder_id : null, dry_run: dry })

function handleError(e) {
  const c = conflictOf(e)
  if (c) { conflict.value = c; error.value = ''; preview.value = null } else error.value = errText(e)
}
async function check() {
  busy.value = true; preview.value = null; error.value = ''
  try { preview.value = await api.cableWizard(payload(true)); conflict.value = null } catch (e) { handleError(e) } finally { busy.value = false }
}
async function resolve(yes) {
  if (!yes) { conflict.value = null; step.value = 1; return }
  if (conflict.value.code === 'port_reserved') form.use_reserved = true
  else form.remove_old = true
  conflict.value = null
  await check()
}
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
  try { emit('done', await api.cableWizard(payload(false))) } catch (e) { handleError(e) } finally { busy.value = false }
}

onMounted(async () => {
  await loadCableTypes()
  const t = cableTypes.value.find(x => x.name === form.cable_type)
  if (t) category.value = t.category
  else if (cableTypes.value.length) { form.cable_type = cableTypes.value[0].name; category.value = cableTypes.value[0].category }
  if (props.presetPortId) step.value = 0
})
</script>
