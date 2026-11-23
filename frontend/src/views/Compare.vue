<template>
  <div class="max-w-7xl space-y-4">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Soll/Ist-Abgleich</h1>
      <a v-if="tab === 'lldp'" :class="btnGhost" href="#" @click.prevent="downloadCsv">CSV-Export</a>
    </div>
    <div class="flex gap-1 border-b border-slate-200 dark:border-slate-700">
      <button v-for="[k, l] in TABS" :key="k" @click="setTab(k)" class="px-4 py-2 text-sm -mb-px border-b-2 transition-colors"
        :class="tab === k ? 'border-ks-600 text-ks-700 dark:text-ks-300 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'">{{ l }}</button>
    </div>
    <VlanCompare v-if="tab === 'vlan'" />
    <template v-else>
    <p class="text-sm text-slate-500 dark:text-slate-400">Vergleicht die dokumentierte Verkabelung (Soll, auch über Patchfelder hinweg) mit den per LLDP/CDP gemeldeten Nachbarn (Ist).
      <template v-if="res"> Grundlage: {{ res.devices }} Gerät(e) mit Nachbardaten.</template></p>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

    <div class="flex flex-wrap gap-2 items-center">
      <button v-for="[k, l] in chips" :key="k" type="button" @click="toggle(k)" class="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
        :class="active.has(k) ? chipClass(k) + ' border-transparent' : 'bg-white dark:bg-slate-800 text-slate-500 border-slate-300 dark:border-slate-600'">
        {{ l }} <span class="font-semibold">{{ res?.summary[k] ?? 0 }}</span></button>
      <select v-model="fSite" :class="inp" class="max-w-[14rem] ml-auto" @change="load"><option value="">alle Standorte</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
      <input v-model="q" :class="inp" class="max-w-xs" placeholder="Gerät/Port filtern …" />
    </div>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th :class="th">Ergebnis</th><th :class="th">Gerät : Port</th><th :class="th">Soll (dokumentiert)</th><th :class="th">Ist (gesehen)</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="r in shown" :key="r.device_id + ':' + r.port" class="border-t border-slate-100 dark:border-slate-700 align-top">
            <td :class="td"><span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="chipClass(r.status)">{{ r.status_label }}</span></td>
            <td :class="td" class="font-mono text-xs"><router-link :to="`/devices/${r.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ r.device }}</router-link>:{{ r.port }}</td>
            <td :class="td" class="text-xs">
              <template v-if="r.soll?.label"><span class="font-mono text-slate-700 dark:text-slate-200">{{ r.soll.label }}</span>
                <span v-if="r.soll.via.length" class="block text-slate-400">über {{ r.soll.via.join(' → ') }}</span></template>
              <span v-else-if="r.soll?.why" class="text-amber-600">{{ r.soll.why }}</span>
              <span v-else class="text-slate-400">nicht dokumentiert</span>
            </td>
            <td :class="td" class="text-xs">
              <div v-for="(i, n) in r.ist" :key="n"><span class="font-mono text-slate-700 dark:text-slate-200">{{ i.name }}<template v-if="i.port">:{{ i.port }}</template></span>
                <span class="text-slate-400"> · {{ i.protocol.toUpperCase() }}<template v-if="!i.device_id"> · nicht im Bestand</template></span></div>
              <span v-if="!r.ist.length" class="text-slate-400">kein Nachbar gesehen</span>
            </td>
            <td :class="td" class="text-right"><router-link v-if="r.soll?.label || r.ist[0]?.port_id" class="text-xs text-ks-600 dark:text-ks-400 hover:underline" :to="`/devices/${r.device_id}`">Gerät →</router-link></td>
          </tr>
          <tr v-if="!shown.length"><td colspan="5" class="px-3 py-6 text-center text-slate-400">
            {{ res && !res.devices ? 'Noch keine Nachbardaten – sie kommen mit dem Checkmk-Import (Verwaltung → Checkmk).' : 'Keine Einträge für diese Auswahl.' }}</td></tr>
        </tbody>
      </table>
    </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errText, getToken, defaultSite } from '../api.js'
import { inp, card, btnGhost, th, td } from '../ui.js'
import VlanCompare from '../components/VlanCompare.vue'

const TABS = [['lldp', 'Verkabelung (LLDP/CDP)'], ['vlan', 'VLANs (Checkmk)']]
const route = useRoute(), router = useRouter()
const tab = ref(route.query.tab === 'vlan' ? 'vlan' : 'lldp')
function setTab(k) { tab.value = k; router.replace({ query: k === 'vlan' ? { tab: 'vlan' } : {} }) }

const res = ref(null), sites = ref([]), fSite = ref(defaultSite() || ''), q = ref(''), error = ref('')
const active = ref(new Set(['mismatch', 'port_mismatch', 'undocumented', 'not_seen', 'unmapped']))
const chips = [['mismatch', 'anderes Gerät'], ['port_mismatch', 'anderer Port'], ['undocumented', 'nicht dokumentiert'], ['not_seen', 'nicht gesehen'], ['unmapped', 'Port unbekannt'], ['unknown', 'keine Daten'], ['ok', 'stimmt']]
const chipClass = s => ({ ok: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', mismatch: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  port_mismatch: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', undocumented: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  not_seen: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300', unmapped: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  unknown: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400' }[s] || '')
const shown = computed(() => (res.value?.rows || []).filter(r => active.value.has(r.status) &&
  (!q.value || `${r.device}:${r.port} ${r.soll?.label || ''} ${r.ist.map(i => i.name + i.port).join(' ')}`.toLowerCase().includes(q.value.toLowerCase()))))
function toggle(k) { const s = new Set(active.value); s.has(k) ? s.delete(k) : s.add(k); active.value = s }

async function load() {
  error.value = ''
  try { res.value = await api.compare(fSite.value ? { site_id: fSite.value } : {}) } catch (e) { error.value = errText(e) }
}
async function downloadCsv() {
  const sel = [...active.value].join(',')
  const r = await fetch(`/api/compare/export.csv?status=${sel}${fSite.value ? '&site_id=' + fSite.value : ''}`, { headers: { 'X-Auth-Token': getToken() } })
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'soll-ist.csv'; a.click(); URL.revokeObjectURL(a.href)
}
onMounted(async () => { try { sites.value = await api.sites() } catch { /* ignore */ } await load() })
</script>
