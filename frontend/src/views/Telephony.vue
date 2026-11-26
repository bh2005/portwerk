<template>
  <div class="max-w-7xl space-y-4">
    <div class="flex items-center justify-between flex-wrap gap-3">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Telefonie') }}</h1>
      <div class="flex bg-white dark:bg-slate-800 rounded-lg p-1 shadow-sm text-sm">
        <button v-for="[k, l] in TABS" :key="k" class="px-3 py-1.5 rounded-md" :class="tab === k ? 'bg-ks-600 text-white' : 'text-slate-600 dark:text-slate-300'" @click="setTab(k)">{{ $t(l) }}</button>
      </div>
    </div>
    <NumberPlan v-if="tab === 'numbers'" />
    <template v-else>
    <div class="flex items-center justify-between flex-wrap gap-2">
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ $t('SIP-Trunks') }}</h2>
      <div class="flex gap-2">
        <a :class="btnGhost" :href="csvUrl" @click.prevent="downloadCsv">{{ $t('CSV-Export') }}</a>
        <button v-if="canWrite" :class="btnPrimary" @click="openForm()">{{ $t('+ SIP-Trunk') }}</button>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">{{ $t('Anschlüsse beim Provider mit Kanälen und Rufnummern, dazu SBC, TK-Anlage und die WAN-Leitung, über die der Trunk läuft. TK-Anlagen, SBCs, Gateways und Telefone sind normale Geräte (eigene Gerätetypen, Port-Medien UP0E, S0, S2M, a/b, TAE, LSA).') }}</p>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>
    <p v-if="note" class="text-sm text-green-600 dark:text-green-400">{{ note }}</p>

    <div class="flex flex-wrap gap-3 items-center">
      <input v-model="q" :class="inp" class="max-w-xs" :placeholder="$t('Suchen (Name, Provider, Kennung, Rufnummer …)')" @input="loadSoon" />
      <select v-model="fStatus" :class="inp" class="max-w-[11rem]" @change="load"><option value="">{{ $t('alle Status') }}</option><option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ $t(s.label) }}</option></select>
      <select v-model="fSite" :class="inp" class="max-w-[14rem]" @change="load"><option value="">{{ $t('alle Standorte') }}</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="expiring" @change="load" />{{ ' ' + $t('Vertrag läuft in 90 Tagen aus') }}</label>
    </div>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th :class="th">{{ $t('Name') }}</th><th :class="th">{{ $t('Status') }}</th><th :class="th">{{ $t('Standort') }}</th><th :class="th">{{ $t('Provider / Kennung') }}</th>
          <th :class="th">{{ $t('Kanäle') }}</th><th :class="th">{{ $t('SBC / TK-Anlage') }}</th><th :class="th">{{ $t('Vertragsende') }}</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="l in trunks" :key="l.id" class="border-t border-slate-100 dark:border-slate-700" :class="sel?.id === l.id ? 'bg-ks-50 dark:bg-ks-900/20' : ''">
            <td :class="td" class="font-medium text-slate-800 dark:text-slate-100">{{ l.name }}<span class="block text-xs font-normal text-slate-400">{{ $t(l.mode_label) }}</span></td>
            <td :class="td"><span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="statusClass(l.status)">{{ $t(l.status_label) }}</span></td>
            <td :class="td" class="text-xs text-slate-600 dark:text-slate-300">{{ l.site }}</td>
            <td :class="td" class="text-xs">{{ l.provider || '–' }}<span v-if="l.trunk_ident" class="block font-mono text-slate-400">{{ l.trunk_ident }}</span></td>
            <td :class="td" class="text-xs">{{ l.channels ?? '–' }}</td>
            <td :class="td" class="text-xs font-mono">
              <router-link v-if="l.sbc" :to="`/devices/${l.sbc.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ l.sbc.hostname }}</router-link><span v-else class="text-slate-400">–</span>
              <span class="text-slate-400"> / </span>
              <router-link v-if="l.pbx" :to="`/devices/${l.pbx.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ l.pbx.hostname }}</router-link><span v-else class="text-slate-400">–</span></td>
            <td :class="td" class="text-xs"><template v-if="l.contract_end">{{ l.contract_end }}<span v-if="l.status !== 'terminated' && l.days_left != null && l.days_left <= 90" class="block" :class="l.days_left < 0 ? 'text-red-600' : 'text-amber-600'">{{ l.days_left < 0 ? $t('abgelaufen') : $t('in {n} Tagen', { n: l.days_left }) }}</span></template><span v-else class="text-slate-400">–</span></td>
            <td :class="td" class="text-right whitespace-nowrap"><button :class="btnLink" @click="select(l)">{{ $t('Details') }}</button></td>
          </tr>
          <tr v-if="!trunks.length"><td colspan="8" class="px-3 py-6 text-center text-slate-400">{{ $t('Keine SIP-Trunks gefunden.') }}</td></tr>
        </tbody>
      </table>
    </div>

    </template>

    <!-- Details -->
    <SidePanel :open="!!sel" :close-on-esc="!form" @close="sel = null">
      <template #title>
        <template v-if="sel">
          <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100 break-words">{{ sel.name }}</h2>
          <p class="text-xs text-slate-400 mt-0.5"><span class="px-2 py-0.5 rounded-full text-xs font-medium mr-2" :class="statusClass(sel.status)">{{ $t(sel.status_label) }}</span>{{ sel.site }} · {{ $t(sel.mode_label) }}</p>
        </template>
      </template>
      <template v-if="sel">
        <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div><dt :class="lbl">{{ $t('SBC') }}</dt><dd><router-link v-if="sel.sbc" :to="`/devices/${sel.sbc.id}`" class="font-mono text-ks-600 dark:text-ks-400 hover:underline">{{ sel.sbc.hostname }}</router-link><span v-else>–</span></dd></div>
          <div><dt :class="lbl">{{ $t('TK-Anlage') }}</dt><dd><router-link v-if="sel.pbx" :to="`/devices/${sel.pbx.id}`" class="font-mono text-ks-600 dark:text-ks-400 hover:underline">{{ sel.pbx.hostname }}</router-link><span v-else>–</span></dd></div>
          <div class="sm:col-span-2"><dt :class="lbl">{{ $t('WAN-Leitung') }}</dt><dd><router-link v-if="sel.wan" :to="`/wan?id=${sel.wan.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ sel.wan.name }}</router-link>
            <span v-if="sel.wan" class="text-xs text-slate-400"> · {{ [sel.wan.provider, sel.wan.circuit_id].filter(Boolean).join(' · ') }}</span><span v-else>–</span></dd></div>
          <div v-for="[k, v] in details" :key="k" :class="WIDE.includes(k) ? 'sm:col-span-2' : ''"><dt :class="lbl">{{ $t(k) }}</dt><dd class="text-slate-700 dark:text-slate-200 break-words whitespace-pre-line">{{ v || '–' }}</dd></div>
        </dl>
        <div v-if="sel.number_blocks?.length || canWrite">
          <h3 :class="lbl">{{ $t('Rufnummernblöcke') }}</h3>
          <ul class="text-sm space-y-1"><li v-for="b in sel.number_blocks" :key="b.id">
            <router-link :to="`/telephony?tab=numbers&block=${b.id}`" class="font-mono text-ks-600 dark:text-ks-400 hover:underline" @click="tab = 'numbers'; sel = null">{{ b.first }} … {{ b.last.split('-').pop() }}</router-link>
            <span class="text-xs text-slate-400"> · {{ $t('{a} vergeben, {r} reserviert, {f} frei', { a: b.counts.assigned, r: b.counts.reserved, f: b.counts.free }) }}</span></li></ul>
          <p v-if="!sel.number_blocks?.length" class="text-xs text-slate-400">{{ $t('Noch kein Rufnummernblock – im Reiter „Rufnummernplan“ anlegen.') }}</p>
        </div>
        <div v-if="sel.orders?.length">
          <h3 :class="lbl">{{ $t('Aufträge') }}</h3>
          <ul class="text-sm space-y-1"><li v-for="o in sel.orders" :key="o.id + o.action">
            <router-link :to="`/workorders/${o.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ o.number }}</router-link> {{ o.title }} <span class="text-xs text-slate-400">· {{ ACTIONS[o.action] || o.action }} · {{ o.status }}</span></li></ul>
        </div>
      </template>
      <template #footer v-if="sel && canPlan(sel)">
        <div class="flex gap-3 items-center flex-wrap">
          <button v-if="sel.status !== 'active' && sel.status !== 'terminated'" :class="btnPrimary" :disabled="busy" @click="orderFor(sel, 'trunk_activate')">{{ $t('In Betrieb nehmen (Auftrag)') }}</button>
          <button v-if="sel.status !== 'terminated'" :class="btnGhost" :disabled="busy" @click="openForm(sel, true)">{{ $t('Ändern per Auftrag …') }}</button>
          <button v-if="sel.status !== 'terminated'" :class="btnDanger" :disabled="busy" @click="orderFor(sel, 'trunk_terminate')">{{ $t('Kündigen (Auftrag)') }}</button>
          <template v-if="canWrite">
            <button :class="btnLink" @click="openForm(sel)">{{ $t('Direkt bearbeiten') }}</button>
            <button v-if="['planned', 'terminated'].includes(sel.status)" :class="btnDanger" @click="remove(sel)">{{ $t('Löschen') }}</button>
          </template>
        </div>
      </template>
    </SidePanel>

    <!-- Formular -->
    <ModalDialog v-if="form" wide :title="formTitle" :error="formError" @close="form = null">
      <p v-if="asOrder" class="text-xs text-slate-400">{{ $t('Es wird ein Patchauftrag mit den geänderten Feldern angelegt. Der Trunk selbst ändert sich erst, wenn der Auftrag bestätigt wird.') }}</p>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Name') }}</label><input v-model="form.name" :class="inp" :placeholder="$t('z. B. Telekom CompanyFlex Werk A')" /></div>
        <div v-if="!asOrder"><label :class="lbl">{{ $t('Status') }}</label><select v-model="form.status" :class="inp"><option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ $t(s.label) }}</option></select></div>
        <div><label :class="lbl">{{ $t('Standort') }}</label><select v-model="form.site_id" :class="inp" :disabled="asOrder"><option :value="null" disabled>{{ $t('wählen …') }}</option><option v-for="s in writeSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
        <div><label :class="lbl">{{ $t('Anbindung') }}</label><select v-model="form.mode" :class="inp"><option v-for="m in meta.modes" :key="m.value" :value="m.value">{{ $t(m.label) }}</option></select></div>
        <div><label :class="lbl">{{ $t('SBC (Ankunft des Trunks)') }}</label><select v-model="form.sbc_device_id" :class="inp"><option :value="null">–</option><option v-for="d in sbcs" :key="d.id" :value="d.id">{{ d.hostname }} ({{ typeLabel(d.type) }})</option></select></div>
        <div><label :class="lbl">{{ $t('TK-Anlage') }}</label><select v-model="form.pbx_device_id" :class="inp"><option :value="null">–</option><option v-for="d in pbxs" :key="d.id" :value="d.id">{{ d.hostname }}</option></select></div>
        <div><label :class="lbl">{{ $t('WAN-Leitung') }}</label><select v-model="form.wan_link_id" :class="inp"><option :value="null">–</option><option v-for="w in wans" :key="w.id" :value="w.id">{{ w.name }} ({{ $t(w.status_label) }})</option></select></div>
        <div><label :class="lbl">{{ $t('Provider') }}</label><input v-model="form.provider" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Trunk-Kennung beim Provider') }}</label><input v-model="form.trunk_ident" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Registrar / Proxy') }}</label><input v-model="form.registrar" :class="inp" :placeholder="$t('z. B. reg.sip-trunk.telekom.de')" /></div>
        <div><label :class="lbl">{{ $t('Kanäle (gleichzeitige Gespräche)') }}</label><input v-model.number="form.channels" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Vertragsnummer') }}</label><input v-model="form.contract_number" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Kosten pro Monat') }}</label><input v-model.number="form.monthly_cost" type="number" min="0" step="any" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Vertragsbeginn') }}</label><input v-model="form.contract_start" type="date" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Vertragsende') }}</label><input v-model="form.contract_end" type="date" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Kündigungsfrist (Tage)') }}</label><input v-model.number="form.notice_days" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Ansprechpartner / Störungsnummer') }}</label><input v-model="form.contact" :class="inp" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Rufnummern (je Zeile ein Block)') }}</label><textarea v-model="form.numbers" rows="3" :class="inp" class="font-mono text-xs" :placeholder="$t('z. B. +49 6181 1234-0…99')"></textarea></div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="form.note" :class="inp" /></div>
      <template #footer>
        <button :class="btnGhost" @click="form = null">{{ $t('Abbrechen') }}</button>
        <button :class="btnPrimary" :disabled="busy || !form.name || !form.site_id" @click="submit">{{ asOrder ? $t('Änderungsauftrag anlegen') : $t('Speichern') }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import SidePanel from '../components/SidePanel.vue'
import NumberPlan from '../components/NumberPlan.vue'
import { api, errText, canWriteMaster, getToken, isGlobal, scopesOf, siteAdminIds } from '../api.js'
import { inp, lbl, card, btnPrimary, btnGhost, btnDanger, btnLink, th, td, typeLabel } from '../ui.js'

const route = useRoute(), router = useRouter()
const TABS = [['trunks', 'SIP-Trunks'], ['numbers', 'Rufnummernplan']]
const tab = ref(route.query.tab === 'numbers' ? 'numbers' : 'trunks')
function setTab(k) { tab.value = k; sel.value = null; router.replace({ query: k === 'numbers' ? { tab: k } : {} }) }
watch(() => route.query.tab, v => { tab.value = v === 'numbers' ? 'numbers' : 'trunks' })
const canWrite = canWriteMaster()
const trunks = ref([]), sites = ref([]), meta = ref({ statuses: [], modes: [], sbc_types: [], pbx_types: [] }), sel = ref(null)
const q = ref(''), fStatus = ref(''), fSite = ref(''), expiring = ref(false)
const error = ref(''), note = ref(''), busy = ref(false)
const form = ref(null), formError = ref(''), asOrder = ref(false), editId = ref(null), original = ref(null)
const sbcs = ref([]), pbxs = ref([]), wans = ref([])
const WIDE = ['Rufnummern', 'Kontakt', 'Notiz']
const csvUrl = '/api/sip-trunks/export.csv'
const ACTIONS = { trunk_activate: t('in Betrieb nehmen'), trunk_change: t('ändern'), trunk_terminate: t('kündigen') }
const FIELDS = ['name', 'mode', 'provider', 'trunk_ident', 'registrar', 'channels', 'numbers', 'sbc_device_id', 'pbx_device_id', 'wan_link_id',
  'contract_number', 'contract_start', 'contract_end', 'notice_days', 'monthly_cost', 'contact', 'note']

const writeSites = computed(() => isGlobal() ? sites.value : sites.value.filter(s => siteAdminIds().includes(s.id)))
const canPlan = l => isGlobal() || scopesOf().some(x => x.site_id === l.site_id && ['planer', 'admin'].includes(x.role))
const formTitle = computed(() => asOrder.value ? `${original.value?.name}: ${t('Änderung per Auftrag')}` : editId.value ? t('SIP-Trunk bearbeiten') : t('Neuer SIP-Trunk'))
const statusClass = s => ({ planned: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300', ordered: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', suspended: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  terminated: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' }[s] || '')
const details = computed(() => !sel.value ? [] : [
  ['Provider', sel.value.provider], ['Trunk-Kennung', sel.value.trunk_ident], ['Registrar / Proxy', sel.value.registrar], ['Kanäle', sel.value.channels ?? ''],
  ['Rufnummern', sel.value.numbers],
  ['Vertragsnummer', sel.value.contract_number], ['Vertragsbeginn', sel.value.contract_start], ['Vertragsende', sel.value.contract_end],
  ['Kündigungsfrist', sel.value.notice_days != null ? t('{n} Tage', { n: sel.value.notice_days }) : ''], ['Kosten / Monat', sel.value.monthly_cost != null ? sel.value.monthly_cost.toFixed(2) : ''],
  ['Kontakt', sel.value.contact], ['Notiz', sel.value.note]])

watch(() => form.value?.site_id, refreshChoices)
let timer
const loadSoon = () => { clearTimeout(timer); timer = setTimeout(load, 250) }
async function load() {
  error.value = ''
  try {
    trunks.value = await api.sipTrunks({ q: q.value || undefined, status: fStatus.value || undefined, site_id: fSite.value || undefined, expiring_days: expiring.value ? 90 : undefined })
    if (sel.value) sel.value = trunks.value.find(l => l.id === sel.value.id) ? await api.sipTrunk(sel.value.id) : null
  } catch (e) { error.value = errText(e) }
}
async function select(l) { try { sel.value = await api.sipTrunk(l.id) } catch (e) { error.value = errText(e) } }
async function downloadCsv() {
  const r = await fetch(csvUrl, { headers: { 'X-Auth-Token': getToken() } })
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'sip-trunks.csv'; a.click(); URL.revokeObjectURL(a.href)
}

async function refreshChoices() {
  const sid = form.value?.site_id
  if (!sid) { sbcs.value = pbxs.value = wans.value = []; return }
  try {
    const devs = (await api.devices({ site_id: sid, limit: 500 })).items || []
    sbcs.value = devs.filter(d => meta.value.sbc_types.includes(d.type)).sort((a, b) => (a.type === 'sbc' ? 0 : 1) - (b.type === 'sbc' ? 0 : 1))
    pbxs.value = devs.filter(d => meta.value.pbx_types.includes(d.type))
    wans.value = (await api.wanLinks({ site_id: sid })).filter(w => w.status !== 'terminated' || w.id === form.value?.wan_link_id)
  } catch { sbcs.value = pbxs.value = wans.value = [] }
}

function openForm(l = null, order = false) {
  formError.value = ''; asOrder.value = order; editId.value = l?.id || null; original.value = l
  form.value = l ? { ...l } : { name: '', status: 'planned', mode: 'registration', site_id: writeSites.value[0]?.id ?? null, sbc_device_id: null, pbx_device_id: null, wan_link_id: null,
    provider: '', trunk_ident: '', registrar: '', channels: null, numbers: '', contract_number: '', contract_start: null, contract_end: null, notice_days: null, monthly_cost: null, contact: '', note: '' }
  refreshChoices()
}

async function submit() {
  busy.value = true; formError.value = ''
  try {
    if (asOrder.value) {
      const patch = {}
      for (const k of FIELDS) { const a = form.value[k] ?? null, b = original.value[k] ?? null; if ((a === '' ? null : a) !== (b === '' ? null : b)) patch[k] = form.value[k] === '' && !['numbers', 'note', 'contact', 'provider', 'trunk_ident', 'registrar', 'contract_number'].includes(k) ? null : form.value[k] }
      if (!Object.keys(patch).length) { formError.value = t('Es wurde nichts geändert.'); return }
      await makeOrder(original.value, 'trunk_change', patch)
    } else {
      const saved = editId.value ? await api.updateSipTrunk(editId.value, form.value) : await api.createSipTrunk(form.value)
      form.value = null; note.value = t('Gespeichert'); await load(); await select(saved)
    }
  } catch (e) { formError.value = errText(e) } finally { busy.value = false }
}

async function makeOrder(l, action, patch) {
  const loc = (await api.locations(l.site_id))[0]
  const wo = await api.createWorkorder({ title: `SIP-Trunk ${ACTIONS[action]}: ${l.name}`, location_id: loc?.id ?? null })
  await api.addWorkitem(wo.id, { action, sip_trunk_id: l.id, trunk_patch: patch || {} })
  router.push(`/workorders/${wo.id}`)
}
async function orderFor(l, action) {
  if (!confirm(t('Patchauftrag „{n}“ anlegen?', { n: `SIP-Trunk ${ACTIONS[action]}: ${l.name}` }))) return
  busy.value = true; error.value = ''
  try { await makeOrder(l, action) } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
async function remove(l) {
  if (!confirm(t('SIP-Trunk „{n}“ löschen?', { n: l.name }))) return
  try { await api.deleteSipTrunk(l.id); sel.value = null; await load() } catch (e) { error.value = errText(e) }
}

onMounted(async () => {
  try { [sites.value, meta.value] = await Promise.all([api.sites(), api.sipTrunkMeta()]) } catch (e) { error.value = errText(e) }
  await load()
  const id = Number(route.query.id)
  if (id) { try { sel.value = await api.sipTrunk(id) } catch { /* nicht sichtbar */ } }
})
</script>
