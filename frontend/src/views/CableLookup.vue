<template>
  <div class="min-h-screen bg-slate-100 dark:bg-slate-900">
    <MobileBar :title="`Kabel ${r?.label || (r ? '#' + r.cable_id : '')}`" subtitle="Etikett gescannt" back="/m">
      <router-link to="/dashboard" class="text-xs underline text-white/80">Vollansicht</router-link>
    </MobileBar>
    <div class="max-w-2xl mx-auto p-3 space-y-4">
      <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
      <p v-if="loading" class="text-sm text-slate-400">Suche …</p>

      <template v-if="r">
        <div v-if="!r.cables.length && !r.planned.length && !r.history.length" :class="card" class="p-4 text-sm text-slate-500">
          Zu diesem Etikett ist nichts bekannt (oder es liegt außerhalb deines Bereichs).
        </div>

        <div v-for="c in r.cables" :key="c.cable_id" :class="card" class="p-4 border-l-4 border-l-green-500">
          <div class="text-xs font-semibold uppercase tracking-wide text-green-600 dark:text-green-400 mb-2">steckt aktuell</div>
          <Ends :a="c.a" :b="c.b" />
          <p class="text-xs text-slate-400 mt-2">{{ [c.cable_type !== 'other' ? c.cable_type : '', c.length_m ? `${c.length_m} m` : '', c.color].filter(Boolean).join(' · ') }}</p>
        </div>

        <div v-for="(p, i) in r.planned" :key="'p' + i" :class="card" class="p-4 border-l-4 border-l-amber-500">
          <div class="text-xs font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400 mb-2">
            geplant: {{ p.action_label }} ·
            <router-link :to="`/workorders/${p.workorder.id}`" class="hover:underline">{{ p.workorder.number }}</router-link>
            ({{ p.workorder.status_label }}{{ p.item_status === 'done' ? ', Position erledigt' : '' }})
          </div>
          <Ends :a="p.a" :b="p.b" />
          <router-link :to="{ path: `/m/wo/${p.workorder.id}`, query: { label: r.label } }"
            class="mt-3 block text-center bg-ks-600 text-white font-semibold py-3 rounded-xl">Im Auftrag abhaken</router-link>
        </div>

        <div v-if="r.history.length" :class="card" class="p-4">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">früher</div>
          <div v-for="(h, i) in r.history" :key="'h' + i" class="text-sm py-1 border-t first:border-t-0 border-slate-100 dark:border-slate-700">
            <Ends :a="h.a" :b="h.b" />
            <div class="text-xs text-slate-400">{{ fmtTime(h.valid_from) }} – {{ fmtTime(h.valid_to) }}
              <span v-if="h.ended_workorder || h.ended_by">· getrennt: {{ h.ended_workorder || h.ended_by }}</span></div>
          </div>
        </div>
      </template>
  </div>
  </div>
</template>

<script setup>
import { h as hx, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, errText } from '../api.js'
import { card, fmtTime } from '../ui.js'
import MobileBar from '../components/mobile/MobileBar.vue'

const end = e => e
  ? (e.device_id ? hx(RouterLink, { to: `/devices/${e.device_id}`, class: 'text-ks-600 dark:text-ks-400 hover:underline' }, () => `${e.hostname}:${e.port}`)
                 : hx('span', `${e.hostname}:${e.port}`))
  : hx('span', '–')
const Ends = (props) => hx('div', { class: 'font-mono text-sm' }, [end(props.a), hx('span', { class: 'mx-2 text-slate-400' }, '↔'), end(props.b)])
Ends.props = ['a', 'b']

const route = useRoute()
const r = ref(null), err = ref(''), loading = ref(false)

async function load() {
  loading.value = true; err.value = ''; r.value = null
  try {
    r.value = await api.resolveLabel(route.params.label ? { label: route.params.label } : { cable_id: route.params.id })
  } catch (e) { err.value = errText(e) } finally { loading.value = false }
}
onMounted(load)
watch(() => route.fullPath, load)
</script>
