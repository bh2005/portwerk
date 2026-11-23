<template>
  <div class="max-w-5xl space-y-5">
    <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Übersicht</h1>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <div v-if="ready.length" :class="card" class="p-4 border-l-4 border-l-green-500">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-green-700 dark:text-green-400 mb-2">Zur Bestätigung vorgeschlagen ({{ ready.length }}) – LLDP stimmt</h2>
      <ul class="divide-y divide-slate-100 dark:divide-slate-700 text-sm">
        <li v-for="w in ready" :key="w.id" class="py-1.5 flex items-center gap-3">
          <router-link :to="`/workorders/${w.id}`" class="font-mono font-medium text-ks-700 dark:text-ks-400 hover:underline">{{ w.number }}</router-link>
          <span class="flex-1 truncate text-slate-700 dark:text-slate-200">{{ w.title }}</span>
          <span class="text-xs text-slate-400 whitespace-nowrap">ausgeführt von {{ w.finished_by || '–' }}</span>
        </li>
      </ul>
    </div>
    <div v-if="tasks.length" :class="card" class="p-4">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Meine Aufgaben ({{ tasks.length }})</h2>
      <ul class="divide-y divide-slate-100 dark:divide-slate-700 text-sm">
        <li v-for="w in tasks" :key="w.id" class="py-1.5 flex items-center gap-3">
          <router-link :to="`/workorders/${w.id}`" class="font-mono font-medium text-ks-700 dark:text-ks-400 hover:underline">{{ w.number }}</router-link>
          <span class="flex-1 truncate text-slate-700 dark:text-slate-200">{{ w.title }}</span>
          <span v-if="w.assigned_to && w.assigned_to.username !== myName" class="text-xs text-sky-700 dark:text-sky-300 whitespace-nowrap">in Vertretung für {{ w.assigned_to.full_name || w.assigned_to.username }}</span>
          <span class="text-xs text-slate-400 whitespace-nowrap">{{ w.status_label }} · {{ w.progress.done }}/{{ w.progress.total }}</span>
        </li>
      </ul>
    </div>
    <template v-if="s">
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Standorte" :value="s.sites" />
        <StatCard label="Racks" :value="s.racks" :hint="`${s.locations} Locations`" />
        <StatCard label="Geräte" :value="s.devices" :hint="s.devices_without_location ? `${s.devices_without_location} ohne Location` : ''" :warn="!!s.devices_without_location" />
        <StatCard label="Ports" :value="s.ports" />
        <StatCard label="Aktiv" :value="s.devices_by_status.active || 0" :hint="`${s.devices_by_status.planned || 0} geplant`" />
      </div>

      <router-link v-if="cap && cap.alerts" to="/capacity" :class="card" class="block p-4 border-l-4 border-l-red-500 hover:shadow-md transition-shadow">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Kapazität: {{ cap.alerts }} Engpass/Engpässe (unter {{ cap.warn }} % frei)</h2>
          <span class="text-xs text-ks-600 dark:text-ks-400">Kapazität öffnen →</span>
        </div>
        <ul class="mt-2 text-sm space-y-0.5">
          <li v-for="(a, i) in cap.worst" :key="i"><span class="text-red-600 font-medium tabular-nums">{{ a.free_pct }} %</span>
            <span class="ml-2 text-slate-700 dark:text-slate-200">{{ a.label }}</span><span class="ml-1 text-slate-500">· {{ a.path }}</span></li>
        </ul>
      </router-link>

      <div class="grid md:grid-cols-3 gap-3">
        <div v-for="g in groups" :key="g.title" :class="card" class="p-4">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">{{ g.title }}</h2>
          <p v-if="!g.rows.length" class="text-sm text-slate-400">Noch keine Daten</p>
          <div v-for="[k, n] in g.rows" :key="k" class="flex items-center gap-2 text-sm py-0.5">
            <span class="w-28 text-slate-600 dark:text-slate-300 truncate">{{ g.label(k) }}</span>
            <div class="flex-1 h-2 rounded bg-slate-100 dark:bg-slate-700"><div class="h-2 rounded bg-ks-500" :style="{ width: (n / s.devices * 100) + '%' }"></div></div>
            <span class="w-8 text-right text-slate-500">{{ n }}</span>
          </div>
        </div>
      </div>

      <div :class="card" class="p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">Letzte Importe</h2>
        <p v-if="!s.last_imports.length" class="text-sm text-slate-400">Noch kein Import. Unter „Import“ kannst du Geräte aus CSV, JSON oder Checkmk einlesen.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Zeit</th><th :class="th">Quelle</th><th :class="th">Art</th><th :class="th">Ergebnis</th></tr></thead>
          <tbody>
            <tr v-for="r in s.last_imports" :key="r.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td">{{ fmtTime(r.started_at) }}</td>
              <td :class="td">{{ sourceLabel(r.source) }}</td>
              <td :class="td">{{ r.dry_run ? 'Trockenlauf' : (r.stats.applied ? 'angewendet' : 'nicht angewendet') }}</td>
              <td :class="td" class="text-slate-500">{{ r.stats.created }} neu · {{ r.stats.updated }} geändert · {{ r.stats.unchanged }} gleich<span v-if="r.stats.errors" class="text-red-500"> · {{ r.stats.errors }} Fehler</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import StatCard from '../components/StatCard.vue'
import { api, errText, hasRole, getUser } from '../api.js'
import { card, th, td, typeLabel, statusLabel, sourceLabel, fmtTime } from '../ui.js'

const myName = getUser().username

const s = ref(null), error = ref(''), tasks = ref([]), cap = ref(null), ready = ref([])
const sorted = o => Object.entries(o || {}).sort((a, b) => b[1] - a[1])
const groups = computed(() => !s.value ? [] : [
  { title: 'Nach Typ', rows: sorted(s.value.devices_by_type), label: typeLabel },
  { title: 'Nach Status', rows: sorted(s.value.devices_by_status), label: statusLabel },
  { title: 'Nach Quelle', rows: sorted(s.value.devices_by_source), label: sourceLabel },
])
onMounted(async () => {
  try { s.value = await api.stats() } catch (e) { error.value = errText(e) }
  try { cap.value = await api.capacitySummary() } catch { /* Kapazität ist optional */ }
  if (hasRole('freigeber')) { try { ready.value = (await api.workorders({ status: 'done' })).filter(w => w.lldp_status === 'ok') } catch { /* optional */ } }
  try { tasks.value = (await api.workorders({ assigned: 'me' })).filter(w => !['confirmed', 'rejected'].includes(w.status)) } catch { /* ohne Aufträge keine Karte */ }
})
</script>
