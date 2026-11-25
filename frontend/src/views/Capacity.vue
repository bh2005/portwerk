<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Kapazität') }}</h1>
      <div class="flex gap-2 items-center flex-wrap text-sm">
        <select v-model="siteId" :class="inp" class="!w-48 !py-1.5" @change="load">
          <option :value="null">{{ $t('alle Standorte') }}</option>
          <option v-for="s in allSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option>
        </select>
        <label class="text-slate-500">{{ $t('Engpass unter') }}</label>
        <select v-model.number="warn" :class="inp" class="!w-24 !py-1.5" @change="load">
          <option v-for="w in [5, 10, 15, 20, 30]" :key="w" :value="w">{{ w }} %</option>
        </select>
        <label class="flex items-center gap-1 text-slate-600 dark:text-slate-300"><input v-model="onlyIssues" type="checkbox" />{{ ' ' + $t('nur Engpässe') }}</label>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      {{ $t('Ports je Kategorie:') + ' ' }}<Legend />{{ ' ' + $t('Bei Patchfeldern und Dosen zählt nur die Vorderseite. HE: belegt = mindestens eine Seite; „frei“ = vorne und hinten frei; „Block“ = größter zusammenhängender freier Bereich (passt ein Gerät dieser Höhe hinein?).') }}
    </p>
    <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>

    <!-- Engpässe -->
    <div v-if="data && data.alerts.length" :class="card" class="p-4 border-l-4 border-l-red-500">
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">{{ $t('{n} Engpass/Engpässe (weniger als {p} % frei)', { n: data.alerts.length, p: data.warn }) }}</h2>
      <ul class="text-sm space-y-1">
        <li v-for="(a, i) in data.alerts.slice(0, showAll ? undefined : 8)" :key="i" class="flex gap-2 flex-wrap">
          <span class="font-medium text-red-600 tabular-nums w-14 text-right dark:text-red-400">{{ a.free_pct }} %</span>
          <span class="text-slate-700 dark:text-slate-200">{{ $t(a.label) }}</span>
          <span class="text-slate-500">{{ a.path }}</span>
          <span class="text-slate-400">({{ $t('{a} von {b} frei', { a: a.free, b: a.total }) }}<template v-if="a.kind === 'units'">, {{ $t('größter Block {n} HE', { n: a.largest_block }) }}</template>)</span>
        </li>
      </ul>
      <button v-if="data.alerts.length > 8" :class="btnLink" class="mt-2" @click="showAll = !showAll">{{ showAll ? 'weniger' : `alle ${data.alerts.length} anzeigen` }}</button>
    </div>

    <div v-if="data" :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40">
          <th :class="th">{{ $t('Ort') }}</th>
          <th v-for="(l, c) in data.categories" :key="c" :class="th" class="min-w-[9rem]">{{ $t(l) }}</th>
          <th :class="th" class="min-w-[9rem]">{{ $t('Höheneinheiten') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.key" class="border-t border-slate-100 dark:border-slate-700" :class="r.level === 0 ? 'bg-slate-50/60 dark:bg-slate-800/60' : ''">
            <td :class="td" class="whitespace-nowrap">
              <span :style="{ paddingLeft: `${r.level * 1.1}rem` }" class="inline-flex items-center gap-1">
                <button v-if="r.hasKids" class="w-4 text-slate-400" @click="toggle(r.key)">{{ open.has(r.key) ? '▾' : '▸' }}</button><span v-else class="w-4"></span>
                <span :class="r.level === 0 ? 'font-semibold' : ''" class="text-slate-800 dark:text-slate-100">{{ r.name }}</span>
                <span class="text-[11px] text-slate-400">{{ $t(r.kindLabel) }}</span>
              </span>
            </td>
            <td v-for="(l, c) in data.categories" :key="c" :class="td">
              <Bar v-if="r.stats[c].total" :s="r.stats[c]" :warn="r.warn.includes(c) || (r.level === 0 && pct(r.stats[c]) < data.warn)" />
            </td>
            <td :class="td">
              <div v-if="r.units" class="text-xs" :class="r.warn.includes('units') ? 'text-red-600 dark:text-red-400 font-medium' : 'text-slate-600 dark:text-slate-300'">
                <UnitBar :u="r.units" :warn="r.warn.includes('units')" />
                {{ $t('{a} von {b} frei', { a: r.units.free, b: r.units.total }) }} · {{ $t('Block') }} {{ r.units.largest_block }}
                <span v-if="r.units.half_free" class="text-slate-400"> · {{ $t('{n} halb', { n: r.units.half_free }) }}</span>
                <span v-if="r.units.planned" class="text-sky-600"> · {{ $t('{n} verplant', { n: r.units.planned }) }}</span>
                <span v-if="r.units.freed" class="text-green-600 dark:text-green-400"> · {{ $t('{n} wird frei', { n: r.units.freed }) }}</span>
              </div>
              <div v-else-if="r.siteUnits && r.siteUnits.racks" class="text-xs text-slate-500">{{ $t('{a} von {b} HE frei ({n} Racks)', { a: r.siteUnits.free, b: r.siteUnits.total, n: r.siteUnits.racks }) }}</div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="p-4 text-sm text-slate-400">{{ onlyIssues ? $t('Keine Engpässe.') : $t('Keine Daten.') }}</p>
    </div>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, h, onMounted, ref } from 'vue'
import { api, errText, defaultSite } from '../api.js'
import { inp, card, th, td, btnLink, kindLabel } from '../ui.js'

const COLORS = { used: '#64748b', planned: '#0ea5e9', reserved: '#f59e0b', free: '#22c55e' }
const NAMES = { used: t('belegt'), planned: t('verplant'), reserved: t('reserviert'), free: t('frei') }
const pct = s => s.total ? 100 * s.free / s.total : 100

const Legend = () => h('span', { class: 'inline-flex gap-3 mr-1' }, Object.keys(COLORS).map(k =>
  h('span', { class: 'inline-flex items-center gap-1' }, [h('span', { class: 'inline-block w-2.5 h-2.5 rounded-sm', style: { background: COLORS[k] } }), NAMES[k]])))

/** Gestapelter Balken belegt/verplant/reserviert/frei mit Text „frei x/y (z %)“. */
const Bar = (p) => {
  const s = p.s
  return h('div', { class: 'text-xs', title: Object.keys(COLORS).map(k => `${NAMES[k]}: ${s[k]}`).join(' · ') }, [
    h('div', { class: 'flex h-2 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700 ' + (p.warn ? 'ring-2 ring-red-500' : '') },
      Object.keys(COLORS).map(k => s[k] ? h('div', { style: { width: `${100 * s[k] / s.total}%`, background: COLORS[k] } }) : null)),
    h('div', { class: 'mt-0.5 ' + (p.warn ? 'text-red-600 dark:text-red-400 font-medium' : 'text-slate-600 dark:text-slate-300') },
      t('{a} / {b} frei ({p} %)', { a: s.free, b: s.total, p: Math.round(pct(s)) })),
  ])
}
Bar.props = ['s', 'warn']
const UnitBar = (p) => h('div', { class: 'flex h-2 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700 mb-0.5 ' + (p.warn ? 'ring-2 ring-red-500' : '') }, [
  h('div', { style: { width: `${100 * p.u.used / p.u.total}%`, background: COLORS.used } }),
  h('div', { style: { width: `${100 * p.u.free / p.u.total}%`, background: COLORS.free, marginLeft: 'auto' } }),
])
UnitBar.props = ['u', 'warn']

const data = ref(null), err = ref(''), warn = ref(10), siteId = ref(defaultSite()), allSites = ref([]), onlyIssues = ref(false), showAll = ref(false)
const open = ref(new Set())

function hasIssue(n) { return n.warn.length > 0 || n.children.some(hasIssue) }
const rows = computed(() => {
  if (!data.value) return []
  const out = []
  const walk = (n, level, key) => {
    if (onlyIssues.value && !hasIssue(n)) return
    out.push({ key, level, name: n.name, kindLabel: kindLabel(n.kind), stats: n.stats, units: n.units, warn: n.warn, hasKids: n.children.length > 0 })
    if (open.value.has(key) || onlyIssues.value) n.children.forEach(c => walk(c, level + 1, `l${c.id}`))
  }
  for (const s of data.value.sites) {
    const issue = s.children.some(hasIssue)
    if (onlyIssues.value && !issue) continue
    out.push({ key: `s${s.id}`, level: 0, name: `${s.code} · ${s.name}`, kindLabel: 'Standort', stats: s.stats, units: null, siteUnits: s.units, warn: [], hasKids: s.children.length > 0 })
    if (open.value.has(`s${s.id}`) || onlyIssues.value) s.children.forEach(c => walk(c, 1, `l${c.id}`))
  }
  return out
})
function toggle(k) { const s = new Set(open.value); s.has(k) ? s.delete(k) : s.add(k); open.value = s }

async function load() {
  try {
    data.value = await api.capacity({ site_id: siteId.value || undefined, warn: warn.value }); err.value = ''
    if (data.value.sites.length === 1 && !open.value.size) open.value = new Set([`s${data.value.sites[0].id}`])
  } catch (e) { err.value = errText(e) }
}
onMounted(async () => { try { allSites.value = await api.sites() } catch {} ; load() })
</script>
