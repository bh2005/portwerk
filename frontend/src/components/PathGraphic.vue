<template>
  <div class="space-y-3">
    <div class="flex items-center gap-2 flex-wrap text-sm">
      <span class="font-mono font-semibold text-slate-800 dark:text-slate-100">{{ path.summary }}</span>
      <span v-if="path.complete" class="px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">durchgängig · {{ path.hops }} Zwischenstation(en)</span>
      <span v-else-if="path.nodes.length > 1" class="px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">unvollständig</span>
    </div>

    <div class="overflow-x-auto pb-2">
      <div class="flex flex-col md:flex-row md:items-stretch gap-0">
        <div v-if="path.ends[0]" class="flex md:flex-row flex-col items-center"><span :class="openEnd">{{ path.ends[0] }}</span><span class="md:w-8 md:h-0.5 w-0.5 h-6 bg-amber-400 border-dashed"></span></div>
        <template v-for="(n, i) in path.nodes" :key="i">
          <!-- Station -->
          <div class="w-full md:w-40 shrink-0 rounded-xl border-2 p-3 bg-white dark:bg-slate-800"
            :class="n.passive ? 'border-slate-300 dark:border-slate-600 border-dashed' : 'border-slate-400 dark:border-slate-500'">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">{{ typeLabel(n.device.type) }}<span v-if="n.device.status === 'planned'" class="ml-1 text-sky-600">· geplant</span><span v-if="n.device.status === 'retired'" class="ml-1 text-red-500 dark:text-red-400">· außer Betrieb</span></div>
            <router-link v-if="n.device.id" :to="`/devices/${n.device.id}`" class="block font-semibold text-ks-700 dark:text-ks-300 hover:underline break-all" @click="$emit('navigate')">{{ n.device.hostname }}</router-link>
            <div v-else class="font-semibold text-slate-400 italic">{{ n.device.hostname }}</div>
            <div v-if="n.device.location || n.device.unit" class="text-xs text-slate-500">{{ [n.device.location, n.device.unit ? `HE ${n.device.unit}` : ''].filter(Boolean).join(' · ') }}</div>
            <div class="mt-2 flex flex-col gap-1">
              <div v-for="(p, k) in n.ports" :key="k" class="flex items-center gap-1 flex-wrap">
                <span class="font-mono text-xs px-1.5 py-0.5 rounded"
                  :class="p.start ? 'bg-ks-600 text-white ring-2 ring-ks-300' : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'">
                  <template v-if="n.passive && n.ports.length > 1">{{ k === 0 ? '◂' : '▸' }} </template>{{ p.name }}</span>
                <span v-if="p.config" class="text-[10px] px-1 rounded bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300" :title="p.config">{{ p.config }}</span>
                <span v-if="p.reservation" class="text-[10px] px-1 rounded bg-amber-100 text-amber-800" :title="`reserviert: ${p.reservation}`">reserviert</span>
                <router-link v-for="pl in p.planned" :key="pl.workorder.id + pl.action" :to="`/workorders/${pl.workorder.id}`"
                  class="text-[10px] px-1 rounded bg-sky-100 text-sky-800 hover:underline" @click="$emit('navigate')">{{ pl.workorder.number }}: {{ pl.action }}</router-link>
              </div>
            </div>
          </div>
          <!-- Kabel zur nächsten Station -->
          <div v-if="i < path.links.length" class="flex md:flex-col flex-row items-center justify-center md:flex-1 md:min-w-[5.5rem] md:px-1 py-1 md:py-0 gap-2 md:gap-0">
            <div class="text-xs font-mono font-semibold text-slate-700 dark:text-slate-200 md:mb-1 truncate max-w-full order-2 md:order-1" :title="path.links[i].label">{{ path.links[i].label || '–' }}</div>
            <div class="order-1 md:order-2 md:w-full md:h-1.5 w-1.5 h-10 rounded-full" :style="lineStyle(path.links[i])"
              :class="path.links[i].measurement_ok === 0 ? 'outline outline-2 outline-red-500 outline-offset-1' : ''"></div>
            <div class="text-[11px] text-slate-500 md:mt-1 order-3 truncate max-w-full" :title="cableInfo(path.links[i])">{{ cableInfo(path.links[i]) }}</div>
          </div>
        </template>
        <div v-if="path.ends[1]" class="flex md:flex-row flex-col items-center"><span class="md:w-8 md:h-0.5 w-0.5 h-6 bg-amber-400"></span><span :class="openEnd">{{ path.ends[1] }}</span></div>
      </div>
    </div>

    <div v-if="path.lldp.length" class="text-sm space-y-1">
      <div class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">LLDP/CDP-Abgleich der Enden</div>
      <div v-for="(l, i) in path.lldp" :key="i" class="flex gap-2 items-start">
        <span :class="LLDP[l.status]?.cls">{{ LLDP[l.status]?.icon }}</span>
        <span class="text-slate-700 dark:text-slate-200">{{ l.text || LLDP[l.status]?.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { typeLabel } from '../ui.js'

defineProps({ path: { type: Object, required: true } })
defineEmits(['navigate'])

const openEnd = 'text-xs px-2 py-1 rounded-lg bg-amber-50 text-amber-700 border border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 whitespace-nowrap'
const COLORS = { blau: '#2563eb', blue: '#2563eb', gelb: '#eab308', yellow: '#eab308', rot: '#dc2626', red: '#dc2626', grün: '#16a34a', gruen: '#16a34a',
  green: '#16a34a', grau: '#6b7280', gray: '#6b7280', grey: '#6b7280', schwarz: '#111827', black: '#111827', weiß: '#e5e7eb', weiss: '#e5e7eb',
  white: '#e5e7eb', orange: '#ea580c', violett: '#7c3aed', lila: '#7c3aed', purple: '#7c3aed', rosa: '#ec4899', pink: '#ec4899',
  braun: '#92400e', brown: '#92400e', türkis: '#0d9488', tuerkis: '#0d9488', cyan: '#0891b2', aqua: '#0891b2' }
const lineStyle = l => {
  const c = COLORS[String(l.color || '').trim().toLowerCase()]
  return { background: c || '#94a3b8', boxShadow: c === '#e5e7eb' ? 'inset 0 0 0 1px #9ca3af' : 'none' }
}
const cableInfo = l => [l.type, l.length_m ? `${l.length_m} m` : '', l.color, l.measurement_ok === 0 ? 'Messung ✗' : ''].filter(Boolean).join(' · ')
const LLDP = {
  ok: { icon: '✓', cls: 'text-green-600 font-bold', label: 'stimmt' },
  port_mismatch: { icon: '⚠', cls: 'text-red-600 font-bold', label: 'anderer Port' },
  mismatch: { icon: '⚠', cls: 'text-red-600 font-bold', label: 'anderes Gerät' },
  not_seen: { icon: '?', cls: 'text-amber-600 font-bold', label: 'nicht gesehen' },
  unknown: { icon: '–', cls: 'text-slate-400 font-bold', label: 'keine LLDP-Daten' },
}
</script>
