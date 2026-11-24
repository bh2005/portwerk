<template>
  <SidePanel :open="open" title="Strecke" @close="$emit('close')">
    <template #title>
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Strecke</h2>
      <p class="text-xs text-slate-500 dark:text-slate-400 truncate font-mono">{{ data?.summary || '' }}</p>
    </template>

    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>
    <p v-if="loading && !data" class="text-sm text-slate-400">Lade …</p>

    <template v-if="data">
      <p v-if="!data.complete" class="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2">
        Strecke unvollständig<template v-if="openEnds.length">: {{ openEnds.join(' · ') }}</template><template v-else-if="nodes.length === 1"> – der Port ist nicht verbunden</template>.</p>

      <!-- offenes Ende links -->
      <ConnectBox v-if="openLeft" :key="'cl' + startOf(0)" label="Verbindung am Anfang herstellen" :port-id="startOf(0)" @done="reload('Verbindung hergestellt.')" @error="e => error = e" />

      <div v-for="(n, i) in nodes" :key="i">
        <!-- Station -->
        <div class="rounded-lg border px-3 py-2" :class="n.passive ? 'border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/30' : 'border-ks-300 dark:border-ks-700 bg-white dark:bg-slate-800'">
          <div class="flex items-center justify-between gap-2">
            <span class="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{{ role(i) }}</span>
            <button v-if="i > 0 && i < nodes.length - 1 && n.passive && canWrite" :class="btnDanger" :disabled="busy" @click="removeStation(n)">entfernen</button>
          </div>
          <div class="font-mono text-sm text-slate-800 dark:text-slate-100">
            <router-link v-if="n.device.id" :to="`/devices/${n.device.id}`" class="text-ks-600 dark:text-ks-400 hover:underline" @click="$emit('close')">{{ n.device.hostname }}</router-link>
            <span v-else class="text-slate-400">{{ n.device.hostname }}</span>
            <span class="text-slate-500"> : {{ n.ports.map(p => p.name).join(' ⇄ ') }}</span>
          </div>
          <div class="text-xs text-slate-400">{{ typeLabel(n.device.type) }}<template v-if="n.device.location"> · {{ n.device.location }}</template><template v-if="n.device.unit"> · HE {{ n.device.unit }}</template></div>
          <div v-for="p in n.ports.filter(x => x.planned.length || x.reservation || x.config)" :key="p.id" class="text-xs text-slate-500 mt-0.5">
            <span class="font-mono">{{ p.name }}</span>
            <span v-if="p.config" class="text-indigo-600 dark:text-indigo-400"> · {{ p.config }}</span>
            <span v-for="(pl, k) in p.planned" :key="k" class="text-sky-700 dark:text-sky-300"> · verplant: {{ pl.workorder.number }} ({{ pl.action }})</span>
            <span v-if="p.reservation" class="text-amber-700 dark:text-amber-300"> · reserviert: {{ p.reservation }}</span>
          </div>
          <!-- LLDP/CDP-Ist an den Enden -->
          <div v-if="lldpAt(i)" class="text-xs mt-1" :class="lldpClass(lldpAt(i).status)">{{ lldpIcon(lldpAt(i).status) }} {{ lldpAt(i).text }}</div>
        </div>

        <!-- Kabel zur nächsten Station -->
        <div v-if="i < links.length" class="ml-5 pl-4 py-2 border-l-2" :class="links[i].provisional ? 'border-dashed border-amber-400' : 'border-slate-300 dark:border-slate-600'">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span class="text-slate-400">│</span>
            <span class="font-medium text-slate-700 dark:text-slate-200">{{ links[i].label || 'Kabel' }}</span>
            <span class="text-xs text-slate-500">{{ cableText(links[i]) }}</span>
            <span v-if="links[i].provisional" class="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" title="Aus dem Soll/Ist-Abgleich übernommen – Dosen und Patchfelder fehlen ggf. noch">vorläufig</span>
            <span v-if="links[i].measurement_ok === true" class="text-green-600" title="Messung bestanden">✓</span>
            <span v-if="links[i].measurement_ok === false" class="text-red-500" title="Messung nicht bestanden">✗</span>
          </div>
          <p v-if="links[i].note" class="text-xs text-slate-400 mt-0.5">{{ links[i].note }}</p>
          <div v-if="canWrite" class="flex gap-3 mt-1">
            <button :class="btnLink" @click="toggleEdit(i)">{{ edit?.i === i ? 'schließen' : 'bearbeiten' }}</button>
            <button :class="btnLink" @click="toggleMove(i)">{{ mv?.i === i ? 'abbrechen' : 'umstecken' }}</button>
            <button :class="btnLink" @click="toggleInsert(i)">{{ ins?.i === i ? 'abbrechen' : '+ Zwischenstation' }}</button>
            <button :class="btnDanger" :disabled="busy" @click="unplug(i)">lösen</button>
          </div>

          <!-- Kabel bearbeiten -->
          <div v-if="edit?.i === i" class="mt-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3">
            <CableFields :model-value="edit.f" />
            <div class="flex gap-2 justify-end"><button :class="btnGhost" @click="edit = null">Abbrechen</button><button :class="btnPrimary" :disabled="busy" @click="saveCable">Speichern</button></div>
          </div>

          <!-- Ziel ändern: ein Ende an einen anderen Port stecken -->
          <div v-if="mv?.i === i" class="mt-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3">
            <div class="text-xs text-slate-500">Welches Ende soll an einen anderen Port?</div>
            <label class="flex items-center gap-2 text-sm"><input v-model="mv.end" type="radio" value="left" /> <span class="font-mono">{{ endName(i, false) }}</span></label>
            <label class="flex items-center gap-2 text-sm"><input v-model="mv.end" type="radio" value="right" /> <span class="font-mono">{{ endName(i, true) }}</span></label>
            <PortPicker :key="'mv' + i + mv.end" v-model="mv.portId" label="Neuer Port" @select="p => mv.sel = p" />
            <p v-if="mv.sel" class="text-xs text-slate-500">Danach: <span class="font-mono">{{ mv.end === 'left' ? mv.sel.device.hostname + ':' + mv.sel.name : endName(i, false) }}</span> →
              <span class="font-mono">{{ mv.end === 'left' ? endName(i, true) : mv.sel.device.hostname + ':' + mv.sel.name }}</span></p>
            <p v-if="mv.sel?.cable" class="text-xs text-red-500">Der Port ist bereits verbunden ({{ mv.sel.cable.device_hostname }}:{{ mv.sel.cable.port_name }}). Zuerst dort lösen.</p>
            <p class="text-xs text-slate-400">Das Kabel behält alle Angaben; in der Historie endet die alte Verbindung, die neue beginnt.</p>
            <div class="flex gap-2 justify-end"><button :class="btnGhost" @click="mv = null">Abbrechen</button>
              <button :class="btnPrimary" :disabled="busy || !mv.sel || !!mv.sel.cable" @click="moveEnd(i)">Umstecken</button></div>
          </div>

          <!-- Zwischenstation einfügen -->
          <div v-if="ins?.i === i" class="mt-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3">
            <PortPicker v-model="ins.portId" label="Patchfeld / Dose und Port" @select="p => ins.sel = p" />
            <template v-if="ins.sel">
              <p v-if="!stationOk(ins.sel)" class="text-xs text-red-500">{{ ins.sel.device.hostname }} ist kein Patchfeld und keine Dose, oder der Port hat keine Gegenseite (vorn ↔ hinten).</p>
              <template v-else>
                <p class="text-xs text-slate-500">Reihenfolge: <span class="font-mono">{{ endName(i, ins.swap) }}</span> → <span class="font-mono">{{ ins.sel.name }}</span> ⇄
                  <span class="font-mono">{{ ins.sel.peer_port_name || '?' }}</span> → <span class="font-mono">{{ endName(i, !ins.swap) }}</span></p>
                <label class="flex items-center gap-2 text-xs text-slate-500"><input v-model="ins.swap" type="checkbox" /> Seiten tauschen (der gewählte Port zeigt zum anderen Ende)</label>
                <p class="text-xs text-slate-400">Das erste Teilkabel behält Nummer, Länge und Einbaudatum, beide behalten Kabelart und Farbe. Das Messprotokoll gehört zum alten Kabel und entfällt.</p>
              </template>
            </template>
            <div class="flex gap-2 justify-end"><button :class="btnGhost" @click="ins = null">Abbrechen</button>
              <button :class="btnPrimary" :disabled="busy || !ins.sel || !stationOk(ins.sel)" @click="insertStation(i)">Einfügen</button></div>
          </div>
        </div>
      </div>

      <!-- offenes Ende rechts / nicht verbundener Port -->
      <ConnectBox v-if="openRight" :key="'cr' + startOf(1)" label="Verbindung am Ende herstellen" :port-id="startOf(1)" @done="reload('Verbindung hergestellt.')" @error="e => error = e" />
      <ConnectBox v-else-if="nodes.length === 1 && !openLeft" :key="'c1' + startOf(1)" label="Verbindung herstellen" :port-id="startOf(1)" @done="reload('Verbindung hergestellt.')" @error="e => error = e" />

      <details v-if="nodes.length > 1" class="text-sm"><summary class="cursor-pointer text-xs text-slate-500">Grafik</summary>
        <div class="mt-2"><PathGraphic :path="data" @navigate="$emit('close')" /></div></details>
    </template>

    <template #footer>
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs text-slate-400">{{ links.length ? `${links.length} Kabel · ${Math.max(0, nodes.length - 2)} Zwischenstation(en)` : '' }}</span>
        <button v-if="canWrite && links.some(l => l.provisional)" :class="btnGhost" :disabled="busy" title="Alle vorläufigen Kabel dieser Strecke als vollständig dokumentiert markieren" @click="complete">Strecke vollständig</button>
      </div>
    </template>
  </SidePanel>
</template>

<script setup>
import { computed, ref, watch, h, defineComponent } from 'vue'
import SidePanel from './SidePanel.vue'
import PathGraphic from './PathGraphic.vue'
import PortPicker from './PortPicker.vue'
import CableFields from './CableFields.vue'
import { api, errText, conflictOf, canWriteMaster } from '../api.js'
import { btnPrimary, btnGhost, btnDanger, btnLink, typeLabel } from '../ui.js'

/** Strecken-Editor: die ganze Strecke ab einem Port als Seitenleiste – Anfang, Ende (mit LLDP/CDP-Ist) und dazwischen Kabel und Stationen,
 *  die sich direkt bearbeiten, einfügen und entfernen lassen. */
const props = defineProps({ open: Boolean, portId: { type: Number, default: null } })
const emit = defineEmits(['close', 'changed'])

const data = ref(null), loading = ref(false), error = ref(''), msg = ref(''), busy = ref(false)
const edit = ref(null), ins = ref(null), mv = ref(null)
const canWrite = canWriteMaster()
const nodes = computed(() => data.value?.nodes || [])
const links = computed(() => data.value?.links || [])
const openEnds = computed(() => (data.value?.ends || []).filter(Boolean))
const openLeft = computed(() => !!data.value?.ends?.[0] && nodes.value.length > 0 && nodes.value[0].passive && canWrite)
const openRight = computed(() => !!data.value?.ends?.[1] && nodes.value.length > 0 && nodes.value[nodes.value.length - 1].passive && canWrite)
const startOf = side => side === 0 ? nodes.value[0]?.ports[0]?.id : nodes.value[nodes.value.length - 1]?.ports.slice(-1)[0]?.id

const role = i => nodes.value.length === 1 ? 'Port' : i === 0 ? 'Anfang' : i === nodes.value.length - 1 ? 'Ende' : 'Zwischenstation'
const lldpAt = i => (data.value?.lldp?.length && nodes.value.length > 1 && [0, nodes.value.length - 1].includes(i) && data.value.lldp[i === 0 ? 0 : 1]?.status !== 'n/a') ? data.value.lldp[i === 0 ? 0 : 1] : null
const lldpIcon = s => ({ ok: '✓ LLDP/CDP:', unknown: '○ LLDP/CDP:' }[s] || '✗ LLDP/CDP:')
const lldpClass = s => ({ ok: 'text-green-600 dark:text-green-400', unknown: 'text-slate-400', not_seen: 'text-amber-600 dark:text-amber-400' }[s] || 'text-red-600 dark:text-red-400')
const cableText = l => [l.type || '', l.length_m ? `${l.length_m} m` : '', l.color].filter(Boolean).join(' · ')

/** Namen der Kabelenden: links = letzter Port der Station i, rechts = erster Port der Station i+1 (``swap`` vertauscht). */
const leftPort = i => nodes.value[i].ports.slice(-1)[0]
const rightPort = i => nodes.value[i + 1].ports[0]
const endName = (i, swap) => { const p = swap ? rightPort(i) : leftPort(i); const n = nodes.value[swap ? i + 1 : i]; return `${n.device.hostname}:${p.name}` }
const stationOk = p => ['patchpanel', 'outlet'].includes(p.device?.type) && !!p.peer_port_id && !p.cable && !(ports => ports.some(x => x.id === p.peer_port_id && x.cable))(p.device?.ports || [])

async function load() {
  if (!props.open || !props.portId) return
  loading.value = true
  try { data.value = await api.portPath(props.portId); error.value = '' } catch (e) { data.value = null; error.value = errText(e) } finally { loading.value = false }
}
async function reload(m) { msg.value = ''; edit.value = ins.value = mv.value = null; await load(); msg.value = m || ''; emit('changed') }
watch(() => [props.open, props.portId], ([o]) => { if (o) { msg.value = ''; error.value = ''; edit.value = ins.value = mv.value = null; data.value = null; load() } }, { immediate: true })

const cableFields = l => ({ cable_label: l.label || '', cable_type: l.cable_type || 'other', fiber_count: l.fiber_count ?? null, length_m: l.length_m ?? null, color: l.color || '',
  installed_at: l.installed_at || null, measurement_ref: l.measurement_ref || '', measurement_ok: l.measurement_ok ?? null, note: l.note || '' })
function toggleEdit(i) { ins.value = mv.value = null; edit.value = edit.value?.i === i ? null : { i, f: { ...cableFields(links.value[i]), provisional: !!links.value[i].provisional } } }
function toggleMove(i) { edit.value = ins.value = null; mv.value = mv.value?.i === i ? null : { i, end: 'right', portId: '', sel: null } }
function toggleInsert(i) { edit.value = mv.value = null; ins.value = ins.value?.i === i ? null : { i, portId: '', sel: null, swap: false } }

async function run(fn, done) {
  busy.value = true; error.value = ''
  try { await fn(); await reload(done) } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
const saveCable = () => run(() => api.updateCable(links.value[edit.value.i].cable_id, { ...edit.value.f }), 'Kabel gespeichert.')
async function moveEnd(i, reserved = false) {
  const m = mv.value
  busy.value = true; error.value = ''
  try {
    await api.moveCableEnd(links.value[i].cable_id, { end_port_id: (m.end === 'left' ? leftPort(i) : rightPort(i)).id, new_port_id: m.sel.id, use_reserved: reserved })
    busy.value = false; await reload('Kabel umgesteckt.')
  } catch (e) {
    busy.value = false
    const c = conflictOf(e)
    if (c && c.code === 'port_reserved' && !reserved && confirm(c.message)) return moveEnd(i, true)
    error.value = errText(e)
  }
}
const insertStation = i => run(() => api.insertStation(links.value[i].cable_id, { port_id: ins.value.sel.id, side_port_id: (ins.value.swap ? rightPort(i) : leftPort(i)).id }), 'Zwischenstation eingefügt.')
function removeStation(n) {
  if (!confirm(`${n.device.hostname} (${n.ports.map(p => p.name).join(' ⇄ ')}) aus der Strecke nehmen?\n\nDie beiden Kabel werden zu einem vorläufigen Direktkabel.`)) return
  return run(() => api.removeStation({ port_id: n.ports[0].id }), 'Zwischenstation entfernt.')
}
function unplug(i) {
  if (!confirm('Dieses Kabel lösen?')) return
  return run(() => api.setCable(leftPort(i).id, { port_b_id: null }), 'Kabel gelöst.')
}
function complete() {
  return run(async () => { for (const l of links.value.filter(x => x.provisional)) await api.updateCable(l.cable_id, { ...cableFields(l), provisional: false }) }, 'Strecke als vollständig markiert.')
}

/** Verbindung an einem offenen Ende bzw. einem unverbundenen Port herstellen (Ziel wählen, Kabeldaten, Speichern). */
const ConnectBox = defineComponent({
  props: { label: String, portId: Number },
  emits: ['done', 'error'],
  setup(p, { emit: em }) {
    const f = ref({ cable_label: '', cable_type: 'Cat6', fiber_count: null, length_m: null, color: '', installed_at: null, measurement_ref: '', measurement_ok: null, note: '' })
    const target = ref(''), sel = ref(null), open = ref(false), b = ref(false)
    async function save(reserved = false) {
      b.value = true
      try { await api.setCable(p.portId, { port_b_id: Number(target.value), ...f.value, use_reserved: reserved }); em('done') }
      catch (e) {
        const c = conflictOf(e)
        if (c && c.code === 'port_reserved' && !reserved && confirm(c.message)) return save(true)
        em('error', errText(e))
      } finally { b.value = false }
    }
    return () => !canWrite ? null : !open.value
      ? h('button', { class: btnLink + ' my-2', onClick: () => { open.value = true } }, '+ ' + p.label)
      : h('div', { class: 'my-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3' }, [
        h('div', { class: 'text-xs font-semibold uppercase tracking-wide text-slate-500' }, p.label),
        h(PortPicker, { modelValue: target.value, 'onUpdate:modelValue': v => { target.value = v }, label: 'Zielgerät und Zielport', onSelect: s => { sel.value = s } }),
        h(CableFields, { modelValue: f.value }),
        h('div', { class: 'flex gap-2 justify-end' }, [
          h('button', { class: btnGhost, onClick: () => { open.value = false } }, 'Abbrechen'),
          h('button', { class: btnPrimary, disabled: b.value || !target.value, onClick: () => save() }, 'Verbinden')]),
      ])
  },
})
</script>
