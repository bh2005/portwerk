<template>
  <div class="max-w-6xl space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Katalog') }}</h1>
      <button v-if="canWrite && tab === 'models'" @click="openModel()" :class="btnPrimary">{{ $t('+ Modell') }}</button>
      <button v-if="canWrite && tab === 'cables'" @click="openCable()" :class="btnPrimary">{{ $t('+ Kabelart') }}</button>
    </div>
    <div class="flex gap-1 border-b border-slate-200 dark:border-slate-700">
      <button v-for="[k, l] in [['models', 'Gerätemodelle'], ['cables', 'Kabelarten']]" :key="k" @click="tab = k"
        class="px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors"
        :class="tab === k ? 'border-ks-600 text-ks-700 dark:text-ks-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'">{{ $t(l) }}</button>
    </div>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <!-- Gerätemodelle -->
    <div v-if="tab === 'models'" class="space-y-3">
      <div class="flex gap-2 flex-wrap">
        <input v-model="q" :class="inp" class="!w-64" :placeholder="$t('Suche: Hersteller, Modell, Artikelnr.')" @input="loadModels" />
        <select v-model="typeFilter" :class="inp" class="!w-48" @change="loadModels">
          <option value="">{{ $t('Alle Typen') }}</option><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ $t(l) }}</option></select>
        <label class="flex items-center gap-2 text-sm text-slate-500"><input type="checkbox" v-model="withInactive" @change="loadModels" />{{ ' ' + $t('auch deaktivierte') }}</label>
      </div>
      <div :class="card" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="border-b border-slate-100 dark:border-slate-700">
            <th :class="th">{{ $t('Hersteller') }}</th><th :class="th">{{ $t('Modell') }}</th><th :class="th">{{ $t('Typ') }}</th><th :class="th">{{ $t('HE') }}</th>
            <th :class="th">{{ $t('Ports') }}</th><th :class="th">{{ $t('Artikelnr.') }}</th><th :class="th">{{ $t('Geräte') }}</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-if="!models.length"><td colspan="8" :class="td" class="text-slate-400">{{ $t('Noch keine Modelle. Mit „+ Modell“ ein Gerät oder Patchfeld als Vorlage anlegen.') }}</td></tr>
            <tr v-for="m in models" :key="m.id" class="border-b border-slate-50 dark:border-slate-700/50" :class="m.active ? '' : 'opacity-50'">
              <td :class="td">{{ m.vendor || '–' }}</td>
              <td :class="td" class="font-medium text-slate-800 dark:text-slate-100">{{ m.model }}<span v-if="!m.active" class="ml-2 text-[10px] text-slate-400">{{ $t('(deaktiviert)') }}</span></td>
              <td :class="td">{{ typeLabel(m.type) }}</td><td :class="td">{{ m.height_u }}</td>
              <td :class="td" class="text-xs">{{ portSummary(m) }}</td>
              <td :class="td" class="font-mono text-xs">{{ m.article_no || '–' }}</td>
              <td :class="td">{{ m.device_count }}</td>
              <td :class="td" class="text-right whitespace-nowrap">
                <template v-if="canWrite">
                  <button :class="btnLink" @click="openModel(m)">{{ $t('Bearbeiten') }}</button>
                  <button :class="btnDanger" class="ml-3" @click="removeModel(m)">{{ $t('Löschen') }}</button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Kabelarten -->
    <div v-if="tab === 'cables'" :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="border-b border-slate-100 dark:border-slate-700">
          <th :class="th">{{ $t('Name') }}</th><th :class="th">{{ $t('Kategorie') }}</th><th :class="th">{{ $t('Zählfeld') }}</th><th :class="th">{{ $t('Bemerkung') }}</th>
          <th :class="th">{{ $t('Verwendet') }}</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="t in cables" :key="t.id" class="border-b border-slate-50 dark:border-slate-700/50" :class="t.active ? '' : 'opacity-50'">
            <td :class="td" class="font-medium text-slate-800 dark:text-slate-100">{{ t.name }}
              <span v-if="t.builtin" class="ml-1 text-[10px] text-slate-400">{{ $t('mitgeliefert') }}</span>
              <span v-if="!t.active" class="ml-1 text-[10px] text-slate-400">{{ $t('(deaktiviert)') }}</span></td>
            <td :class="td">{{ categoryLabel(t.category) }}</td>
            <td :class="td">{{ t.count_label || '–' }}</td>
            <td :class="td" class="text-xs text-slate-500">{{ t.note }}</td>
            <td :class="td">{{ t.in_use }}</td>
            <td :class="td" class="text-right whitespace-nowrap">
              <template v-if="canWrite">
                <button :class="btnLink" @click="openCable(t)">{{ $t('Bearbeiten') }}</button>
                <button v-if="!t.builtin" :class="btnDanger" class="ml-3" @click="removeCable(t)">{{ $t('Löschen') }}</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Dialog Modell -->
    <ModalDialog v-if="mForm" wide :title="mForm.id ? $t('Modell bearbeiten') : $t('Neues Modell')" :error="formError" @close="mForm = null">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Hersteller') }}</label><input v-model="mForm.vendor" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Modell') }}</label><input v-model="mForm.model" :class="inp" placeholder="z. B. C9300-48P" /></div>
        <div><label :class="lbl">{{ $t('Typ') }}</label>
          <select v-model="mForm.type" :class="inp"><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ $t(l) }}</option></select></div>
        <div><label :class="lbl">{{ $t('Höhe (HE)') }}</label><input v-model.number="mForm.height_u" type="number" min="1" max="50" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Artikelnummer') }}</label><input v-model="mForm.article_no" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Einbau') }}</label>
          <select v-model="mForm.orientation" :class="inp" @change="if (mForm.orientation === 'vertical') { if (mForm.mount_side === 'both') mForm.mount_side = 'rear'; if (!mForm.side_slot) mForm.side_slot = 'right' } else mForm.side_slot = ''">
            <option value="horizontal">{{ $t('19 Zoll (HE-Platz)') }}</option><option value="vertical">{{ $t('Hochkant im Seitenkanal (0 HE)') }}</option><option value="din_rail">{{ $t('Hutschiene / Montageplatte (ohne HE)') }}</option></select></div>
        <div><label :class="lbl">{{ $t('Einbauseite') }}</label>
          <select v-model="mForm.mount_side" :class="inp"><option value="front">{{ $t('Vorderseite') }}</option><option value="rear">{{ $t('Rückseite') }}</option><option v-if="mForm.orientation === 'horizontal'" value="both">{{ $t('beide Seiten (durchgehend)') }}</option></select></div>
        <div v-if="mForm.orientation === 'vertical'"><label :class="lbl">{{ $t('Seitenkanal (Vorgabe)') }}</label>
          <select v-model="mForm.side_slot" :class="inp"><option value="left">{{ $t('links') }}</option><option value="right">{{ $t('rechts') }}</option></select></div>
        <div class="flex items-end"><label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="mForm.active" />{{ ' ' + $t('aktiv (in Assistenten wählbar)') }}</label></div>
      </div>
      <div><label :class="lbl">{{ $t('Beschreibung') }}</label><input v-model="mForm.description" :class="inp" /></div>
      <div>
        <div class="flex items-center justify-between mb-1">
          <label :class="lbl" class="!mb-0">{{ $t('Port-Vorlage') }}</label>
          <button :class="btnLink" @click="addGroup">{{ $t('+ Portgruppe') }}</button>
        </div>
        <p v-if="!mForm.ports.length" class="text-xs text-slate-400">{{ $t('Keine Ports – z. B. für USV oder Zubehör ohne Anschlüsse.') }}</p>
        <div v-for="(g, i) in mForm.ports" :key="i" class="grid grid-cols-12 gap-2 items-end mb-2">
          <div class="col-span-3"><label :class="lbl">{{ $t('Präfix') }}</label><input v-model="g.prefix" :class="inp" :placeholder="$t('Gi1/0/')" /></div>
          <div class="col-span-1"><label :class="lbl">{{ $t('Start') }}</label><input v-model.number="g.start" type="number" min="0" :class="inp" /></div>
          <div class="col-span-2"><label :class="lbl">{{ $t('Anzahl') }}</label><input v-model.number="g.count" type="number" min="1" max="512" :class="inp" /></div>
          <div class="col-span-2"><label :class="lbl">{{ $t('Medium') }}</label><select v-model="g.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
          <div class="col-span-2"><label :class="lbl">{{ $t('Mbit/s') }}</label><input v-model.number="g.speed_mbps" type="number" min="0" :class="inp" /></div>
          <div class="col-span-1 pb-2"><label class="text-[11px] text-slate-500 flex items-center gap-1" :title="$t('Vorder- und Rückseite (Patchfeld)')"><input type="checkbox" v-model="g.dual" />{{ ' ' + $t('dual') }}</label></div>
          <div class="col-span-1 pb-2 text-right"><button :class="btnDanger" @click="mForm.ports.splice(i, 1)">✕</button></div>
        </div>
        <p v-if="mForm.ports.length" class="text-xs text-slate-400">{{ $t('Ergibt {n} Ports. „dual“ legt je Port eine Rückseite (', { n: portTotal(mForm) }) }}<code>-back</code>{{ $t(') an und verknüpft beide.') }}</p>
      </div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="mForm.note" :class="inp" /></div>
      <template #footer>
        <button @click="mForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveModel" :class="btnPrimary" :disabled="!mForm.model">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>

    <!-- Dialog Kabelart -->
    <ModalDialog v-if="cForm" :title="cForm.id ? $t('Kabelart bearbeiten') : $t('Neue Kabelart')" :error="formError" @close="cForm = null">
      <div><label :class="lbl">{{ $t('Name') }}</label>
        <input v-model="cForm.name" :class="inp" :disabled="!!cForm.id" :placeholder="$t('z. B. Telefon-Cu 20x2')" />
        <p v-if="cForm.id" class="text-[11px] text-slate-400 mt-1">{{ $t('Der Name ist unveränderlich, weil bestehende Kabel darauf verweisen. Für einen neuen Namen eine neue Kabelart anlegen und diese deaktivieren.') }}</p></div>
      <div><label :class="lbl">{{ $t('Kategorie') }}</label>
        <select v-model="cForm.category" :class="inp"><option v-for="[k, l] in CABLE_CATEGORIES" :key="k" :value="k">{{ $t(l) }}</option></select></div>
      <div><label :class="lbl">{{ $t('Zählfeld (leer = keins)') }}</label>
        <input v-model="cForm.count_label" :class="inp" list="count-labels" :placeholder="$t('Fasern, Adern oder Paare')" />
        <datalist id="count-labels"><option>{{ $t('Fasern') }}</option><option>{{ $t('Adern') }}</option><option>{{ $t('Paare') }}</option></datalist></div>
      <div><label :class="lbl">{{ $t('Bemerkung') }}</label><input v-model="cForm.note" :class="inp" /></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Sortierung') }}</label><input v-model.number="cForm.sort" type="number" min="0" :class="inp" /></div>
        <div class="flex items-end"><label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="cForm.active" />{{ ' ' + $t('aktiv') }}</label></div>
      </div>
      <template #footer>
        <button @click="cForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveCable" :class="btnPrimary" :disabled="!cForm.name">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { t, t as tr } from '../i18n.js'
import { ref, watch, onMounted } from 'vue'
import ModalDialog from '../components/ModalDialog.vue'
import { api, errText, isAdmin } from '../api.js'
import { loadCableTypes } from '../catalog.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnDanger, btnLink, DEVICE_TYPES, PORT_MEDIA, CABLE_CATEGORIES, typeLabel } from '../ui.js'
import { helpContext } from '../content/helpContext.js'

const canWrite = isAdmin()
const tab = ref('models')
const error = ref(''), formError = ref('')
const models = ref([]), cables = ref([])
const q = ref(''), typeFilter = ref(''), withInactive = ref(false)
const mForm = ref(null), cForm = ref(null)

const categoryLabel = k => (CABLE_CATEGORIES.find(c => c[0] === k) || [k, k])[1]
const portTotal = m => m.ports.reduce((n, g) => n + (Number(g.count) || 0) * (g.dual ? 2 : 1), 0)
const portSummary = m => !m.ports.length ? '–' : m.ports.map(g => `${g.count}× ${g.medium}${g.dual ? ' dual' : ''}`).join(', ')

async function loadModels() {
  try { models.value = await api.deviceModels({ q: q.value, type: typeFilter.value, all: withInactive.value || undefined }) }
  catch (e) { error.value = errText(e) }
}
async function loadCables() {
  try { cables.value = await api.cableTypes(true) } catch (e) { error.value = errText(e) }
}

function openModel(m) {
  formError.value = ''
  mForm.value = m ? JSON.parse(JSON.stringify(m))
    : { vendor: '', model: '', type: 'switch', height_u: 1, article_no: '', description: '', ports: [], note: '', active: true, orientation: 'horizontal', mount_side: 'both', side_slot: '' }
}
function addGroup() { mForm.value.ports.push({ prefix: 'Port', start: 1, count: 8, medium: 'RJ45', speed_mbps: null, dual: false, back_suffix: '-back' }) }
async function saveModel() {
  try {
    const f = mForm.value
    f.id ? await api.updateModel(f.id, f) : await api.createModel(f)
    mForm.value = null; await loadModels()
  } catch (e) { formError.value = errText(e) }
}
async function removeModel(m) {
  if (!confirm(t('Modell „{n}“ löschen?', { n: `${m.vendor} ${m.model}` }))) return
  try { await api.deleteModel(m.id); await loadModels() } catch (e) { error.value = errText(e) }
}

function openCable(t) {
  formError.value = ''
  cForm.value = t ? { ...t } : { name: '', category: 'other', count_label: '', note: '', active: true, sort: 100 }
}
async function saveCable() {
  try {
    const f = cForm.value
    f.id ? await api.updateCableType(f.id, f) : await api.createCableType(f)
    cForm.value = null; await loadCables(); loadCableTypes(true)
  } catch (e) { formError.value = errText(e) }
}
async function removeCable(t) {
  if (!confirm(tr('Kabelart „{n}“ löschen?', { n: t.name }))) return
  try { await api.deleteCableType(t.id); await loadCables(); loadCableTypes(true) } catch (e) { error.value = errText(e) }
}

watch(tab, t => { helpContext.value = t; error.value = '' })
onMounted(() => { loadModels(); loadCables() })
</script>
