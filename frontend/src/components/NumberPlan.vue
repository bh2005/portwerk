<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <p class="text-sm text-slate-500 dark:text-slate-400 max-w-3xl">{{ $t('Rufnummernblöcke mit Durchwahlbereich; je Durchwahl frei, reserviert oder vergeben – an Person, Funktion, Sammelruf, Fax oder Sonderanschluss, optional mit Endgerät. Planer und Administratoren des Standorts vergeben Durchwahlen, Blöcke legen Administratoren an.') }}</p>
      <div class="flex gap-2">
        <a :class="btnGhost" href="/api/numbers/export.csv" @click.prevent="downloadCsv()">{{ $t('CSV-Export') }}</a>
        <button v-if="canWrite" :class="btnPrimary" @click="openBlock()">{{ $t('+ Rufnummernblock') }}</button>
      </div>
    </div>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <div :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr><th :class="th">{{ $t('Block') }}</th><th :class="th">{{ $t('Rufnummern') }}</th><th :class="th">{{ $t('Standort') }}</th><th :class="th">{{ $t('SIP-Trunk') }}</th>
          <th :class="th" class="w-64">{{ $t('Belegung') }}</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="b in blocks" :key="b.id" class="border-t border-slate-100 dark:border-slate-700 cursor-pointer" :class="sel?.id === b.id ? 'bg-ks-50 dark:bg-ks-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-700/30'" @click="select(b.id)">
            <td :class="td" class="font-medium text-slate-800 dark:text-slate-100">{{ b.name || '–' }}</td>
            <td :class="td" class="font-mono text-xs">{{ b.first }} … {{ b.last.split('-').pop() }}</td>
            <td :class="td" class="text-xs">{{ b.site }}</td>
            <td :class="td" class="text-xs">{{ b.trunk?.name || '–' }}</td>
            <td :class="td"><Usage :c="b.counts" /></td>
            <td :class="td" class="text-right"><button :class="btnLink" @click.stop="select(b.id)">{{ $t('Öffnen') }}</button></td>
          </tr>
          <tr v-if="!blocks.length"><td colspan="6" class="px-3 py-6 text-center text-slate-400">{{ $t('Noch keine Rufnummernblöcke.') }}</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="sel" :class="card" class="p-4 space-y-3">
      <div class="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">{{ sel.name || sel.prefix }} <span class="font-mono text-sm font-normal text-slate-500">{{ sel.first }} … {{ sel.last }}</span></h2>
          <p class="text-xs text-slate-400 mt-0.5">{{ sel.site }}<template v-if="sel.trunk"> · {{ $t('SIP-Trunk') }} {{ sel.trunk.name }}</template>
            · {{ $t('{a} vergeben, {r} reserviert, {f} frei', { a: sel.counts.assigned, r: sel.counts.reserved, f: sel.counts.free }) }}
            <span v-if="sel.counts.expired" class="text-amber-600 dark:text-amber-400"> · {{ $t('{n} Reservierung(en) abgelaufen', { n: sel.counts.expired }) }}</span></p>
          <p v-if="sel.note" class="text-xs text-slate-500 mt-1 whitespace-pre-line">{{ sel.note }}</p>
        </div>
        <div class="flex gap-2 flex-wrap items-center">
          <button v-if="sel.can_assign" :class="btnPrimary" :disabled="!sel.counts.free" @click="assignNext">{{ $t('Nächste freie vergeben …') }}</button>
          <a :class="btnGhost" href="#" @click.prevent="downloadCsv(sel.id)">{{ $t('CSV (mit freien)') }}</a>
          <button v-if="sel.can_edit" :class="btnLink" @click="openBlock(sel)">{{ $t('Block bearbeiten') }}</button>
          <button v-if="sel.can_edit" :class="btnLink" class="!text-red-600" @click="removeBlock">{{ $t('Löschen') }}</button>
        </div>
      </div>
      <div class="flex flex-wrap gap-3 items-center">
        <select v-model="fStatus" :class="inp" class="max-w-[14rem]"><option v-for="[k, l] in FILTERS" :key="k" :value="k">{{ $t(l) }}</option></select>
        <input v-model="q" :class="inp" class="max-w-xs" :placeholder="$t('Durchwahl, Name, Notiz …')" />
        <span class="text-xs text-slate-400">{{ $t('{n} Nummern', { n: filtered.length }) }}</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Rufnummer') }}</th><th :class="th">{{ $t('Status') }}</th><th :class="th">{{ $t('Art') }}</th><th :class="th">{{ $t('Inhaber / Funktion') }}</th>
            <th :class="th">{{ $t('Endgerät') }}</th><th :class="th">{{ $t('Notiz') }}</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="r in filtered.slice(0, limit)" :key="r.extension" class="border-t border-slate-100 dark:border-slate-700" :class="r.extension === focusExt ? 'bg-amber-50 dark:bg-amber-900/20' : ''">
              <td :class="td" class="font-mono text-xs whitespace-nowrap">{{ r.number }}</td>
              <td :class="td"><span class="px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap" :class="statusClass(r)">{{ statusText(r) }}</span></td>
              <td :class="td" class="text-xs">{{ r.a ? $t(r.a.kind_label) : '' }}</td>
              <td :class="td" class="text-slate-800 dark:text-slate-100">{{ r.a?.holder }}</td>
              <td :class="td" class="text-xs font-mono whitespace-nowrap"><router-link v-if="r.a?.device" :to="`/devices/${r.a.device.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ r.a.device.hostname }}</router-link></td>
              <td :class="td" class="text-xs text-slate-500 max-w-xs truncate" :title="r.a?.note">{{ r.a?.note }}</td>
              <td :class="td" class="text-right whitespace-nowrap">
                <template v-if="sel.can_assign">
                  <button :class="btnLink" @click="openAssign(r)">{{ r.a ? $t('Bearbeiten') : $t('Vergeben') }}</button>
                  <button v-if="r.a" :class="btnLink" class="ml-3 !text-red-600" @click="free(r)">{{ $t('Freigeben') }}</button>
                </template>
              </td>
            </tr>
            <tr v-if="!filtered.length"><td colspan="7" class="px-3 py-6 text-center text-slate-400">{{ $t('Keine Nummern für diesen Filter.') }}</td></tr>
          </tbody>
        </table>
        <div v-if="filtered.length > limit" class="text-center mt-2"><button :class="btnGhost" @click="limit += 200">{{ $t('Weitere {n} anzeigen', { n: Math.min(200, filtered.length - limit) }) }}</button></div>
      </div>
    </div>

    <!-- Durchwahl vergeben/bearbeiten -->
    <ModalDialog v-if="af" :title="af.number" :error="afError" @close="af = null">
      <div class="flex gap-4 text-sm">
        <label v-for="s in meta.statuses" :key="s.value" class="flex items-center gap-2"><input type="radio" :value="s.value" v-model="af.status" />{{ ' ' + $t(s.label) }}</label>
      </div>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Art') }}</label><select v-model="af.kind" :class="inp"><option v-for="k in meta.kinds" :key="k.value" :value="k.value">{{ $t(k.label) }}</option></select></div>
        <div><label :class="lbl">{{ $t('Inhaber / Funktion') }}</label><input v-model="af.holder" :class="inp" :placeholder="$t('z. B. Erika Müller, Zentrale, Aufzug Halle 2')" /></div>
        <div><label :class="lbl">{{ $t('Endgerät (optional)') }}</label><select v-model="af.device_id" :class="inp"><option :value="null">–</option>
          <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.hostname }} ({{ typeLabel(d.type) }})</option></select></div>
        <div v-if="af.status === 'reserved'"><label :class="lbl">{{ $t('Reserviert bis (optional)') }}</label><input v-model="af.reserved_until" type="date" :class="inp" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="af.note" :class="inp" /></div>
      <template #footer>
        <button :class="btnGhost" @click="af = null">{{ $t('Abbrechen') }}</button>
        <button :class="btnPrimary" :disabled="busy || (af.status === 'assigned' && !af.holder.trim())" @click="saveAssign">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>

    <!-- Block anlegen/bearbeiten -->
    <ModalDialog v-if="bf" :title="bf.id ? $t('Rufnummernblock bearbeiten') : $t('Neuer Rufnummernblock')" :error="bfError" @close="bf = null">
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Standort') }}</label><select v-model="bf.site_id" :class="inp"><option :value="null" disabled>{{ $t('wählen …') }}</option><option v-for="s in writeSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select></div>
        <div><label :class="lbl">{{ $t('SIP-Trunk (optional)') }}</label><select v-model="bf.sip_trunk_id" :class="inp"><option :value="null">–</option><option v-for="t in trunks.filter(x => x.site_id === bf.site_id)" :key="t.id" :value="t.id">{{ t.name }}</option></select></div>
        <div><label :class="lbl">{{ $t('Name') }}</label><input v-model="bf.name" :class="inp" :placeholder="$t('z. B. Hauptanschluss Werk A')" /></div>
        <div><label :class="lbl">{{ $t('Präfix (Rufnummer ohne Durchwahl)') }}</label><input v-model="bf.prefix" :class="inp" class="font-mono" placeholder="+49 6181 1234" /></div>
        <div><label :class="lbl">{{ $t('Durchwahl von') }}</label><input v-model.number="bf.range_from" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Durchwahl bis') }}</label><input v-model.number="bf.range_to" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Feste Stellenzahl (0 = ohne führende Nullen)') }}</label><input v-model.number="bf.width" type="number" min="0" max="8" :class="inp" /></div>
        <div class="text-xs text-slate-500 self-end pb-2">{{ $t('Beispiel:') }} <span class="font-mono">{{ preview }}</span></div>
      </div>
      <div><label :class="lbl">{{ $t('Notiz') }}</label><textarea v-model="bf.note" rows="2" :class="inp"></textarea></div>
      <template #footer>
        <button :class="btnGhost" @click="bf = null">{{ $t('Abbrechen') }}</button>
        <button :class="btnPrimary" :disabled="busy || !bf.site_id || !bf.prefix" @click="saveBlock">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ModalDialog from './ModalDialog.vue'
import { api, errText, canWriteMaster, getToken, isGlobal, siteAdminIds } from '../api.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnLink, typeLabel } from '../ui.js'

const route = useRoute()
const canWrite = canWriteMaster()
const blocks = ref([]), sel = ref(null), sites = ref([]), trunks = ref([]), devices = ref([]), meta = ref({ statuses: [], kinds: [] })
const error = ref(''), busy = ref(false), fStatus = ref('all'), q = ref(''), limit = ref(200), focusExt = ref(null)
const af = ref(null), afError = ref(''), bf = ref(null), bfError = ref('')
const FILTERS = [['all', 'alle Nummern'], ['free', 'nur freie'], ['assigned', 'nur vergebene'], ['reserved', 'nur reservierte'], ['expired', 'abgelaufene Reservierungen']]
const PHONE_TYPES = ['phone', 'dect_base', 'endpoint', 'voice_gateway', 'gateway', 'other']

const Usage = (p) => {
  const c = p.c, pct = n => `${c.total ? (100 * n / c.total) : 0}%`
  return h('div', { class: 'space-y-0.5' }, [
    h('div', { class: 'h-2 rounded bg-slate-100 dark:bg-slate-700 overflow-hidden flex' }, [
      h('div', { class: 'bg-ks-600', style: { width: pct(c.assigned) } }), h('div', { class: 'bg-amber-400', style: { width: pct(c.reserved) } })]),
    h('div', { class: 'text-[11px] text-slate-500' }, t('{a} vergeben, {r} reserviert, {f} frei', { a: c.assigned, r: c.reserved, f: c.free }))])
}
Usage.props = ['c']

const writeSites = computed(() => isGlobal() ? sites.value : sites.value.filter(s => siteAdminIds().includes(s.id)))
const pad = (b, n) => b.width ? String(n).padStart(b.width, '0') : String(n)
const preview = computed(() => bf.value ? `${(bf.value.prefix || '').trim() || '+49 …'}-${pad(bf.value, bf.value.range_from ?? 0)}` : '')
const rows = computed(() => {
  if (!sel.value) return []
  const got = new Map(sel.value.assignments.map(a => [a.extension, a]))
  const out = []
  for (let e = sel.value.range_from; e <= sel.value.range_to; e++) {
    const a = got.get(e)
    out.push({ extension: e, ext: pad(sel.value, e), number: `${sel.value.prefix}-${pad(sel.value, e)}`, a })
  }
  return out
})
const filtered = computed(() => {
  const ql = q.value.trim().toLowerCase(), qd = ql.replace(/\D/g, '')
  return rows.value.filter(r => {
    if (fStatus.value === 'free' && r.a) return false
    if (['assigned', 'reserved'].includes(fStatus.value) && r.a?.status !== fStatus.value) return false
    if (fStatus.value === 'expired' && !r.a?.expired) return false
    if (!ql) return true
    const qn = qd.replace(/^0+/, '')                                      // 06181… findet auch +49 6181…
    const digitHit = qd && (qd.length <= 5 ? r.ext.startsWith(qd) : r.number.replace(/\D/g, '').includes(qn))   // kurz: Durchwahl, lang: ganze Nummer
    return digitHit || (r.a && `${r.a.holder} ${r.a.note} ${r.a.device?.hostname || ''}`.toLowerCase().includes(ql))
  })
})
const statusText = r => !r.a ? t('frei') : r.a.expired ? t('Reservierung abgelaufen') : t(r.a.status_label) + (r.a.reserved_until ? ' ' + t('bis {d}', { d: r.a.reserved_until }) : '')
const statusClass = r => !r.a ? 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
  : r.a.expired ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
  : r.a.status === 'reserved' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'

watch([fStatus, q], () => { limit.value = 200 })

async function loadBlocks() {
  try { blocks.value = await api.numberBlocks() } catch (e) { error.value = errText(e) }
}
async function select(id) {
  error.value = ''
  try {
    sel.value = await api.numberBlock(id)
    const devs = (await api.devices({ site_id: sel.value.site_id, limit: 500 })).items || []
    devices.value = devs.filter(d => PHONE_TYPES.includes(d.type))
  } catch (e) { error.value = errText(e) }
}
async function refresh() { await loadBlocks(); if (sel.value) await select(sel.value.id) }

function openAssign(r) {
  afError.value = ''
  af.value = { ext: r.extension, number: r.number, status: r.a?.status || 'assigned', kind: r.a?.kind || 'person', holder: r.a?.holder || '',
    device_id: r.a?.device_id ?? null, reserved_until: r.a?.reserved_until || null, note: r.a?.note || '' }
}
async function assignNext() {
  try { const n = await api.nextFreeNumber(sel.value.id); openAssign({ extension: n.extension, number: n.number }) } catch (e) { error.value = errText(e) }
}
async function saveAssign() {
  busy.value = true; afError.value = ''
  try {
    const { ext, number, ...body } = af.value
    await api.setNumber(sel.value.id, ext, { ...body, reserved_until: body.status === 'reserved' ? (body.reserved_until || null) : null })
    af.value = null; focusExt.value = ext; await refresh()
  } catch (e) { afError.value = errText(e) } finally { busy.value = false }
}
async function free(r) {
  if (!confirm(t('{n} freigeben ({h})?', { n: r.number, h: r.a.holder || t(r.a.status_label) }))) return
  try { await api.freeNumber(sel.value.id, r.extension); await refresh() } catch (e) { error.value = errText(e) }
}

function openBlock(b = null) {
  bfError.value = ''
  bf.value = b ? { id: b.id, site_id: b.site_id, sip_trunk_id: b.sip_trunk_id, name: b.name, prefix: b.prefix, range_from: b.range_from, range_to: b.range_to, width: b.width, note: b.note }
    : { site_id: writeSites.value[0]?.id ?? null, sip_trunk_id: route.query.trunk ? Number(route.query.trunk) : null, name: '', prefix: '', range_from: 0, range_to: 99, width: 0, note: '' }
}
async function saveBlock() {
  busy.value = true; bfError.value = ''
  try {
    const { id, ...body } = bf.value
    const saved = id ? await api.updateNumberBlock(id, body) : await api.createNumberBlock(body)
    bf.value = null; await loadBlocks(); await select(saved.id)
  } catch (e) { bfError.value = errText(e) } finally { busy.value = false }
}
async function removeBlock() {
  if (!confirm(t('Rufnummernblock „{n}“ löschen?', { n: sel.value.name || sel.value.prefix }))) return
  try { await api.deleteNumberBlock(sel.value.id); sel.value = null; await loadBlocks() } catch (e) { error.value = errText(e) }
}
async function downloadCsv(blockId = null) {
  const url = '/api/numbers/export.csv' + (blockId ? `?block_id=${blockId}&include_free=true` : '')
  const r = await fetch(url, { headers: { 'X-Auth-Token': getToken() } })
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'rufnummernplan.csv'; a.click(); URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  try { [meta.value, sites.value, trunks.value] = await Promise.all([api.numberMeta(), api.sites(), api.sipTrunks()]) } catch (e) { error.value = errText(e) }
  await loadBlocks()
  const id = Number(route.query.block)
  if (id) {
    await select(id)
    if (route.query.ext != null) { focusExt.value = Number(route.query.ext); q.value = sel.value ? pad(sel.value, focusExt.value) : '' }
  }
})
</script>
