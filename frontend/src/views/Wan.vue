<template>
  <div class="max-w-7xl space-y-4">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">WAN-Verbindungen</h1>
      <div class="flex gap-2">
        <a :class="btnGhost" :href="csvUrl" @click.prevent="downloadCsv">CSV-Export</a>
        <button v-if="canWrite" :class="btnPrimary" @click="openForm()">+ WAN-Verbindung</button>
      </div>
    </div>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>
    <p v-if="note" class="text-sm text-green-600 dark:text-green-400">{{ note }}</p>

    <div class="flex flex-wrap gap-3 items-center">
      <input v-model="q" :class="inp" class="max-w-xs" placeholder="Suchen (Name, Provider, Leitungs-ID …)" @input="loadSoon" />
      <select v-model="fStatus" :class="inp" class="max-w-[11rem]" @change="load"><option value="">alle Status</option><option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option></select>
      <select v-model="fSite" :class="inp" class="max-w-[14rem]" @change="load"><option value="">alle Standorte</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="expiring" @change="load" /> Vertrag läuft in 90 Tagen aus</label>
    </div>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th :class="th">Name</th><th :class="th">Status</th><th :class="th">Strecke</th><th :class="th">Technik</th><th :class="th">Provider / Leitung</th>
          <th :class="th">Bandbreite</th><th :class="th">Vertragsende</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="l in links" :key="l.id" class="border-t border-slate-100 dark:border-slate-700" :class="sel?.id === l.id ? 'bg-ks-50 dark:bg-ks-900/20' : ''">
            <td :class="td" class="font-medium text-slate-800 dark:text-slate-100">{{ l.name }}</td>
            <td :class="td"><span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="statusClass(l.status)">{{ $t(l.status_label) }}</span></td>
            <td :class="td" class="text-xs text-slate-600 dark:text-slate-300">{{ l.site_a }}<span class="text-slate-400"> ↔ </span>{{ l.site_b || '–' }}</td>
            <td :class="td" class="text-xs">{{ $t(l.technology_label) }}</td>
            <td :class="td" class="text-xs">{{ l.provider || '–' }}<span v-if="l.circuit_id" class="block font-mono text-slate-400">{{ l.circuit_id }}</span></td>
            <td :class="td" class="text-xs">{{ bw(l) }}</td>
            <td :class="td" class="text-xs"><template v-if="l.contract_end">{{ l.contract_end }}<span v-if="l.status !== 'terminated' && l.days_left != null && l.days_left <= 90" class="block" :class="l.days_left < 0 ? 'text-red-600' : 'text-amber-600'">{{ l.days_left < 0 ? 'abgelaufen' : `in ${l.days_left} Tagen` }}</span></template><span v-else class="text-slate-400">–</span></td>
            <td :class="td" class="text-right whitespace-nowrap"><button :class="btnLink" @click="select(l)">Details</button></td>
          </tr>
          <tr v-if="!links.length"><td colspan="8" class="px-3 py-6 text-center text-slate-400">Keine WAN-Verbindungen gefunden.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Details (Seitenleiste von rechts) -->
    <SidePanel :open="!!sel" :close-on-esc="!form" @close="sel = null">
      <template #title>
        <template v-if="sel">
          <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100 break-words">{{ sel.name }}</h2>
          <p class="text-xs text-slate-400 mt-0.5"><span class="px-2 py-0.5 rounded-full text-xs font-medium mr-2" :class="statusClass(sel.status)">{{ $t(sel.status_label) }}</span>{{ sel.site_a }} ↔ {{ sel.site_b || '–' }} · {{ $t(sel.technology_label) }}</p>
        </template>
      </template>
      <template v-if="sel">
        <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div v-for="[k, v] in details" :key="k" :class="WIDE.includes(k) ? 'sm:col-span-2' : ''"><dt :class="lbl">{{ k }}</dt><dd class="text-slate-700 dark:text-slate-200 break-words whitespace-pre-line">{{ v || '–' }}</dd></div>
        </dl>
        <div v-if="sel.orders?.length">
          <h3 :class="lbl">Aufträge</h3>
          <ul class="text-sm space-y-1"><li v-for="o in sel.orders" :key="o.id + o.action">
            <router-link :to="`/workorders/${o.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ o.number }}</router-link> {{ o.title }} <span class="text-xs text-slate-400">· {{ ACTIONS[o.action] || o.action }} · {{ o.status }}</span></li></ul>
        </div>
      </template>
      <template #footer v-if="sel && canPlan(sel)">
        <div class="flex gap-3 items-center flex-wrap">
          <button v-if="sel.status !== 'active' && sel.status !== 'terminated'" :class="btnPrimary" :disabled="busy" @click="orderFor(sel, 'wan_activate')">In Betrieb nehmen (Auftrag)</button>
          <button v-if="sel.status !== 'terminated'" :class="btnGhost" :disabled="busy" @click="openForm(sel, true)">Ändern per Auftrag …</button>
          <button v-if="sel.status !== 'terminated'" :class="btnDanger" :disabled="busy" @click="orderFor(sel, 'wan_terminate')">Kündigen (Auftrag)</button>
          <template v-if="canWrite">
            <button :class="btnLink" @click="openForm(sel)">Direkt bearbeiten</button>
            <button v-if="['planned', 'terminated'].includes(sel.status)" :class="btnDanger" @click="remove(sel)">Löschen</button>
          </template>
        </div>
      </template>
    </SidePanel>

    <!-- Formular -->
    <ModalDialog v-if="form" wide :title="formTitle" :error="formError" @close="form = null">
      <p v-if="asOrder" class="text-xs text-slate-400">Es wird ein Patchauftrag mit den geänderten Feldern angelegt. Die Verbindung selbst ändert sich erst, wenn der Auftrag bestätigt wird.</p>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">Name</label><input v-model="form.name" :class="inp" placeholder="z. B. MPLS Werk A ↔ Werk B" /></div>
        <div v-if="!asOrder"><label :class="lbl">Status</label><select v-model="form.status" :class="inp"><option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option></select></div>
        <div><label :class="lbl">Technik</label><select v-model="form.technology" :class="inp"><option v-for="t in meta.technologies" :key="t.value" :value="t.value">{{ t.label }}</option></select></div>
        <div><label :class="lbl">Standort A</label><select v-model="form.site_a_id" :class="inp" :disabled="asOrder"><option :value="null" disabled>wählen …</option><option v-for="s in writeSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
        <div><label :class="lbl">Standort B (Gegenstelle)</label><select v-model="form.site_b_id" :class="inp"><option :value="null">(kein eigener Standort)</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
        <div v-if="!form.site_b_id"><label :class="lbl">Gegenstelle (Freitext)</label><input v-model="form.remote_label" :class="inp" placeholder="z. B. Internet, Provider-Wolke, Cloud" /></div>
        <div><label :class="lbl">Port A (optional)</label><select v-model="form.port_a_id" :class="inp"><option :value="null">–</option><option v-for="p in portsA" :key="p.id" :value="p.id">{{ p.label }}</option></select></div>
        <div><label :class="lbl">Port B (optional)</label><select v-model="form.port_b_id" :class="inp" :disabled="!form.site_b_id"><option :value="null">–</option><option v-for="p in portsB" :key="p.id" :value="p.id">{{ p.label }}</option></select></div>
        <div><label :class="lbl">Provider</label><input v-model="form.provider" :class="inp" /></div>
        <div><label :class="lbl">Leitungs-ID / Circuit-ID</label><input v-model="form.circuit_id" :class="inp" /></div>
        <div><label :class="lbl">Bandbreite Down (Mbit/s)</label><input v-model.number="form.bandwidth_down" type="number" min="0" step="any" :class="inp" /></div>
        <div><label :class="lbl">Bandbreite Up (Mbit/s)</label><input v-model.number="form.bandwidth_up" type="number" min="0" step="any" :class="inp" /></div>
        <div><label :class="lbl">Vertragsnummer</label><input v-model="form.contract_number" :class="inp" /></div>
        <div><label :class="lbl">Kosten pro Monat</label><input v-model.number="form.monthly_cost" type="number" min="0" step="any" :class="inp" /></div>
        <div><label :class="lbl">Vertragsbeginn</label><input v-model="form.contract_start" type="date" :class="inp" /></div>
        <div><label :class="lbl">Vertragsende</label><input v-model="form.contract_end" type="date" :class="inp" /></div>
        <div><label :class="lbl">Kündigungsfrist (Tage)</label><input v-model.number="form.notice_days" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Ansprechpartner / Störungsnummer</label><input v-model="form.contact" :class="inp" /></div>
      </div>
      <div><label :class="lbl">Notiz</label><input v-model="form.note" :class="inp" /></div>
      <template #footer>
        <button :class="btnGhost" @click="form = null">Abbrechen</button>
        <button :class="btnPrimary" :disabled="busy || !form.name || !form.site_a_id" @click="submit">{{ asOrder ? $t('Änderungsauftrag anlegen') : $t('Speichern') }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import SidePanel from '../components/SidePanel.vue'
import { api, errText, canWriteMaster, getToken, isGlobal, scopesOf, siteAdminIds } from '../api.js'
import { inp, lbl, card, btnPrimary, btnGhost, btnDanger, btnLink, th, td } from '../ui.js'

const route = useRoute(), router = useRouter()
const canWrite = canWriteMaster()
const links = ref([]), sites = ref([]), meta = ref({ statuses: [], technologies: [] }), sel = ref(null)
const q = ref(''), fStatus = ref(''), fSite = ref(''), expiring = ref(false)
const error = ref(''), note = ref(''), busy = ref(false)
const form = ref(null), formError = ref(''), asOrder = ref(false), editId = ref(null), original = ref(null)
const portsA = ref([]), portsB = ref([])
const WIDE = ['Kontakt', 'Notiz']
const csvUrl = '/api/wan/export.csv'
const ACTIONS = { wan_activate: 'in Betrieb nehmen', wan_change: 'ändern', wan_terminate: 'kündigen' }
const FIELDS = ['name', 'technology', 'provider', 'circuit_id', 'bandwidth_down', 'bandwidth_up', 'contract_number', 'contract_start', 'contract_end',
  'notice_days', 'monthly_cost', 'contact', 'note', 'remote_label', 'site_b_id', 'port_a_id', 'port_b_id']

const writeSites = computed(() => isGlobal() ? sites.value : sites.value.filter(s => siteAdminIds().includes(s.id)))
const canPlan = l => isGlobal() || scopesOf().some(x => x.site_id === l.site_a_id && ['planer', 'admin'].includes(x.role))
const formTitle = computed(() => asOrder.value ? `${original.value?.name}: Änderung per Auftrag` : editId.value ? 'WAN-Verbindung bearbeiten' : 'Neue WAN-Verbindung')
const statusClass = s => ({ planned: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300', ordered: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', suspended: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  terminated: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' }[s] || '')
const bw = l => l.bandwidth_down || l.bandwidth_up ? `${l.bandwidth_down ?? '–'} / ${l.bandwidth_up ?? '–'} Mbit/s` : '–'
const portLabel = p => p ? `${p.device_hostname}:${p.name}` : ''
const details = computed(() => !sel.value ? [] : [
  ['Port A', portLabel(sel.value.port_a)], ['Port B', portLabel(sel.value.port_b)], ['Bandbreite (Down / Up)', bw(sel.value) === '–' ? '' : bw(sel.value)],
  ['Vertragsnummer', sel.value.contract_number], ['Vertragsbeginn', sel.value.contract_start], ['Vertragsende', sel.value.contract_end],
  ['Kündigungsfrist', sel.value.notice_days != null ? `${sel.value.notice_days} Tage` : ''], ['Kosten / Monat', sel.value.monthly_cost != null ? sel.value.monthly_cost.toFixed(2) : ''],
  ['Kontakt', sel.value.contact], ['Notiz', sel.value.note]])

watch([() => form.value?.site_a_id, () => form.value?.site_b_id], refreshPorts)
let timer
const loadSoon = () => { clearTimeout(timer); timer = setTimeout(load, 250) }
async function load() {
  error.value = ''
  try {
    links.value = await api.wanLinks({ q: q.value || undefined, status: fStatus.value || undefined, site_id: fSite.value || undefined, expiring_days: expiring.value ? 90 : undefined })
    if (sel.value) sel.value = links.value.find(l => l.id === sel.value.id) ? await api.wanLink(sel.value.id) : null
  } catch (e) { error.value = errText(e) }
}
async function select(l) { try { sel.value = await api.wanLink(l.id) } catch (e) { error.value = errText(e) } }
async function downloadCsv() {
  const r = await fetch(csvUrl, { headers: { 'X-Auth-Token': getToken() } })
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'wan-verbindungen.csv'; a.click(); URL.revokeObjectURL(a.href)
}

async function portsOf(siteId) {
  if (!siteId) return []
  const devs = (await api.devices({ site_id: siteId, limit: 500 })).items || []
  const out = []
  for (const d of devs) {
    if (!['router', 'firewall', 'switch', 'gateway', 'media_converter'].includes(d.type)) continue
    for (const p of await api.devicePorts(d.id)) out.push({ id: p.id, label: `${d.hostname}:${p.name}` })
  }
  return out
}
async function refreshPorts() {
  if (!form.value) return
  try { portsA.value = await portsOf(form.value.site_a_id); portsB.value = await portsOf(form.value.site_b_id) } catch { portsA.value = portsB.value = [] }
}

function openForm(l = null, order = false) {
  formError.value = ''; asOrder.value = order; editId.value = l?.id || null; original.value = l
  form.value = l ? { ...l } : { name: '', status: 'planned', technology: 'other', site_a_id: writeSites.value[0]?.id ?? null, site_b_id: null, remote_label: '', port_a_id: null, port_b_id: null,
    provider: '', circuit_id: '', bandwidth_down: null, bandwidth_up: null, contract_number: '', contract_start: null, contract_end: null, notice_days: null, monthly_cost: null, contact: '', note: '' }
  refreshPorts()
}

async function submit() {
  busy.value = true; formError.value = ''
  try {
    if (asOrder.value) {
      const patch = {}
      for (const k of FIELDS) { const a = form.value[k] ?? null, b = original.value[k] ?? null; if ((a === '' ? null : a) !== (b === '' ? null : b)) patch[k] = form.value[k] === '' ? null : form.value[k] }
      if (!Object.keys(patch).length) { formError.value = 'Es wurde nichts geändert.'; return }
      await makeOrder(original.value, 'wan_change', patch)
    } else {
      const saved = editId.value ? await api.updateWan(editId.value, form.value) : await api.createWan(form.value)
      form.value = null; note.value = 'Gespeichert.'; await load(); await select(saved)
    }
  } catch (e) { formError.value = errText(e) } finally { busy.value = false }
}

async function makeOrder(l, action, patch) {
  const loc = (await api.locations(l.site_a_id))[0]
  const wo = await api.createWorkorder({ title: `WAN ${ACTIONS[action]}: ${l.name}`, location_id: loc?.id ?? null })
  await api.addWorkitem(wo.id, { action, wan_link_id: l.id, wan_patch: patch || {} })
  router.push(`/workorders/${wo.id}`)
}
async function orderFor(l, action) {
  if (!confirm(`Patchauftrag „WAN ${ACTIONS[action]}: ${l.name}“ anlegen?`)) return
  busy.value = true; error.value = ''
  try { await makeOrder(l, action) } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
async function remove(l) {
  if (!confirm(`WAN-Verbindung „${l.name}“ löschen?`)) return
  try { await api.deleteWan(l.id); sel.value = null; await load() } catch (e) { error.value = errText(e) }
}

onMounted(async () => {
  try { [sites.value, meta.value] = await Promise.all([api.sites(), api.wanMeta()]) } catch (e) { error.value = errText(e) }
  await load()
  const id = Number(route.query.id)
  if (id) { try { sel.value = await api.wanLink(id) } catch { /* nicht sichtbar */ } }
})
</script>
