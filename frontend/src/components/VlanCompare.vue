<template>
  <div class="space-y-4">
    <p class="text-sm text-slate-500 dark:text-slate-400">
      {{ $t('Vergleicht die dokumentierte VLAN-Konfiguration (Soll) mit den VLANs, die Checkmk im Inventar meldet (Ist). Checkmk liefert diese Daten nur für') + ' ' }}<b>{{ $t('Cisco') }}</b>{{ ' ' + $t('und nur') + ' ' }}<b>{{ $t('Access-VLANs') }}</b>{{ ' ' + $t('– Trunks und Voice-VLANs werden nicht gemeldet.') }}
      <template v-if="res">{{ ' ' + $t('Grundlage: {n} Gerät(e) mit VLAN-Daten.', { n: res.devices }) }}</template></p>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>

    <div class="flex flex-wrap gap-2 items-center">
      <button v-for="[k, l] in chips" :key="k" type="button" @click="toggle(k)" class="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
        :class="active.has(k) ? chipClass(k) + ' border-transparent' : 'bg-white dark:bg-slate-800 text-slate-500 border-slate-300 dark:border-slate-600'">
        {{ $t(l) }} <span class="font-semibold">{{ res?.summary[k] ?? 0 }}</span></button>
      <select v-model="fSite" :class="inp" class="max-w-[14rem] ml-auto" @change="load"><option value="">{{ $t('alle Standorte') }}</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
      <input v-model="q" :class="inp" class="max-w-xs" :placeholder="$t('Gerät/Port filtern …')" />
    </div>

    <div v-if="canWrite && adoptable.length" class="flex items-center gap-3 text-sm">
      <span class="text-slate-500">{{ $t('{n} gewählt', { n: picked.size }) }}</span>
      <button :class="btnPrimary" class="!py-1 !px-3 !text-xs" :disabled="!picked.size" @click="adopt">{{ $t('Ist übernehmen') }}</button>
      <button :class="btnLink" @click="picked = new Set(adoptable.map(r => r.port_id))">{{ $t('alle übernehmbaren wählen ({n})', { n: adoptable.length }) }}</button>
      <span class="text-xs text-slate-400">{{ $t('trägt das gemeldete Access-VLAN als Doku ein (Historie: „checkmk“)') }}</span>
    </div>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th v-if="canWrite" :class="th" class="w-6"></th><th :class="th">{{ $t('Ergebnis') }}</th><th :class="th">{{ $t('Gerät : Port') }}</th>
          <th :class="th">{{ $t('Soll (dokumentiert)') }}</th><th :class="th">{{ $t('Ist (Checkmk)') }}</th><th :class="th">{{ $t('Hinweis') }}</th></tr></thead>
        <tbody>
          <tr v-for="r in shown" :key="r.port_id" class="border-t border-slate-100 dark:border-slate-700 align-top">
            <td v-if="canWrite" :class="td"><input v-if="r.adoptable" type="checkbox" :checked="picked.has(r.port_id)" @change="pick(r.port_id)" /></td>
            <td :class="td"><span class="px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap" :class="chipClass(r.status)">{{ $t(r.status_label) }}</span></td>
            <td :class="td" class="font-mono text-xs"><router-link :to="`/devices/${r.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ r.device }}</router-link>:{{ r.port }}</td>
            <td :class="td" class="text-xs">{{ r.soll }}</td>
            <td :class="td" class="text-xs font-mono">{{ r.ist }}</td>
            <td :class="td" class="text-xs text-slate-500">{{ r.why }}</td>
          </tr>
          <tr v-if="!shown.length"><td :colspan="canWrite ? 6 : 5" class="px-3 py-6 text-center text-slate-400">
            {{ res && !res.devices ? $t('Noch keine VLAN-Daten – sie kommen mit dem Checkmk-Import, sofern Checkmk VLANs im Inventar führt (Cisco).') : $t('Keine Einträge für diese Auswahl.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, onMounted, ref } from 'vue'
import { api, errText, canWriteMaster, isSiteAdmin, defaultSite } from '../api.js'
import { inp, card, th, td, btnPrimary, btnLink } from '../ui.js'

const canWrite = canWriteMaster() || isSiteAdmin()
const res = ref(null), sites = ref([]), fSite = ref(defaultSite() || ''), q = ref(''), error = ref(''), msg = ref(''), picked = ref(new Set())
const active = ref(new Set(['mismatch', 'undocumented', 'not_reported']))
const chips = [['mismatch', 'abweichend'], ['undocumented', 'nicht dokumentiert'], ['not_reported', 'nicht gemeldet'], ['unrated', 'nicht bewertbar'],
  ['plausible', 'plausibel (Trunk)'], ['ok', 'stimmt']]
const chipClass = s => ({ ok: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', mismatch: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  undocumented: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300', not_reported: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  unrated: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400', plausible: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300' }[s] || '')
const shown = computed(() => (res.value?.rows || []).filter(r => active.value.has(r.status) &&
  (!q.value || `${r.device}:${r.port} ${r.soll} ${r.ist}`.toLowerCase().includes(q.value.toLowerCase()))))
const adoptable = computed(() => shown.value.filter(r => r.adoptable))
function toggle(k) { const s = new Set(active.value); s.has(k) ? s.delete(k) : s.add(k); active.value = s }
function pick(id) { const s = new Set(picked.value); s.has(id) ? s.delete(id) : s.add(id); picked.value = s }

async function load() {
  error.value = ''
  try { res.value = await api.vlanCompare(fSite.value ? { site_id: fSite.value } : {}) } catch (e) { error.value = errText(e) }
}
async function adopt() {
  if (!confirm(t('Für {n} Port(s) das von Checkmk gemeldete Access-VLAN als Doku übernehmen?', { n: picked.value.size }))) return
  try {
    const r = await api.vlanAdopt([...picked.value])
    msg.value = t('{n} übernommen', { n: r.adopted }) + (r.skipped ? ', ' + t('{n} übersprungen (kein eindeutiges VLAN oder keine Berechtigung)', { n: r.skipped }) : '') + '.'
    picked.value = new Set(); await load()
  } catch (e) { error.value = errText(e) }
}
onMounted(async () => { try { sites.value = await api.sites() } catch { /* ignore */ } await load() })
</script>
