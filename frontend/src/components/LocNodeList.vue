<template>
  <div>
    <div v-for="(n, i) in nodes" :key="n._k" class="mb-1.5">
      <div class="flex items-center gap-2" :style="{ paddingLeft: depth * 16 + 'px' }">
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300 w-16 text-center shrink-0">{{ LABEL[n.kind] }}</span>
        <input v-model="n.name" :class="inp" class="!py-1 flex-1 min-w-0" :placeholder="`Name ${LABEL[n.kind]}`" />
        <template v-if="CONTAINER.includes(n.kind)">
          <input v-model.number="n.rack_units" type="number" min="1" max="100" :class="inp" class="!py-1 !w-16" :title="n.kind === 'cabinet' ? 'Höheneinheiten (leer = keine HE-Teilung)' : 'Höheneinheiten'" />
          <span class="text-xs text-slate-400">{{ $t('HE') }}</span>
        </template>
        <button :class="btnDanger" @click="nodes.splice(i, 1)" :title="$t('Entfernen (mit Unterstruktur)')">✕</button>
      </div>
      <LocNodeList v-if="!CONTAINER.includes(n.kind)" :nodes="n.children" :parent-rank="RANK[n.kind]" :depth="depth + 1" />
    </div>

    <!-- Hinzufügen -->
    <div class="flex items-center gap-2 flex-wrap text-xs" :style="{ paddingLeft: depth * 16 + 'px' }">
      <span class="text-slate-400">{{ $t('hinzufügen:') }}</span>
      <button v-for="k in kinds" :key="k" :class="btnLink" @click="addOne(k)">+ {{ LABEL[k] }}</button>
      <button v-if="kinds.length" :class="btnLink" @click="many = many ? null : { kind: kinds[0], count: 3, pattern: pattern(kinds[0]), start: 1 }">{{ $t('Mehrere …') }}</button>
    </div>
    <div v-if="many" class="flex items-end gap-2 flex-wrap my-1.5 p-2 rounded-lg bg-slate-50 dark:bg-slate-700/40" :style="{ marginLeft: depth * 16 + 'px' }">
      <div><label :class="lbl">{{ $t('Art') }}</label>
        <select v-model="many.kind" :class="inp" class="!py-1" @change="many.pattern = pattern(many.kind)"><option v-for="k in kinds" :key="k" :value="k">{{ LABEL[k] }}</option></select></div>
      <div><label :class="lbl">{{ $t('Anzahl') }}</label><input v-model.number="many.count" type="number" min="1" max="100" :class="inp" class="!py-1 !w-20" /></div>
      <div><label :class="lbl">{{ $t('Namensmuster') }}</label><input v-model="many.pattern" :class="inp" class="!py-1 !w-40" :title="$t('{n} wird durch die Nummer ersetzt')" /></div>
      <div><label :class="lbl">{{ $t('Ab Nr.') }}</label><input v-model.number="many.start" type="number" min="0" :class="inp" class="!py-1 !w-20" /></div>
      <button :class="btnPrimary" class="!py-1" @click="addMany">{{ $t('Anlegen') }}</button>
      <button :class="btnGhost" class="!py-1" @click="many = null">{{ $t('Abbrechen') }}</button>
    </div>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { ref, computed } from 'vue'
import { inp, lbl, btnPrimary, btnGhost, btnDanger, btnLink } from '../ui.js'

const props = defineProps({ nodes: { type: Array, required: true }, parentRank: { type: Number, default: -1 }, depth: { type: Number, default: 0 } })

const RANK = { building: 0, floor: 1, room: 2, machine: 3, vehicle: 3, rack: 4, wallrack: 4, cabinet: 4 }
const LABEL = { building: t('Gebäude'), floor: t('Etage'), room: t('Raum'), machine: t('Anlage/Maschine'), vehicle: t('Mobile Maschine'), rack: t('Rack'), wallrack: t('Wandgehäuse'), cabinet: t('Schaltschrank') }
const PATTERN = { building: t('Gebäude {n}'), floor: t('Etage {n}'), room: t('Raum {n}'), machine: t('Maschine {n}'), vehicle: t('Lader {n}'), rack: t('Rack {n}'), wallrack: t('Wandgehäuse {n}'), cabinet: t('Schaltschrank {n}') }
const CONTAINER = ['rack', 'wallrack', 'cabinet']
const kinds = computed(() => Object.keys(RANK).filter(k => RANK[k] > props.parentRank))
const many = ref(null)
const pattern = k => PATTERN[k]

function addOne(kind) { props.nodes.push(makeNode(kind)) }
function addMany() {
  const m = many.value
  const count = Math.max(1, Math.min(100, Number(m.count) || 1))
  for (let i = 0; i < count; i++) props.nodes.push(makeNode(m.kind, m.pattern.replace('{n}', (Number(m.start) || 0) + i)))
  many.value = null
}
</script>

<script>
// eigenständig exportierbar, damit der Assistent Knoten anlegen kann
let _seq = 0
export function makeNode(kind, name = '') {
  return { _k: `w${++_seq}${Math.random().toString(36).slice(2, 6)}`, kind, name, rack_units: ({ rack: 42, wallrack: 12 })[kind] ?? null, note: '', children: [] }
}
</script>
