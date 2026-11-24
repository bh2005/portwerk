<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Zeitreise</h1>
      <div class="flex bg-white dark:bg-slate-800 rounded-lg p-1 shadow-sm text-sm">
        <button v-for="[k, l] in MODES" :key="k" class="px-3 py-1.5 rounded-md"
          :class="mode === k ? 'bg-ks-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="mode = k; load()">{{ l }}</button>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Grundlage ist die Verbindungs-Historie: welche Kabel wann zwischen welchen Ports steckten (Geräte- und Portnamen von damals).
      Orte und Patchfeld-Gegenseiten werden mit dem heutigen Stand gezeigt.
    </p>

    <div :class="card" class="p-4 flex flex-wrap items-end gap-3">
      <div><label :class="lbl">Standort</label>
        <select v-model="siteId" :class="inp" class="!w-56" @change="load">
          <option :value="null">alle</option>
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option>
        </select></div>
      <template v-if="mode === 'snapshot'">
        <div><label :class="lbl">Stand am</label><input v-model="at" type="datetime-local" :class="inp" @change="load" /></div>
      </template>
      <template v-else>
        <div><label :class="lbl">Von</label><input v-model="from" type="datetime-local" :class="inp" @change="load" /></div>
        <div><label :class="lbl">Bis (leer = jetzt)</label><input v-model="to" type="datetime-local" :class="inp" @change="load" /></div>
        <div class="flex gap-2 pb-1">
          <button v-for="[d, l] in PRESETS" :key="l" :class="btnLink" @click="preset(d)">{{ l }}</button>
        </div>
      </template>
      <div class="ml-auto"><label :class="lbl">Filter</label><input v-model="q" :class="inp" class="!w-56" placeholder="Gerät, Port, Kabel …" /></div>
    </div>
    <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>
    <p v-if="loading" class="text-sm text-slate-400">Lade …</p>

    <!-- Stand am -->
    <div v-if="mode === 'snapshot' && snap" :class="card" class="overflow-x-auto">
      <div class="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border-b border-slate-100 dark:border-slate-700">
        {{ shown(snap.connections).length }} Verbindungen am {{ fmtTime(snap.at) }}</div>
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Von</th><th :class="th">Nach</th><th :class="th">Kabel</th>
          <th :class="th">Gesteckt</th><th :class="th">Getrennt</th></tr></thead>
        <tbody>
          <tr v-for="c in shown(snap.connections)" :key="c.id" class="border-t border-slate-100 dark:border-slate-700">
            <td :class="td"><End :e="c.a" /></td><td :class="td"><End :e="c.b" /></td>
            <td :class="td" class="text-xs">{{ cable(c) }}</td>
            <td :class="td" class="text-xs whitespace-nowrap">{{ fmtTime(c.valid_from) }} <Who :name="c.created_by" :wo="c.workorder" /></td>
            <td :class="td" class="text-xs whitespace-nowrap">
              <span v-if="!c.valid_to" class="text-green-600 dark:text-green-400">steckt noch</span>
              <template v-else>{{ fmtTime(c.valid_to) }} <Who :name="c.ended_by" :wo="c.ended_workorder" /></template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Vergleich -->
    <template v-if="mode === 'diff' && dif">
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div v-for="[k, l, cls] in SUMMARY" :key="k" :class="card" class="px-4 py-3">
          <div class="text-xs uppercase tracking-wide text-slate-400">{{ l }}</div>
          <div class="text-2xl font-semibold" :class="cls">{{ dif.summary[k] }}</div>
        </div>
      </div>
      <p class="text-sm text-slate-500">{{ fmtTime(dif.from) }} → {{ fmtTime(dif.to) }} · vorher {{ dif.summary.before }}, nachher {{ dif.summary.after }} Verbindungen</p>

      <section v-if="dif.moved.length" :class="card" class="p-4">
        <h2 class="text-sm font-semibold text-amber-700 dark:text-amber-400 mb-2">↻ Umgesteckt ({{ dif.moved.length }})</h2>
        <div v-for="(m, i) in dif.moved.filter(x => match(x.before) || match(x.after))" :key="i" class="text-sm py-1.5 border-t first:border-t-0 border-slate-100 dark:border-slate-700 flex flex-wrap gap-x-2">
          <End :e="m.port" /><span class="text-slate-400">:</span>
          <span class="line-through text-slate-400"><End :e="m.from" plain /></span><span class="text-slate-400">→</span><End :e="m.to" />
          <span class="text-xs text-slate-500">{{ fmtTime(m.after.valid_from) }} <Who :name="m.after.created_by" :wo="m.after.workorder" /></span>
        </div>
      </section>
      <section v-for="[k, l, cls, sign] in LISTS" v-show="dif[k].length" :key="k" :class="card" class="p-4">
        <h2 class="text-sm font-semibold mb-2" :class="cls">{{ sign }} {{ l }} ({{ dif[k].length }})</h2>
        <div v-for="c in shown(dif[k])" :key="c.id" class="text-sm py-1.5 border-t first:border-t-0 border-slate-100 dark:border-slate-700 flex flex-wrap gap-x-2">
          <End :e="c.a" /><span class="text-slate-400">↔</span><End :e="c.b" />
          <span class="text-xs text-slate-500">{{ cable(c) }}</span>
          <span class="text-xs text-slate-500 ml-auto">
            <template v-if="k !== 'removed'">gesteckt {{ fmtTime(c.valid_from) }} <Who :name="c.created_by" :wo="c.workorder" /></template>
            <template v-if="k !== 'added' && c.valid_to"> · getrennt {{ fmtTime(c.valid_to) }} <Who :name="c.ended_by" :wo="c.ended_workorder" /></template>
          </span>
        </div>
      </section>
      <p v-if="!Object.values(dif.summary).slice(0, 5).some(Boolean)" class="text-sm text-slate-400">Keine Änderungen in diesem Zeitraum.</p>
    </template>
  </div>
</template>

<script setup>
import { h, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, errText, defaultSite } from '../api.js'
import { inp, lbl, card, th, td, btnLink, fmtTime } from '../ui.js'

const MODES = [['diff', 'Vergleich'], ['snapshot', 'Stand am']]
const PRESETS = [[7, '7 Tage'], [30, '30 Tage'], [90, '90 Tage'], ['year', 'seit Jahresbeginn']]
const SUMMARY = [['added', 'neu', 'text-green-600 dark:text-green-400'], ['removed', 'entfernt', 'text-red-600 dark:text-red-400'], ['moved', 'umgesteckt', 'text-amber-600 dark:text-amber-400'],
  ['changed', 'geändert', 'text-sky-600 dark:text-sky-400'], ['temporary', 'zwischenzeitlich', 'text-slate-500 dark:text-slate-400']]
const LISTS = [['added', 'Neu', 'text-green-700 dark:text-green-400', '+'], ['removed', 'Entfernt', 'text-red-700 dark:text-red-400', '−'],
  ['temporary', 'Nur zwischenzeitlich gesteckt', 'text-slate-600 dark:text-slate-300', '~']]

const End = (p) => {
  const t = `${p.e.hostname}:${p.e.port}`
  return p.e.device_id && !p.plain ? h(RouterLink, { to: `/devices/${p.e.device_id}`, class: 'font-mono text-xs text-ks-600 dark:text-ks-400 hover:underline' }, () => t)
    : h('span', { class: 'font-mono text-xs', title: p.e.device_id ? '' : 'Gerät/Port existiert nicht mehr' }, t)
}
End.props = ['e', 'plain']
const Who = (p) => p.wo ? h(RouterLink, { to: `/workorders/${p.wo.id}`, class: 'text-ks-600 dark:text-ks-400 hover:underline' }, () => p.wo.number)
  : (p.name ? h('span', { class: 'text-slate-400' }, `(${p.name})`) : null)
Who.props = ['name', 'wo']

const pad = n => String(n).padStart(2, '0')
const local = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
const daysAgo = n => { const d = new Date(); d.setDate(d.getDate() - n); return local(d) }

const mode = ref('diff'), sites = ref([]), siteId = ref(defaultSite()), q = ref(''), err = ref(''), loading = ref(false)
const at = ref(local(new Date())), from = ref(daysAgo(30)), to = ref('')
const snap = ref(null), dif = ref(null)

const cable = c => [c.cable_label, c.cable_type, c.length_m ? `${c.length_m} m` : '', c.color].filter(Boolean).join(' · ')
const match = c => !q.value || [c.a.hostname, c.a.port, c.b.hostname, c.b.port, c.cable_label].join(' ').toLowerCase().includes(q.value.toLowerCase())
const shown = list => list.filter(match)

function preset(d) {
  if (d === 'year') from.value = `${new Date().getFullYear()}-01-01T00:00`
  else from.value = daysAgo(d)
  to.value = ''; load()
}
async function load() {
  loading.value = true; err.value = ''
  try {
    const scope = { site_id: siteId.value || undefined }
    if (mode.value === 'snapshot') snap.value = await api.historySnapshot({ at: at.value, ...scope })
    else dif.value = await api.historyDiff({ from: from.value, to: to.value || undefined, ...scope })
  } catch (e) { err.value = errText(e) } finally { loading.value = false }
}
onMounted(async () => { try { sites.value = await api.sites() } catch {} ; load() })
</script>
