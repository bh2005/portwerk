<template>
  <div class="max-w-6xl space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Standorte') }}</h1>
      <div v-if="canWrite" class="flex gap-2">
        <button @click="wizard = { siteId: null }" :class="btnPrimary">{{ $t('Assistent: Neuer Standort') }}</button>
        <button @click="openSite()" :class="btnGhost">{{ $t('+ Standort (einfach)') }}</button>
      </div>
    </div>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <div class="grid md:grid-cols-3 gap-4">
      <div :class="card" class="p-2 md:col-span-1">
        <div v-if="sites.length > 5" class="p-1 pb-2"><input v-model="siteQ" :class="inp" class="!py-1" :placeholder="$t('Standort suchen (Code, Name, Adresse) …')" />
          <p v-if="siteQ" class="text-[11px] text-slate-400 mt-1">{{ $t('{a} von {b}', { a: shownSites.length, b: sites.length }) }}</p></div>
        <p v-if="!sites.length" class="text-sm text-slate-400 p-3">{{ $t('Noch kein Standort angelegt.') }}</p>
        <p v-else-if="!shownSites.length" class="text-sm text-slate-400 p-3">{{ $t('Kein Standort für diese Suche.') }}</p>
        <button v-for="s in shownSites" :key="s.id" @click="select(s)"
          class="w-full text-left px-3 py-2 rounded-lg transition-colors"
          :class="sel?.id === s.id ? 'bg-ks-50 dark:bg-ks-900/30' : 'hover:bg-slate-50 dark:hover:bg-slate-700/50'">
          <div class="text-sm font-medium text-slate-800 dark:text-slate-100">{{ s.code }} <span class="font-normal text-slate-400">· {{ s.name }}</span></div>
          <div class="text-[11px] text-slate-400">{{ $t('{a} Locations · {b} Geräte', { a: s.locations, b: s.devices }) }}</div>
        </button>
      </div>

      <div :class="card" class="p-4 md:col-span-2" v-if="sel">
        <div class="flex items-start justify-between mb-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ sel.code }} · {{ sel.name }}</h2>
            <p v-if="sel.address" class="text-xs text-slate-400">{{ sel.address }}</p>
            <p v-if="sel.note" class="text-xs text-slate-400">{{ sel.note }}</p>
          </div>
          <div v-if="canWrite" class="flex gap-3 items-center">
            <button :class="btnLink" @click="openSite(sel)">{{ $t('Bearbeiten') }}</button>
            <button :class="btnDanger" @click="removeSite">{{ $t('Löschen') }}</button>
            <button :class="btnGhost" @click="wizard = { siteId: sel.id, siteLabel: sel.code }">{{ $t('Struktur-Assistent') }}</button>
            <button :class="btnPrimary" @click="openLoc()">{{ $t('+ Location') }}</button>
          </div>
        </div>

        <p v-if="!tree.length" class="text-sm text-slate-400">{{ $t('Noch keine Gebäude, Räume oder Racks.') }}</p>
        <div v-if="tree.length > 6" class="flex items-center gap-2 flex-wrap mb-2">
          <input v-model="locQ" :class="inp" class="!py-1 !w-64" :placeholder="$t('Locations filtern (Name, Kennung) …')" />
          <select v-model="locKind" :class="inp" class="!py-1 !w-44"><option value="">{{ $t('alle Arten') }}</option><option v-for="k in locKinds" :key="k" :value="k">{{ kindLabel(k) }}</option></select>
          <button v-if="locQ || locKind" type="button" :class="btnLink" @click="locQ = ''; locKind = ''">{{ $t('Filter zurücksetzen') }}</button>
          <span v-if="locQ || locKind" class="text-xs text-slate-400">{{ $t('{a} von {b}', { a: treeShown.length, b: tree.length }) }}</span>
        </div>
        <p v-if="tree.length && !treeShown.length" class="text-sm text-slate-400">{{ $t('Keine Location für diesen Filter.') }}</p>
        <ul class="text-sm">
          <li v-for="n in treeShown" :key="n.id" class="flex items-center gap-2 py-1 border-b border-slate-50 dark:border-slate-700/50" :style="{ paddingLeft: n.depth * 18 + 'px' }">
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300">{{ kindLabel(n.kind) }}</span>
            <span class="text-slate-800 dark:text-slate-100">{{ n.name }}</span>
            <span v-if="n.ident" class="text-xs font-mono text-slate-500">{{ n.ident }}</span>
            <span v-if="n.rack_units" class="text-xs text-slate-400">{{ n.rack_units }} {{ $t('HE') }}</span>
            <router-link v-if="n.devices" :to="{ path: '/devices', query: { location_id: n.id } }" class="text-xs text-ks-600 dark:text-ks-400 hover:underline">{{ $t('{n} Geräte', { n: n.devices }) }}</router-link>
            <span v-if="canWrite" class="ml-auto flex gap-3">
              <button :class="btnLink" @click="openLoc(n)">{{ $t('Bearbeiten') }}</button>
              <button v-if="MOVABLE_KINDS.includes(n.kind)" :class="btnLink" :title="n.kind === 'vehicle' ? $t('Mobile Maschine an einen anderen Standort verlegen (samt Geräten)') : $t('An einen anderen Standort/Ort verlegen (samt Geräten)')" @click="openMove(n)">{{ $t('Verlegen') }}</button>
              <button v-if="!CONTAINER_KINDS.includes(n.kind)" :class="btnLink" @click="openLoc(null, n)">{{ $t('+ darunter') }}</button>
              <button :class="btnDanger" @click="removeLoc(n)">{{ $t('Löschen') }}</button>
            </span>
          </li>
        </ul>
      </div>
    </div>

    <SiteWizard v-if="wizard" :site-id="wizard.siteId" :site-label="wizard.siteLabel || ''" @close="wizard = null" @done="wizardDone" />

    <ModalDialog v-if="siteForm" :title="siteForm.id ? $t('Standort bearbeiten') : $t('Neuer Standort')" :error="formError" @close="siteForm = null">
      <div><label :class="lbl">{{ $t('Code') }}</label><input v-model="siteForm.code" :class="inp" :placeholder="$t('z. B. SITE-A')" /></div>
      <div><label :class="lbl">{{ $t('Name') }}</label><input v-model="siteForm.name" :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Adresse') }}</label><input v-model="siteForm.address" :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="siteForm.note" :class="inp" /></div>
      <template #footer>
        <button @click="siteForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveSite" :class="btnPrimary" :disabled="!siteForm.code || !siteForm.name">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="moveForm" :title="`${kindLabel(moveForm.node.kind)} „${moveForm.node.name}“ verlegen`" :error="formError" @close="moveForm = null">
      <p class="text-sm text-slate-500">{{ $t('Die Location wird samt Gehäusen und Geräten darunter an den neuen Ort gestellt (z. B. eine mobile Maschine in ein anderes Werk). Die Änderung steht im Audit-Log.') }}</p>
      <div><label :class="lbl">{{ $t('Standort') }}</label>
        <select v-model="moveForm.site_id" :class="inp" @change="loadMoveTargets"><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
      <div><label :class="lbl">{{ $t('Darunter (optional)') }}</label>
        <select v-model="moveForm.parent_id" :class="inp"><option :value="null">{{ $t('(direkt am Standort)') }}</option>
          <option v-for="n in moveForm.targets" :key="n.id" :value="n.id">{{ n.path }}</option></select></div>
      <template #footer>
        <button @click="moveForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveMove" :class="btnPrimary">{{ $t('Verlegen') }}</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="locForm" :title="locForm.id ? $t('Location bearbeiten') : $t('Neue Location')" :error="formError" @close="locForm = null">
      <div><label :class="lbl">{{ $t('Art') }}</label>
        <select v-model="locForm.kind" :class="inp"><option v-for="[k, l] in LOCATION_KINDS" :key="k" :value="k">{{ $t(l) }}</option></select></div>
      <div><label :class="lbl">{{ $t('Name') }}</label><input v-model="locForm.name" :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Übergeordnet') }}</label>
        <select v-model="locForm.parent_id" :class="inp"><option :value="null">{{ $t('(oberste Ebene)') }}</option>
          <option v-for="n in parentChoices" :key="n.id" :value="n.id">{{ '– '.repeat(n.depth) }}{{ n.name }}</option></select></div>
      <div v-if="CONTAINER_KINDS.includes(locForm.kind)"><label :class="lbl">{{ $t('Höheneinheiten (HE)') }}{{ locForm.kind === 'cabinet' ? ' – ' + $t('optional') : '' }}</label><input v-model.number="locForm.rack_units" type="number" min="1" max="100" :class="inp" :placeholder="locForm.kind === 'cabinet' ? $t('leer = keine HE-Teilung (Hutschiene/Montageplatte)') : ''" /></div>
      <div v-if="['machine', 'vehicle', 'cabinet', 'wallrack', 'rack'].includes(locForm.kind)"><label :class="lbl">{{ locForm.kind === 'vehicle' ? $t('Kennzeichen / Fahrzeugnummer') : locForm.kind === 'machine' ? $t('Anlagen-/Maschinennummer') : $t('Bezeichnung / Nummer') }}</label><input v-model="locForm.ident" :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="locForm.note" :class="inp" /></div>
      <template #footer>
        <button @click="locForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveLoc" :class="btnPrimary" :disabled="!locForm.name">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import SiteWizard from '../components/SiteWizard.vue'
import { api, errText, canWriteMaster } from '../api.js'
import { inp, lbl, card, btnPrimary, btnGhost, btnDanger, btnLink, LOCATION_KINDS, CONTAINER_KINDS, MOVABLE_KINDS, kindLabel } from '../ui.js'

const canWrite = canWriteMaster()
const sites = ref([]), sel = ref(null), locations = ref([])
const error = ref(''), formError = ref('')
const siteForm = ref(null), locForm = ref(null), wizard = ref(null), moveForm = ref(null)
async function openMove(n) {
  formError.value = ''
  moveForm.value = { node: n, site_id: sel.value.id, parent_id: null, targets: [] }
  await loadMoveTargets()
}
async function loadMoveTargets() {
  const f = moveForm.value
  f.parent_id = null
  try { f.targets = (await api.locations(f.site_id)).filter(l => !CONTAINER_KINDS.includes(l.kind) && l.id !== f.node.id && !(l.path || '').startsWith(f.node.path + ' / ')) } catch { f.targets = [] }
}
async function saveMove() {
  try {
    const f = moveForm.value
    const r = await api.moveLocation(f.node.id, { site_id: f.site_id, parent_id: f.parent_id })
    moveForm.value = null
    await load(f.site_id === sel.value.id ? sel.value.id : f.site_id)
    error.value = ''
  } catch (e) { formError.value = errText(e) }
}
async function wizardDone(siteId) { wizard.value = null; await load(siteId) }

// Locations als Baum mit Einrückungstiefe (Eltern vor Kindern)
const tree = computed(() => {
  const out = []
  const walk = (parent, depth) => locations.value.filter(l => (l.parent_id || null) === parent)
    .forEach(l => { out.push({ ...l, depth }); walk(l.id, depth + 1) })
  walk(null, 0)
  return out
})
// Filter: Treffer samt Oberbau (damit man sieht, wo sie liegen) und Unterbau
const siteQ = ref(''), locQ = ref(''), locKind = ref('')
const shownSites = computed(() => {
  const q = siteQ.value.trim().toLowerCase()
  return q ? sites.value.filter(s => `${s.code} ${s.name} ${s.address || ''}`.toLowerCase().includes(q)) : sites.value
})
const locKinds = computed(() => [...new Set(tree.value.map(n => n.kind))])
const treeShown = computed(() => {
  const q = locQ.value.trim().toLowerCase()
  if (!q && !locKind.value) return tree.value
  const byId = new Map(tree.value.map(n => [n.id, n]))
  const hit = new Set(tree.value.filter(n => (!locKind.value || n.kind === locKind.value) && (!q || `${n.name} ${n.ident || ''}`.toLowerCase().includes(q))).map(n => n.id))
  const keep = new Set(hit)
  for (const id of hit) for (let p = byId.get(id)?.parent_id; p && !keep.has(p); p = byId.get(p)?.parent_id) keep.add(p)                // Oberbau
  tree.value.forEach(n => { for (let p = n.parent_id; p; p = byId.get(p)?.parent_id) if (hit.has(p)) { keep.add(n.id); break } })     // Unterbau
  return tree.value.filter(n => keep.has(n.id))
})
const parentChoices = computed(() => tree.value.filter(n => n.id !== locForm.value?.id && !CONTAINER_KINDS.includes(n.kind)))

async function load(keepId) {
  try {
    sites.value = await api.sites()
    sel.value = sites.value.find(s => s.id === keepId) || sites.value[0] || null
    await loadLocations()
  } catch (e) { error.value = errText(e) }
}
async function loadLocations() { locations.value = sel.value ? await api.locations(sel.value.id) : [] }
async function select(s) { sel.value = s; await loadLocations() }

function openSite(s) { formError.value = ''; siteForm.value = s ? { ...s } : { code: '', name: '', address: '', note: '' } }
async function saveSite() {
  try {
    const f = siteForm.value
    const saved = f.id ? await api.updateSite(f.id, f) : await api.createSite(f)
    siteForm.value = null; await load(saved.id)
  } catch (e) { formError.value = errText(e) }
}
async function removeSite() {
  if (!confirm(t('Standort {code} löschen?', { code: sel.value.code }))) return
  try { await api.deleteSite(sel.value.id); await load() } catch (e) { error.value = errText(e) }
}

function openLoc(edit, parent) {
  formError.value = ''
  locForm.value = edit ? { ...edit } : { site_id: sel.value.id, parent_id: parent?.id ?? null, kind: parent ? ({ building: 'floor', floor: 'room', room: 'machine', machine: 'cabinet', vehicle: 'cabinet' }[parent.kind] || 'room') : 'building', name: '', rack_units: null, note: '', ident: '' }
}
async function saveLoc() {
  try {
    const f = { ...locForm.value }
    if (!CONTAINER_KINDS.includes(f.kind)) f.rack_units = null
    f.id ? await api.updateLocation(f.id, f) : await api.createLocation(f)
    locForm.value = null; await load(sel.value.id)
  } catch (e) { formError.value = errText(e) }
}
async function removeLoc(n) {
  if (!confirm(t('„{name}“ löschen?', { name: n.name }))) return
  try { await api.deleteLocation(n.id); await load(sel.value.id) } catch (e) { error.value = errText(e) }
}

const route = useRoute()
onMounted(() => load(Number(route.query.site) || undefined))
</script>
