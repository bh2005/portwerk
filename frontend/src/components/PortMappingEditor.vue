<template>
  <div class="space-y-3">
    <p class="text-sm text-slate-500">Ordne Patchfeld-Ports fortlaufend Ports eines anderen Geräts zu, z. B. <i>Vorderseite P1–P12 → Switch Port 1–12</i>. Kabelnummern entstehen aus einem Muster.
      Du kannst mehrere Zuordnungen anlegen (z. B. vorn zum Switch, hinten zum nächsten Patchfeld) oder alles später im Gerät verbinden.</p>

    <div v-for="(m, i) in modelValue" :key="m.key" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold uppercase tracking-wide text-slate-500">Zuordnung {{ i + 1 }}</span>
        <button type="button" :class="btnDanger" @click="remove(i)">Entfernen</button>
      </div>
      <div class="grid grid-cols-4 gap-3">
        <div><label :class="lbl">Seite</label>
          <select v-model="m.side" :class="inp" @change="m.from = firstOf(m.side)"><option value="front">Vorderseite</option><option value="back" :disabled="!backNames.length">Rückseite</option></select></div>
        <div><label :class="lbl">Ab Port</label>
          <select v-model="m.from" :class="inp"><option v-for="n in namesOf(m.side)" :key="n" :value="n">{{ n }}</option></select></div>
        <div><label :class="lbl">Anzahl</label><input v-model.number="m.count" type="number" min="1" :max="namesOf(m.side).length" :class="inp" /></div>
        <div><label :class="lbl">Kabelart</label><select v-model="m.cable_type" :class="inp"><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Zielgerät suchen</label><input v-model="m.targetQ" :class="inp" placeholder="Hostname (mind. 2 Zeichen)" @input="search(m)" /></div>
        <div v-if="m.target"><label :class="lbl">Erster Zielport an {{ m.target.hostname }}</label>
          <select v-model="m.startId" :class="inp"><option :value="null" disabled>wählen …</option>
            <option v-for="p in m.targetPorts" :key="p.id" :value="p.id">{{ p.name }}{{ p.cable ? ` – belegt (${p.cable.device_hostname}:${p.cable.port_name})` : '' }}</option></select></div>
      </div>
      <div v-if="m.results.length" class="max-h-28 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
        <button v-for="d in m.results" :key="d.id" type="button" @click="pick(m, d)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/40">
          {{ d.hostname }} <span class="text-xs text-slate-400">· {{ typeLabel(d.type) }} · {{ d.location_path }}</span></button>
      </div>
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">Kabelnummer-Muster</label><input v-model="m.pattern" :class="inp" />
          <p class="text-[11px] text-slate-400 mt-1">{hostname}, {port}, {n}, {nn} (zweistellig)</p></div>
        <div><label :class="lbl">Erste Nummer</label><input v-model.number="m.labelStart" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Länge (m)</label><input v-model.number="m.length_m" type="number" min="0" step="0.5" :class="inp" /></div>
      </div>
    </div>

    <button type="button" :class="btnGhost" @click="add">+ Zuordnung</button>
    <p v-if="result.error" class="text-sm text-red-500 dark:text-red-400">{{ result.error }}</p>
    <p v-else-if="result.links.length" class="text-sm text-green-600 dark:text-green-400">{{ result.links.length }} Verbindung(en): {{ result.links[0].port_name }} → … ,
      Kabelnummer {{ result.links[0].cable_label }}<template v-if="result.links.length > 1"> … {{ result.links[result.links.length - 1].cable_label }}</template></p>
  </div>
</template>

<script>
const natural = (a, b) => a.localeCompare(b, undefined, { numeric: true })

/** Erzeugt aus den Zuordnungen die Verbindungen für den Server (oder einen Fehlertext). */
export function buildLinks(mappings, ctx) {
  const links = [], used = new Set(), usedTarget = new Set()
  for (const [i, m] of mappings.entries()) {
    const where = `Zuordnung ${i + 1}`
    const names = [...(m.side === 'back' ? ctx.backNames : ctx.frontNames)].sort(natural)
    const from = names.indexOf(m.from)
    if (!m.target || !m.startId) return { links: [], error: `${where}: Zielgerät und ersten Zielport wählen` }
    if (!(m.count >= 1)) return { links: [], error: `${where}: Anzahl muss mindestens 1 sein` }
    const own = names.slice(from, from + m.count)
    if (own.length < m.count) return { links: [], error: `${where}: Ab ${m.from} gibt es nur ${own.length} Ports auf dieser Seite` }
    const ti = m.targetPorts.findIndex(p => p.id === m.startId)
    const tgt = m.targetPorts.slice(ti, ti + m.count)
    if (tgt.length < m.count) return { links: [], error: `${where}: ${m.target.hostname} hat ab dem gewählten Port nur ${tgt.length} Ports` }
    for (const [k, n] of own.entries()) {
      if (used.has(n)) return { links: [], error: `${where}: Port ${n} ist schon in einer anderen Zuordnung verwendet` }
      if (usedTarget.has(tgt[k].id)) return { links: [], error: `${where}: Zielport ${tgt[k].name} wird mehrfach verwendet` }
      used.add(n); usedTarget.add(tgt[k].id)
      const num = (Number(m.labelStart) || 0) + k
      links.push({
        port_name: n, target_port_id: tgt[k].id, cable_type: m.cable_type, length_m: m.length_m || null,
        cable_label: m.pattern.replaceAll('{hostname}', ctx.hostname).replaceAll('{port}', n).replaceAll('{nn}', String(num).padStart(2, '0')).replaceAll('{n}', String(num)),
      })
    }
  }
  return { links, error: '' }
}

let seq = 0
export function newMapping(firstFront) {
  return { key: `m${++seq}`, side: 'front', from: firstFront || '', count: 1, cable_type: 'Cat6A', pattern: '{hostname}-{nn}', labelStart: 1, length_m: null,
           targetQ: '', results: [], target: null, targetPorts: [], startId: null }
}
</script>

<script setup>
import { computed } from 'vue'
import { api } from '../api.js'
import { cableTypes } from '../catalog.js'
import { inp, lbl, btnGhost, btnDanger, typeLabel } from '../ui.js'

const props = defineProps({
  modelValue: { type: Array, required: true },
  frontNames: { type: Array, default: () => [] },
  backNames: { type: Array, default: () => [] },
  hostname: { type: String, default: '' },
  siteId: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue'])

const namesOf = side => [...(side === 'back' ? props.backNames : props.frontNames)].sort(natural)
const firstOf = side => namesOf(side)[0] || ''
const result = computed(() => buildLinks(props.modelValue, { frontNames: props.frontNames, backNames: props.backNames, hostname: props.hostname || 'PF' }))

function add() {
  const m = newMapping(firstOf('front'))
  m.count = Math.min(props.frontNames.length, 12) || 1
  m.cable_type = cableTypes.value.find(t => t.name === 'Cat6A') ? 'Cat6A' : (cableTypes.value[0]?.name || 'Cat6')
  emit('update:modelValue', [...props.modelValue, m])
}
function remove(i) { emit('update:modelValue', props.modelValue.filter((_, k) => k !== i)) }

let timers = {}
function search(m) {
  clearTimeout(timers[m.key])
  if (m.targetQ.trim().length < 2) { m.results = []; return }
  timers[m.key] = setTimeout(async () => {
    try { m.results = (await api.devices({ q: m.targetQ.trim(), site_id: props.siteId || undefined, limit: 12 })).items } catch { m.results = [] }
  }, 250)
}
async function pick(m, d) {
  m.target = d; m.results = []; m.startId = null
  try { m.targetPorts = (await api.device(d.id)).ports; m.startId = (m.targetPorts.find(p => !p.cable) || m.targetPorts[0] || {}).id ?? null } catch { m.targetPorts = [] }
}
</script>
