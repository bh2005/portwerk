<template>
  <div class="max-w-6xl space-y-4">
    <div class="flex items-start justify-between gap-3 flex-wrap print:hidden">
      <div>
        <button class="text-sm text-slate-400 hover:text-ks-600 dark:hover:text-ks-400" @click="$router.push('/workorders')">← Aufträge</button>
        <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Patchliste</h1>
      </div>
      <div class="flex gap-2 flex-wrap items-center">
        <select v-model="group" :class="inp" class="!w-44" @change="load"><option value="location">nach Ort sortiert</option><option value="order">nach Auftrag</option><option value="none">in Auftragsreihenfolge</option></select>
        <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="onlyOpen" @change="load" /> nur offene</label>
        <button :class="btnGhost" @click="sendOpen = true">Senden …</button>
        <button :class="btnGhost" @click="exportPdf">PDF</button>
        <button :class="btnGhost" @click="exportCsv">CSV-Export</button>
        <button :class="btnPrimary" @click="print">Drucken</button>
      </div>
    </div>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <SendDialog v-if="sendOpen" title="Patchliste senden" :submit="b => api.sendPatchlist({ ...b, ids: data.orders.map(o => o.id), group, only_open: onlyOpen })" @close="sendOpen = false" />

    <!-- Kopf (auch im Ausdruck) -->
    <div v-if="data" :class="card" class="p-4 space-y-2">
      <div class="hidden print:block text-lg font-semibold">Patchliste · {{ today }}</div>
      <div class="flex flex-wrap gap-2 text-sm">
        <router-link v-for="o in data.orders" :key="o.id" :to="`/workorders/${o.id}`" class="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 print:no-underline">
          <span class="font-mono font-semibold text-ks-700 dark:text-ks-400">{{ o.number }}</span> {{ o.title }}
          <span class="text-xs text-slate-400">· {{ o.status_label }} · {{ o.progress.done }}/{{ o.progress.total }}</span></router-link>
      </div>
      <div class="flex items-center gap-3 text-sm text-slate-500">
        <span>{{ data.summary.total }} Positionen<template v-for="(n, k) in data.summary.by_action" :key="k"> · {{ n }}× {{ actionName(k) }}</template></span>
        <span class="flex-1 max-w-xs h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden print:hidden"><span class="block h-full bg-green-500" :style="{ width: pct + '%' }"></span></span>
        <span>{{ data.summary.done }} erledigt<template v-if="data.summary.deviation"> · {{ data.summary.deviation }} Abweichung</template></span>
      </div>
    </div>

    <!-- Sammelaktionen -->
    <div v-if="data && data.items.length" class="flex items-center gap-3 flex-wrap print:hidden">
      <span class="text-sm text-slate-500">{{ selected.size }} ausgewählt</span>
      <button :class="btnPrimary" :disabled="!selected.size || busy" @click="act('execute')">Auswahl abhaken</button>
      <button :class="btnGhost" :disabled="!selected.size || busy" @click="act('deviation')">Abweichung …</button>
      <button :class="btnGhost" :disabled="!selected.size || busy" @click="act('reopen')">Zurücksetzen</button>
      <button :class="btnLink" @click="selectOpen">alle offenen wählen</button>
      <button v-if="selected.size" :class="btnLink" @click="selected = new Set()">Auswahl aufheben</button>
      <span v-if="note" class="text-sm text-green-600">{{ note }}</span>
    </div>

    <div v-if="data" :class="card" class="overflow-x-auto print:shadow-none print:border-0">
      <p v-if="!data.items.length" class="p-6 text-sm text-slate-400">Keine Positionen.</p>
      <table v-else class="w-full text-sm">
        <thead class="bg-slate-50 dark:bg-slate-700/40 print:bg-transparent">
          <tr>
            <th :class="th" class="w-8 print:hidden"><input type="checkbox" :checked="allSelected" @change="toggleAll" /></th>
            <th :class="th">Nr</th><th :class="th">Aktion</th><th :class="th">Seite A</th><th :class="th">Seite B</th><th :class="th">Kabel</th>
            <th v-if="group !== 'order'" :class="th">Auftrag</th><th :class="th">Status</th><th :class="th" class="hidden print:table-cell">erledigt</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(it, i) in data.items" :key="`${it.workorder_id}-${it.id}`">
            <tr v-if="group !== 'none' && (i === 0 || data.items[i - 1].group !== it.group)" class="bg-slate-100 dark:bg-slate-700/60 print:bg-slate-100 break-after-avoid">
              <td :colspan="9" class="px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-200">{{ it.group }} <span class="font-normal text-slate-400">· {{ countIn(it.group) }} Positionen</span></td>
            </tr>
            <tr class="border-t border-slate-100 dark:border-slate-700 break-inside-avoid" :class="it.item_status === 'done' ? 'bg-green-50/50 dark:bg-green-900/10' : (it.item_status === 'deviation' ? 'bg-orange-50/60 dark:bg-orange-900/10' : '')">
              <td :class="td" class="print:hidden"><input type="checkbox" :checked="selected.has(key(it))" @change="toggle(it)" /></td>
              <td :class="td" class="text-slate-400">{{ i + 1 }}</td>
              <td :class="td" class="text-xs">{{ it.action_label }}</td>
              <td :class="td" class="font-mono text-xs">{{ it.a }}<div v-if="group !== 'location' && it.a_location" class="text-[10px] text-slate-400 font-sans">{{ it.a_location }}</div></td>
              <td :class="td" class="font-mono text-xs">{{ it.b }}<div v-if="it.b_location" class="text-[10px] text-slate-400 font-sans">{{ it.b_location }}</div></td>
              <td :class="td" class="text-xs"><span class="font-mono">{{ it.cable_label }}</span> <span class="text-slate-400">{{ it.cable_type }}<template v-if="it.length_m"> · {{ it.length_m }} m</template></span></td>
              <td v-if="group !== 'order'" :class="td" class="font-mono text-xs text-slate-500">{{ it.order }}</td>
              <td :class="td" class="text-xs"><span :class="statusClass(it.item_status)" class="px-2 py-0.5 rounded-full">{{ { open: 'offen', done: 'erledigt', deviation: 'Abweichung' }[it.item_status] }}</span>
                <span v-if="it.deviation_note" class="block text-orange-600">{{ it.deviation_note }}</span></td>
              <td :class="td" class="hidden print:table-cell text-lg leading-none">☐</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import SendDialog from '../components/SendDialog.vue'
import { api, errText } from '../api.js'
import { inp, card, th, td, btnPrimary, btnGhost, btnLink } from '../ui.js'

const route = useRoute()
const ids = String(route.query.ids || '')
const data = ref(null), group = ref('location'), onlyOpen = ref(false)
const error = ref(''), busy = ref(false), note = ref(''), sendOpen = ref(false)
const selected = ref(new Set())
const today = new Date().toLocaleDateString('de-DE')

const key = it => `${it.workorder_id}:${it.id}`
const pct = computed(() => data.value?.summary.total ? Math.round(100 * data.value.summary.done / data.value.summary.total) : 0)
const allSelected = computed(() => !!data.value?.items.length && data.value.items.every(it => selected.value.has(key(it))))
const countIn = g => data.value.items.filter(it => it.group === g).length
const actionName = a => ({ connect: 'verbinden', disconnect: 'trennen', move: 'umstecken', install_device: 'Gerät einbauen', remove_device: 'Gerät zurückbauen' }[a] || a)
const statusClass = s => ({ open: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400', done: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  deviation: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' }[s])

async function load() {
  error.value = ''
  try { data.value = await api.patchlist(ids, group.value, onlyOpen.value) } catch (e) { error.value = errText(e) }
}
function toggle(it) { const s = new Set(selected.value); s.has(key(it)) ? s.delete(key(it)) : s.add(key(it)); selected.value = s }
function toggleAll() { selected.value = allSelected.value ? new Set() : new Set(data.value.items.map(key)) }
function selectOpen() { selected.value = new Set(data.value.items.filter(it => it.item_status === 'open').map(key)) }

async function act(kind) {
  let body = kind === 'execute' ? { action: 'execute', item_status: 'done' } : kind === 'reopen' ? { action: 'reopen' } : null
  if (kind === 'deviation') {
    const n = prompt('Abweichung – was war anders?'); if (!n || !n.trim()) return
    body = { action: 'execute', item_status: 'deviation', deviation_note: n.trim() }
  }
  const byOrder = {}
  for (const it of data.value.items) if (selected.value.has(key(it))) (byOrder[it.workorder_id] ||= []).push(it.id)
  busy.value = true; error.value = ''; note.value = ''
  const problems = []
  let n = 0
  for (const [wid, list] of Object.entries(byOrder)) {
    try { await api.bulkItems(wid, { ...body, ids: list }); n += list.length }
    catch (e) { const o = data.value.orders.find(x => String(x.id) === wid); problems.push(`${o?.number || wid}: ${errText(e)}`) }
  }
  busy.value = false
  if (problems.length) error.value = problems.join(' · ')
  if (n) note.value = `${n} Position(en) aktualisiert.`
  selected.value = new Set()
  await load()
}

async function exportPdf() {
  try {
    const blob = await api.patchlistPdf(ids, group.value, onlyOpen.value)
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'patchliste.pdf'; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { error.value = errText(e) }
}
async function exportCsv() {
  try {
    const blob = await api.patchlistExport(ids, group.value, onlyOpen.value)
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'patchliste.csv'; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { error.value = errText(e) }
}
const print = () => window.print()
onMounted(load)
</script>
