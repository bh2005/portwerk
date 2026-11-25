<template>
  <div class="max-w-6xl space-y-4">
    <div class="flex items-start justify-between gap-3">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100 whitespace-nowrap">{{ $t('Geräte') + ' ' }}<span class="text-sm font-normal text-slate-400">({{ total }})</span></h1>
      <div v-if="canWrite || canOrder" class="flex flex-wrap justify-end gap-2 [&>button]:whitespace-nowrap">
        <button @click="wizard = 'switch'" :class="btnPrimary">{{ $t('Assistent: Gerät platzieren') }}</button>
        <button @click="wizard = 'patchpanel'" :class="btnPrimary">{{ $t('Assistent: Patchfeld') }}</button>
        <button @click="wizard = 'vertical'" :class="btnGhost">{{ $t('Hochkant (PDU …)') }}</button>
        <button @click="cableWizard = true" :class="btnPrimary">{{ $t('Assistent: Kabel einbauen') }}</button>
        <button @click="bulkWizard = true" :class="btnPrimary">{{ $t('Assistent: Massenverkabelung') }}</button>
        <button @click="wizard = 'placeholder'" :class="btnGhost">{{ $t('Platzhalter einplanen') }}</button>
        <button v-if="opEnabled && (canOrder || canWrite)" @click="opDevices = true" :class="btnGhost" :title="$t('Geräte aus einem Geräte-Rollout in OpenPlan als „geplant“ übernehmen')">{{ $t('Aus OpenPlan …') }}</button>
        <button v-if="canWrite" @click="openNew" :class="btnGhost">{{ $t('+ Gerät (einfach)') }}</button>
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <input v-model="f.q" :placeholder="$t('Suchen (Hostname, Modell, Seriennummer, IP …)')" :class="inp" class="!w-72" @input="reloadSoon" />
      <select v-model="f.type" :class="inp" class="!w-40" @change="reload"><option value="">{{ $t('Alle Typen') }}</option><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ $t(l) }}</option></select>
      <select v-model="f.status" :class="inp" class="!w-36" @change="reload"><option value="">{{ $t('Alle Status') }}</option><option v-for="[k, l] in DEVICE_STATUS" :key="k" :value="k">{{ $t(l) }}</option></select>
      <select v-model="f.source" :class="inp" class="!w-36" @change="reload"><option value="">{{ $t('Alle Quellen') }}</option><option v-for="[k, l] in SOURCES" :key="k" :value="k">{{ $t(l) }}</option></select>
      <select v-model="f.site_id" :class="inp" class="!w-40" @change="reload"><option value="">{{ $t('Alle Standorte') }}</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }}</option></select>
    </div>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40">
          <th :class="th">{{ $t('Hostname') }}</th><th :class="th">{{ $t('Typ') }}</th><th :class="th">{{ $t('Modell') }}</th><th :class="th">{{ $t('Mgmt-IP') }}</th>
          <th :class="th">{{ $t('Location') }}</th><th :class="th">{{ $t('Ports') }}</th><th :class="th">{{ $t('Status') }}</th><th :class="th">{{ $t('Quelle') }}</th></tr></thead>
        <tbody>
          <tr v-if="!items.length"><td colspan="8" class="px-3 py-6 text-center text-slate-400">{{ $t('Keine Geräte gefunden.') }}</td></tr>
          <tr v-for="d in items" :key="d.id" class="border-t border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30">
            <td :class="td"><router-link :to="`/devices/${d.id}`" class="text-ks-600 dark:text-ks-400 hover:underline font-medium">{{ d.hostname }}</router-link>
              <div v-if="d.former_hostname" class="text-[11px] text-slate-400">{{ $t('ehemals {name}', { name: d.former_hostname }) }}</div>
              <div v-else-if="d.planned_hostname" class="text-[11px] text-amber-600 dark:text-amber-400">{{ $t('wird nach dem Rückbau zu „{name}“', { name: d.planned_hostname }) }}</div></td>
            <td :class="td">{{ typeLabel(d.type) }}</td>
            <td :class="td" class="text-slate-500">{{ [d.vendor, d.model].filter(Boolean).join(' ') || '–' }}</td>
            <td :class="td" class="font-mono text-xs">{{ d.mgmt_ip || '–' }}</td>
            <td :class="td" class="text-slate-500">{{ d.location_path || '–' }}</td>
            <td :class="td">{{ d.port_count }}</td>
            <td :class="td"><span class="text-[11px] px-2 py-0.5 rounded-full" :class="statusClass(d.status)">{{ statusLabel(d.status) }}</span></td>
            <td :class="td" class="text-slate-500">{{ sourceLabel(d.source) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="total > limit" class="flex items-center justify-between text-sm text-slate-500">
      <span>{{ $t('{a}–{b} von {n}', { a: offset + 1, b: Math.min(offset + limit, total), n: total }) }}</span>
      <div class="flex gap-2">
        <button :class="btnGhost" :disabled="offset === 0" @click="page(-1)">{{ $t('Zurück') }}</button>
        <button :class="btnGhost" :disabled="offset + limit >= total" @click="page(1)">{{ $t('Weiter') }}</button>
      </div>
    </div>

    <ModalDialog v-if="form" :title="$t('Neues Gerät')" :error="formError" @close="form = null">
      <div><label :class="lbl">{{ $t('Hostname') }}</label><input v-model="form.hostname" :class="inp" /></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Typ') }}</label><select v-model="form.type" :class="inp"><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ $t(l) }}</option></select></div>
        <div><label :class="lbl">{{ $t('Status') }}</label><select v-model="form.status" :class="inp"><option v-for="[k, l] in DEVICE_STATUS" :key="k" :value="k">{{ $t(l) }}</option></select></div>
        <div><label :class="lbl">{{ $t('Hersteller') }}</label><input v-model="form.vendor" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Modell') }}</label><input v-model="form.model" :class="inp" /></div>
      </div>
      <template #footer>
        <button @click="form = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="create" :class="btnPrimary" :disabled="!form.hostname">{{ $t('Anlegen') }}</button>
      </template>
    </ModalDialog>
    <CableWizard v-if="cableWizard" @close="cableWizard = false" @done="cableDone" />
    <BulkCableWizard v-if="bulkWizard" @close="bulkWizard = false" @done="bulkDone" />
    <OpenPlanDevicesDialog v-if="opDevices" @close="opDevices = false; reload()" @done="reload" />
    <DeviceWizard v-if="wizard" :kind="wizard" :title="TITLES[wizard]" @close="wizard = null" @done="wizardDone" />
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import { api, errText, canWriteMaster, hasRole } from '../api.js'
import DeviceWizard from '../components/DeviceWizard.vue'
import CableWizard from '../components/CableWizard.vue'
import BulkCableWizard from '../components/BulkCableWizard.vue'
import OpenPlanDevicesDialog from '../components/OpenPlanDevicesDialog.vue'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, DEVICE_TYPES, DEVICE_STATUS, SOURCES, typeLabel, statusLabel, sourceLabel, statusClass } from '../ui.js'

const router = useRouter(), route = useRoute()
const canWrite = canWriteMaster()
const canOrder = hasRole('planer')
const wizard = ref(null), cableWizard = ref(false), bulkWizard = ref(false), opDevices = ref(false), opEnabled = ref(false)
function bulkDone(r) { bulkWizard.value = false; if (r.workorder) router.push(`/workorders/${r.workorder.id}`); else reload() }
async function cableDone() { cableWizard.value = false; reload() }
const TITLES = { switch: t('Assistent: Gerät platzieren'), patchpanel: t('Assistent: Patchfeld platzieren'), placeholder: t('Assistent: Platzhalter einplanen'), vertical: t('Assistent: Hochkant-Gerät (PDU …) platzieren') }
async function wizardDone() { wizard.value = null; reload() }
const limit = 50
const items = ref([]), total = ref(0), offset = ref(0), sites = ref([]), error = ref('')
const f = reactive({ q: '', type: '', status: '', source: '', site_id: '', location_id: route.query.location_id || '' })
const form = ref(null), formError = ref('')

async function load() {
  try {
    const params = { limit, offset: offset.value }
    for (const [k, v] of Object.entries(f)) if (v) params[k] = v
    const r = await api.devices(params)
    items.value = r.items; total.value = r.total; error.value = ''
  } catch (e) { error.value = errText(e) }
}
function reload() { offset.value = 0; load() }
let timer
function reloadSoon() { clearTimeout(timer); timer = setTimeout(reload, 300) }
function page(dir) { offset.value = Math.max(0, offset.value + dir * limit); load() }

function openNew() { formError.value = ''; form.value = { hostname: '', type: 'switch', status: 'active', vendor: '', model: '' } }
async function create() {
  try { const d = await api.createDevice(form.value); form.value = null; router.push(`/devices/${d.id}`) }
  catch (e) { formError.value = errText(e) }
}

onMounted(async () => {
  try { sites.value = await api.sites() } catch {} ; load()
  api.openplanStatus().then(s => { opEnabled.value = s.enabled }).catch(() => {})
})
</script>
