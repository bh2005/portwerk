<template>
  <div class="min-h-screen bg-slate-100 dark:bg-slate-900 pb-28">
    <MobileBar :title="wo ? wo.number : $t('Auftrag')" :subtitle="wo?.title" back="/m">
      <router-link v-if="wo" :to="`/workorders/${wo.id}`" class="text-xs underline text-white/80">{{ $t('Vollansicht') }}</router-link>
    </MobileBar>

    <div v-if="wo" class="p-3 space-y-3">
      <!-- Status und Fortschritt -->
      <div class="bg-white dark:bg-slate-800 rounded-2xl p-4 shadow-sm">
        <div class="flex items-center gap-2 text-sm">
          <span class="px-2 py-0.5 rounded-full font-medium" :class="STATUS_CLS[wo.status] || 'bg-slate-100 text-slate-600'">{{ $t(wo.status_label) }}</span>
          <span v-if="wo.location" class="text-slate-500 truncate">{{ wo.location.name }}</span>
        </div>
        <div class="mt-3 flex items-center gap-3">
          <div class="flex-1 h-3 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"><div class="h-full bg-green-500 transition-all" :style="{ width: pct + '%' }"></div></div>
          <span class="font-semibold tabular-nums text-slate-700 dark:text-slate-200">{{ done }}/{{ items.length }}</span>
        </div>
        <p v-if="wo.depends_on && wo.depends_on.blocking" class="mt-3 text-sm text-amber-700 bg-amber-50 rounded-lg p-2 dark:text-amber-400">
          {{ $t('Erst nach Bestätigung von {n} (Rückbau) starten – aktuell: {s}.', { n: wo.depends_on.number, s: $t(wo.depends_on.status_label) }) }}</p>
        <p v-if="wo.description" class="mt-3 text-sm text-slate-600 dark:text-slate-300 whitespace-pre-line">{{ wo.description }}</p>
      </div>

      <p v-if="err" class="text-sm text-red-700 bg-red-50 rounded-xl p-3 dark:text-red-400">{{ err }}</p>
      <p v-if="info" class="text-sm text-green-700 bg-green-50 rounded-xl p-3 dark:text-green-400">{{ info }}</p>

      <!-- Filter -->
      <div class="flex bg-white dark:bg-slate-800 rounded-xl p-1 shadow-sm text-sm font-medium">
        <button v-for="[k, l] in FILTERS" :key="k" class="flex-1 py-2 rounded-lg"
          :class="filter === k ? 'bg-ks-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="filter = k">
          {{ l }} ({{ count(k) }})</button>
      </div>

      <!-- Positionen nach Ort -->
      <template v-for="g in groups" :key="g.name">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 px-1 pt-2">{{ g.name }}</h3>
        <div v-for="x in g.items" :key="x.id" :id="`item-${x.id}`"
          class="bg-white dark:bg-slate-800 rounded-2xl shadow-sm overflow-hidden border-l-8 transition-shadow"
          :class="[BORDER[x.item_status], highlight === x.id ? 'ring-4 ring-ks-400' : '']">
          <div class="p-4 space-y-3">
            <div class="flex items-start gap-2">
              <span class="text-slate-400 font-semibold tabular-nums">{{ x.n }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-100">{{ $t(x.action_label) }}</span>
              <span v-if="x.cable_label" class="ml-auto font-mono font-bold text-lg px-2 rounded bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100">{{ x.cable_label }}</span>
            </div>
            <End label="von" :name="x.a" :where="x.a_location" :unit="x.a_unit" />
            <End v-if="x.b" :label="x.action === 'disconnect' ? $t('steckt an') : 'nach'" :name="x.b" :where="x.b_location !== x.a_location ? x.b_location : ''" :unit="x.b_unit" />
            <p v-if="x.old_b" class="text-sm text-slate-500">{{ $t('bisher:') + ' ' }}<span class="font-mono">{{ x.old_b }}</span></p>
            <p v-if="details(x)" class="text-sm text-slate-600 dark:text-slate-300">{{ details(x) }}</p>
            <p v-if="x.cfg_text" class="text-sm font-medium text-indigo-700 dark:text-indigo-300">{{ $t('VLAN:') }} {{ x.cfg_text }}</p>
            <p v-if="x.note" class="text-sm text-slate-600 dark:text-slate-300 italic">{{ x.note }}</p>

            <div v-if="x.item_status !== 'open'" class="text-sm" :class="x.item_status === 'done' ? 'text-green-700' : 'text-amber-700'">
              {{ x.item_status === 'done' ? $t('✓ erledigt') : $t('⚠ Abweichung') }} · {{ x.executed_by }}
              <span v-if="x.deviation_note" class="block">„{{ x.deviation_note }}“</span>
            </div>
          </div>
          <div v-if="running" class="flex border-t border-slate-100 dark:border-slate-700">
            <template v-if="x.item_status === 'open'">
              <button class="flex-1 py-4 text-lg font-semibold text-white bg-green-600 active:bg-green-700 disabled:opacity-50" :disabled="busy === x.id" @click="exec(x, 'done')">{{ $t('✓ Erledigt') }}</button>
              <button class="flex-1 py-4 text-lg font-semibold text-amber-800 bg-amber-100 active:bg-amber-200 disabled:opacity-50" :disabled="busy === x.id" @click="deviation(x)">{{ $t('⚠ Abweichung') }}</button>
            </template>
            <button v-else class="flex-1 py-3 text-slate-600 dark:text-slate-300 active:bg-slate-100 dark:active:bg-slate-700" :disabled="busy === x.id" @click="reopen(x)">{{ $t('Zurücksetzen') }}</button>
          </div>
        </div>
      </template>
      <p v-if="!shown.length" class="text-center text-slate-500 py-8">{{ filter === 'open' && items.length ? $t('Alles erledigt 🎉') : $t('Keine Positionen.') }}</p>
    </div>
    <p v-else-if="err" class="m-3 text-sm text-red-700 bg-red-50 rounded-xl p-3 dark:text-red-400">{{ err }}</p>

    <!-- Aktionsleiste unten -->
    <div v-if="wo" class="fixed bottom-0 inset-x-0 p-3 flex gap-2 bg-slate-100/95 dark:bg-slate-900/95 backdrop-blur border-t border-slate-200 dark:border-slate-700">
      <button v-if="scanner?.supported" class="flex-1 bg-white dark:bg-slate-800 text-ks-700 dark:text-ks-300 font-semibold py-4 rounded-2xl shadow" @click="scanner.start()">{{ $t('Scannen') }}</button>
      <button v-if="canStart" class="flex-[2] bg-ks-600 text-white text-lg font-semibold py-4 rounded-2xl shadow-lg disabled:opacity-50" :disabled="!!busy" @click="transition('start')">{{ $t('Auftrag starten') }}</button>
      <button v-else-if="running" class="flex-[2] text-lg font-semibold py-4 rounded-2xl shadow-lg disabled:opacity-50"
        :class="open ? 'bg-slate-300 text-slate-600 dark:bg-slate-700 dark:text-slate-400' : 'bg-green-600 text-white'" :disabled="!!busy || open > 0" @click="transition('finish')">
        {{ open ? `Noch ${open} offen` : $t('Fertig melden') }}</button>
    </div>
    <QrScanner ref="scanner" @result="onScan" />
  </div>
</template>

<script setup>
import { t } from '../../i18n.js'
import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errText, hasRole } from '../../api.js'
import MobileBar from '../../components/mobile/MobileBar.vue'
import QrScanner from '../../components/mobile/QrScanner.vue'
import { labelFromScan, pathFromScan } from './scan.js'

const End = (p) => h('div', [
  h('div', { class: 'text-xs uppercase tracking-wide text-slate-400' }, p.label),
  h('div', { class: 'font-mono text-xl font-semibold text-slate-900 dark:text-white break-all' }, p.name),
  (p.where || p.unit) ? h('div', { class: 'text-sm text-slate-500' }, [p.where, p.unit ? `HE ${p.unit}` : ''].filter(Boolean).join(' · ')) : null,
])
End.props = ['label', 'name', 'where', 'unit']

const FILTERS = [['open', 'Offen'], ['done', 'Erledigt'], ['all', 'Alle']]
const STATUS_CLS = { in_progress: 'bg-ks-100 text-ks-700', approved: 'bg-green-100 text-green-700', rework: 'bg-amber-100 text-amber-800', done: 'bg-slate-200 text-slate-700' }
const BORDER = { open: 'border-slate-300 dark:border-slate-600', done: 'border-green-500', deviation: 'border-amber-500' }

const route = useRoute(), router = useRouter()
const wo = ref(null), items = ref([]), err = ref(''), info = ref(''), busy = ref(null), filter = ref('open'), highlight = ref(null), scanner = ref(null)
const isTech = hasRole('techniker')

const running = computed(() => wo.value?.status === 'in_progress' && isTech)
const canStart = computed(() => isTech && ['approved', 'rework'].includes(wo.value?.status))
const done = computed(() => items.value.filter(x => x.item_status !== 'open').length)
const open = computed(() => items.value.length - done.value)
const pct = computed(() => Math.round(100 * done.value / Math.max(1, items.value.length)))
const count = k => k === 'all' ? items.value.length : k === 'open' ? open.value : done.value
const shown = computed(() => items.value.filter(x => filter.value === 'all' || (filter.value === 'open') === (x.item_status === 'open')))
const groups = computed(() => {
  const m = new Map()
  for (const x of shown.value) { const k = x.group || t('ohne Ort'); if (!m.has(k)) m.set(k, []); m.get(k).push(x) }
  return [...m].map(([name, its]) => ({ name, items: its }))
})
const details = x => [x.cable_type, x.length_m ? `${x.length_m} m` : '', x.color].filter(Boolean).join(' · ')

async function load() {
  try {
    const id = route.params.id
    const [w, pl] = await Promise.all([api.workorder(id), api.patchlist(String(id), 'location', false)])
    wo.value = w
    items.value = pl.items.map((x, i) => ({ ...x, n: i + 1 }))
    err.value = ''
    if (route.query.label) focusLabel(String(route.query.label))
  } catch (e) { err.value = errText(e) }
}

async function exec(x, status, note = '') {
  busy.value = x.id; err.value = ''; info.value = ''
  try {
    const r = await api.executeWorkitem(wo.value.id, x.id, { item_status: status, deviation_note: note })
    Object.assign(x, { item_status: r.item_status, executed_by: r.executed_by, deviation_note: r.deviation_note })
    navigator.vibrate?.(30)
  } catch (e) { err.value = errText(e) } finally { busy.value = null }
}
function deviation(x) {
  const note = prompt(t('Abweichung – was war anders?'))
  if (note && note.trim()) exec(x, 'deviation', note.trim())
}
async function reopen(x) {
  busy.value = x.id
  try { const r = await api.reopenWorkitem(wo.value.id, x.id); Object.assign(x, { item_status: r.item_status, executed_by: '', deviation_note: '' }) }
  catch (e) { err.value = errText(e) } finally { busy.value = null }
}
async function transition(action) {
  busy.value = action; err.value = ''; info.value = ''
  try {
    wo.value = await api.workorderTransition(wo.value.id, action)
    info.value = action === 'start' ? t('Auftrag gestartet.') : t('Fertig gemeldet – der Auftrag wartet jetzt auf die Bestätigung.')
  } catch (e) { err.value = errText(e) } finally { busy.value = null }
}

async function focusLabel(label) {
  const x = items.value.find(i => i.cable_label === label)
  if (!x) { router.push(`/q/k/${encodeURIComponent(label)}`); return }
  filter.value = 'all'; highlight.value = x.id
  await nextTick()
  document.getElementById(`item-${x.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function onScan(text) {
  const label = labelFromScan(text)
  if (label) return focusLabel(label)
  const path = pathFromScan(text)
  if (path) router.push(path)
  else err.value = t('Unbekannter Code: {c}', { c: text })
}

onMounted(load)
watch(() => route.params.id, id => { if (id) load() })
</script>
