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
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>

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
              <span v-else-if="r.soll?.why" class="text-amber-600 dark:text-amber-400">{{ r.soll.why }}</span>
              <span v-else class="text-slate-400">nicht dokumentiert</span>
            </td>
            <td :class="td" class="text-xs">
              <div v-for="(i, n) in r.ist" :key="n"><span class="font-mono text-slate-700 dark:text-slate-200">{{ i.name }}<template v-if="i.port">:{{ i.port }}</template></span>
                <span class="text-slate-400"> · {{ i.protocol.toUpperCase() }}<template v-if="!i.device_id"> · nicht im Bestand</template></span>
                <button v-if="!i.device_id && canWrite && !isMac(i.name)" :class="btnLink" class="ml-2" title="Gerät samt Port im Bestand anlegen" @click="openAdoptDevice(r, i)">In Bestand übernehmen</button></div>
              <span v-if="!r.ist.length" class="text-slate-400">kein Nachbar gesehen</span>
            </td>
            <td :class="td" class="text-right whitespace-nowrap">
              <button v-if="r.adopt && canWrite" :class="btnLink" class="mr-3" :disabled="busy === r.port_id"
                :title="`Als Direktkabel zu ${r.adopt.label} dokumentieren (vorläufig – Dosen und Patchfelder später nachtragen)`" @click="adopt(r)">Verbindung übernehmen</button>
              <button v-if="r.port_id" :class="btnLink" class="mr-3" title="Ganze Strecke ansehen und bearbeiten" @click="strecke = r.port_id">Strecke</button>
              <button v-if="r.port_id" :class="btnLink" class="mr-3" title="Frühere Verbindungen dieses Ports" @click="hist = { id: r.port_id, name: r.port, hostname: r.device, deviceId: r.device_id }">Historie</button>
              <router-link v-if="r.soll?.label || r.ist[0]?.port_id" class="text-xs text-ks-600 dark:text-ks-400 hover:underline" :to="`/devices/${r.device_id}`">Gerät →</router-link></td>
          </tr>
          <tr v-if="!shown.length"><td colspan="5" class="px-3 py-6 text-center text-slate-400">
            {{ res && !res.devices ? 'Noch keine Nachbardaten – sie kommen mit dem Checkmk-Import (Verwaltung → Checkmk).' : 'Keine Einträge für diese Auswahl.' }}</td></tr>
        </tbody>
      </table>
    </div>
    </template>
    <SidePanel :open="!!dev" title="In Bestand übernehmen" @close="dev = null">
      <template v-if="dev">
        <p class="text-sm text-slate-500 dark:text-slate-400">Gesehen von <b class="font-mono">{{ dev.row.device }}:{{ dev.row.port }}</b> per {{ dev.ist.protocol.toUpperCase() }}
          als <span class="font-mono">{{ dev.ist.name }}<template v-if="dev.ist.port">:{{ dev.ist.port }}</template></span>.
          Das Gerät wird am selben Ort wie {{ dev.row.device }} angelegt.</p>
        <div><label :class="lbl">Hostname</label><input v-model="dev.hostname" :class="inp" /></div>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Typ</label><select v-model="dev.type" :class="inp"><option v-for="t in DEVICE_TYPES" :key="t[0]" :value="t[0]">{{ t[1] }}</option></select>
            <p v-if="dev.ist.capabilities" class="text-xs text-slate-400 mt-1">Gemeldet: {{ dev.ist.capabilities }}</p></div>
          <div><label :class="lbl">Verwaltungs-IP</label><input v-model="dev.mgmt_ip" :class="inp" placeholder="optional" /></div>
        </div>
        <div><label :class="lbl">Port am neuen Gerät</label><input v-model="dev.neighbor_port" :class="inp" placeholder="leer = keinen Port anlegen" /></div>
        <label class="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300"><input v-model="dev.create_cable" type="checkbox" class="mt-1" :disabled="!dev.neighbor_port.trim()" />
          <span>Verbindung zu {{ dev.row.device }}:{{ dev.row.port }} als vorläufiges Direktkabel dokumentieren<span v-if="!dev.row.port_id" class="block text-xs text-slate-400">Der lokale Port ist noch nicht im Bestand und wird mit angelegt.</span></span></label>
        <div v-if="cmkOn" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2 text-sm">
          <div class="flex items-center justify-between"><span :class="lbl" class="!mb-0">Checkmk</span>
            <button :class="btnLink" @click="checkCmk">neu prüfen</button></div>
          <p v-if="dev.cmk.loading" class="text-slate-400">Prüfe …</p>
          <p v-else-if="dev.cmk.error" class="text-red-500 dark:text-red-400">{{ dev.cmk.error }}</p>
          <p v-else-if="dev.cmk.created" class="text-green-600 dark:text-green-400">In Checkmk angelegt (nur Ping) in {{ dev.cmk.folder }}. Die Änderung ist noch nicht aktiv.</p>
          <CheckmkActivate v-if="dev.cmk.created" />
          <p v-else-if="dev.cmk.exists" class="text-green-600 dark:text-green-400">In Checkmk vorhanden<span class="text-slate-500 dark:text-slate-400"> · {{ dev.cmk.folder || '/' }}<template v-if="dev.cmk.ipaddress"> · {{ dev.cmk.ipaddress }}</template></span></p>
          <template v-else-if="dev.cmk.exists === false">
            <p class="text-amber-600 dark:text-amber-400">Nicht in Checkmk vorhanden.</p>
            <div><label :class="lbl">Ordner in Checkmk</label>
              <select v-model="dev.cmk.folder" :class="inp"><option v-for="f in cmkFolders" :key="f.path" :value="f.path">{{ f.path }} · {{ f.title }}</option></select></div>
            <div><label :class="lbl">Standort-Tag (location)</label>
              <select v-model="dev.cmk.location" :class="inp"><option value="">keins</option><option v-for="t in cmkTags" :key="t.code" :value="t.code">{{ t.code }} · {{ t.name }}</option></select>
              <p v-if="dev.cmk.locationHint" class="text-xs text-slate-400 mt-1">{{ dev.cmk.locationHint }}</p></div>
            <button :class="btnGhost" :disabled="dev.cmk.busy || !dev.hostname.trim()" @click="createCmk">In Checkmk anlegen (nur Ping)</button>
            <p class="text-xs text-slate-400">Host mit reinem Host-Check, ohne Agent und SNMP; wird als ausstehende Änderung angelegt.</p>
          </template>
        </div>
        <p v-if="dev.error" class="text-sm text-red-500 dark:text-red-400">{{ dev.error }}</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2"><button :class="btnGhost" @click="dev = null">Abbrechen</button>
          <button :class="btnPrimary" :disabled="!dev || !dev.hostname.trim() || dev.busy" @click="adoptDevice">Übernehmen</button></div>
      </template>
    </SidePanel>
    <PathEditor :open="!!strecke" :port-id="strecke" @close="strecke = null" @changed="load" />
    <CableHistoryPanel :open="!!hist" :port-id="hist?.id ?? null" :device-id="hist?.deviceId ?? null" :hostname="hist?.hostname || ''" :port-name="hist?.name || ''" @close="hist = null" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errText, getToken, defaultSite, canWriteMaster } from '../api.js'
import { inp, lbl, card, btnGhost, btnPrimary, btnLink, th, td, DEVICE_TYPES } from '../ui.js'
import SidePanel from '../components/SidePanel.vue'
import CableHistoryPanel from '../components/CableHistoryPanel.vue'
import PathEditor from '../components/PathEditor.vue'
import CheckmkActivate from '../components/CheckmkActivate.vue'
import VlanCompare from '../components/VlanCompare.vue'

const TABS = [['lldp', 'Verkabelung (LLDP/CDP)'], ['vlan', 'VLANs (Checkmk)']]
const route = useRoute(), router = useRouter()
const tab = ref(route.query.tab === 'vlan' ? 'vlan' : 'lldp')
function setTab(k) { tab.value = k; router.replace({ query: k === 'vlan' ? { tab: 'vlan' } : {} }) }

const res = ref(null), sites = ref([]), fSite = ref(defaultSite() || ''), q = ref(''), error = ref(''), msg = ref(''), busy = ref(null), hist = ref(null), strecke = ref(null), dev = ref(null), cmkOn = ref(false), cmkFolders = ref([]), cmkDefault = ref('/')
const canWrite = canWriteMaster()
const cmkTags = computed(() => sites.value.filter(s => /^LOC\d+$/i.test(s.code)).map(s => ({ code: s.code, name: s.name })))
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
async function adopt(r) {
  if (!confirm(`${r.device}:${r.port} ↔ ${r.adopt.label} als Direktkabel dokumentieren?

Die Verbindung wird als „vorläufig“ markiert. Dosen und Patchfelder können später ergänzt werden.`)) return
  busy.value = r.port_id; error.value = ''; msg.value = ''
  try { await api.adoptConnection(r.port_id); msg.value = `Verbindung ${r.device}:${r.port} ↔ ${r.adopt.label} übernommen (vorläufig).`; await load() }
  catch (e) { error.value = errText(e) } finally { busy.value = null }
}
const isMac = n => /^([0-9a-f]{2}[:.-]?){5}[0-9a-f]{2}$/i.test(n || '')
function openAdoptDevice(row, ist) {
  dev.value = { row, ist, hostname: String(ist.name).split('.')[0].toLowerCase(), type: ist.type_guess || 'other', mgmt_ip: ist.address || '',
    neighbor_port: ist.port || '', create_cable: true, error: '', busy: false, cmk: { loading: false, exists: null, error: '', folder: cmkDefault.value, busy: false, created: false, location: '', locationHint: '' } }
  if (cmkOn.value) checkCmk()
}
async function checkCmk() {
  const c = dev.value?.cmk
  if (!c) return
  c.loading = true; c.error = ''; c.created = false
  try {
    const r = await api.checkmkHost(dev.value.hostname.trim())
    c.exists = r.exists; c.folder = r.exists ? r.folder : (c.folder || cmkDefault.value); c.ipaddress = r.ipaddress
    if (!r.exists) {
      if (!cmkFolders.value.length) cmkFolders.value = await api.checkmkFolders()
      const code = sites.value.find(s => s.id === dev.value.row.site_id)?.code || ''
      c.location = cmkTags.value.some(t => t.code === code) ? code : ''
      c.locationHint = c.location ? `aus dem Standort von ${dev.value.row.device} (${code})` : (code ? `Standort ${code} ist kein Checkmk-Tag – bitte wählen oder leer lassen` : '')
    }
  } catch (e) { c.error = errText(e) } finally { c.loading = false }
}
async function createCmk() {
  const d = dev.value, c = d.cmk
  c.busy = true; c.error = ''
  try { const r = await api.checkmkCreateHost({ hostname: d.hostname.trim(), ip: d.mgmt_ip.trim(), folder: c.folder, location_tag: c.location }); c.created = true; c.exists = true; c.folder = r.folder }
  catch (e) { c.error = errText(e) } finally { c.busy = false }
}
async function adoptDevice() {
  const d = dev.value
  d.busy = true; d.error = ''
  try {
    const r = await api.adoptDevice({ obs_id: d.ist.obs_id, hostname: d.hostname.trim(), type: d.type, mgmt_ip: d.mgmt_ip.trim(),
      neighbor_port: d.neighbor_port.trim(), create_cable: d.create_cable && !!d.neighbor_port.trim() })
    msg.value = `${r.hostname} in den Bestand übernommen` + (r.cable_id ? ' – Verbindung dokumentiert (vorläufig).' : r.cable_skipped ? ` – Kabel nicht angelegt (${r.cable_skipped}).` : '.')
    dev.value = null; await load()
  } catch (e) { d.error = errText(e); d.busy = false }
}
async function downloadCsv() {
  const sel = [...active.value].join(',')
  const r = await fetch(`/api/compare/export.csv?status=${sel}${fSite.value ? '&site_id=' + fSite.value : ''}`, { headers: { 'X-Auth-Token': getToken() } })
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'soll-ist.csv'; a.click(); URL.revokeObjectURL(a.href)
}
onMounted(async () => {
  try { const s = await api.checkmkStatus(); cmkOn.value = s.enabled; cmkDefault.value = s.default_folder } catch { /* Checkmk-Anbindung optional */ }
  try { sites.value = await api.sites() } catch { /* ignore */ }
  await load()
})
</script>
