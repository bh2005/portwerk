<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Port-Reservierungen</h1>
      <div class="flex gap-2 items-center flex-wrap">
        <input v-model="q" :class="inp" class="!w-56 !py-1.5" placeholder="Zweck, Gerät, Person …" @input="debouncedLoad" />
        <select v-model="filter" :class="inp" class="!w-40 !py-1.5" @change="load">
          <option value="">alle</option><option value="valid">gültig</option><option value="expired">abgelaufen</option>
        </select>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Reservierte Ports gelten in den Assistenten nicht als frei. Wer sie verbinden oder in einem Auftrag verplanen will, bekommt eine Rückfrage.
      Reservieren: auf der Geräteseite Ports ankreuzen → „Reservieren“. Abgelaufene Reservierungen blockieren nichts mehr.
    </p>
    <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>

    <div v-for="g in groups" :key="g.purpose" :class="card" class="overflow-hidden">
      <div class="px-4 py-2 flex items-center gap-3 flex-wrap border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-700/40">
        <input v-if="canReserve" type="checkbox" :checked="g.rows.every(r => picked.has(r.id))" @change="pickGroup(g, $event.target.checked)" />
        <span class="font-medium text-slate-800 dark:text-slate-100">{{ g.purpose }}</span>
        <span class="text-xs text-slate-400">{{ g.rows.length }} Port(s)</span>
      </div>
      <table class="w-full text-sm">
        <tbody>
          <tr v-for="r in g.rows" :key="r.id" class="border-t first:border-t-0 border-slate-100 dark:border-slate-700" :class="r.expired ? 'text-slate-400' : ''">
            <td v-if="canReserve" :class="td" class="w-6"><input type="checkbox" :checked="picked.has(r.id)" @change="toggle(r.id)" /></td>
            <td :class="td" class="font-mono text-xs"><router-link :to="`/devices/${r.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ r.hostname }}:{{ r.port }}</router-link></td>
            <td :class="td" class="text-xs text-slate-500">{{ r.location }}</td>
            <td :class="td" class="text-xs">{{ r.reserved_by }}</td>
            <td :class="td" class="text-xs whitespace-nowrap">
              <span v-if="r.expired" class="text-red-500 dark:text-red-400">abgelaufen {{ fmtDate(r.until) }}</span>
              <span v-else-if="r.until">bis {{ fmtDate(r.until) }}</span><span v-else class="text-slate-400">unbefristet</span>
            </td>
            <td :class="td" class="text-xs">
              <router-link v-if="r.workorder" :to="`/workorders/${r.workorder.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ r.workorder.number }}</router-link>
              <span v-if="r.busy" class="ml-2 text-amber-600 dark:text-amber-400" title="An diesem Port steckt bereits ein Kabel">belegt</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!loading && !rows.length" class="text-sm text-slate-400">Keine Reservierungen.</p>

    <div v-if="canReserve && picked.size" class="sticky bottom-2 flex items-center gap-3 p-3 rounded-xl shadow bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
      <span class="text-sm text-slate-600 dark:text-slate-300">{{ picked.size }} gewählt</span>
      <button :class="btnPrimary" @click="releasePicked">Freigeben</button>
      <button :class="btnGhost" @click="editPicked">Zweck / Frist ändern</button>
      <button :class="btnLink" @click="picked = new Set()">Auswahl aufheben</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, errText, hasRole } from '../api.js'
import { inp, card, td, btnPrimary, btnGhost, btnLink } from '../ui.js'

const rows = ref([]), q = ref(''), filter = ref('valid'), err = ref(''), msg = ref(''), loading = ref(true)
const picked = ref(new Set()), canReserve = hasRole('planer')
const fmtDate = s => s ? s.split('-').reverse().join('.') : ''

const groups = computed(() => {
  const m = new Map()
  for (const r of rows.value) { if (!m.has(r.purpose)) m.set(r.purpose, []); m.get(r.purpose).push(r) }
  return [...m].map(([purpose, rs]) => ({ purpose, rows: rs }))
})

async function load() {
  loading.value = true
  try {
    const params = { q: q.value || undefined, expired: filter.value === 'expired' ? true : filter.value === 'valid' ? false : undefined }
    rows.value = await api.reservations(params); err.value = ''
    const ids = new Set(rows.value.map(r => r.id)); picked.value = new Set([...picked.value].filter(i => ids.has(i)))
  } catch (e) { err.value = errText(e) } finally { loading.value = false }
}
let timer
function debouncedLoad() { clearTimeout(timer); timer = setTimeout(load, 300) }

function toggle(id) { const s = new Set(picked.value); s.has(id) ? s.delete(id) : s.add(id); picked.value = s }
function pickGroup(g, on) { const s = new Set(picked.value); g.rows.forEach(r => on ? s.add(r.id) : s.delete(r.id)); picked.value = s }

async function releasePicked() {
  if (!confirm(`${picked.value.size} Reservierung(en) freigeben?`)) return
  try { const r = await api.releaseReservations([...picked.value]); msg.value = `${r.released} freigegeben.`; picked.value = new Set(); await load() }
  catch (e) { err.value = errText(e) }
}
async function editPicked() {
  const first = rows.value.find(r => picked.value.has(r.id))
  const purpose = prompt('Wofür (Projekt, Zweck):', first?.purpose || '')
  if (!purpose || !purpose.trim()) return
  const until = prompt('Reserviert bis (JJJJ-MM-TT, leer = unbefristet):', first?.until || '')
  if (until === null) return
  try {
    for (const id of picked.value) {
      const r = rows.value.find(x => x.id === id)
      await api.updateReservation(id, { purpose: purpose.trim(), until: until.trim() || null, workorder_id: r?.workorder?.id || null })
    }
    msg.value = 'Geändert.'; await load()
  } catch (e) { err.value = errText(e) }
}

onMounted(load)
</script>
