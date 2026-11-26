<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-[12vh] px-4" @click.self="$emit('close')" @keydown.esc="$emit('close')">
      <div :class="card" class="w-full max-w-2xl overflow-hidden" role="dialog" :aria-label="$t('Schnellsuche')">
        <div class="flex items-center gap-2 px-4 border-b border-slate-200 dark:border-slate-700">
          <svg class="w-4 h-4 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z"/></svg>
          <input ref="input" v-model="q" @input="soon" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="open(flat[cur])" @keydown.esc="$emit('close')"
            class="flex-1 bg-transparent py-3 text-sm text-slate-800 dark:text-slate-100 focus:outline-none" :placeholder="$t('Gerät, IP, Seriennummer, Standort, Kabelnummer, Auftrag …')" autocomplete="off" spellcheck="false" />
          <kbd class="text-[10px] text-slate-400 border border-slate-300 dark:border-slate-600 rounded px-1">Esc</kbd>
        </div>

        <div class="max-h-[60vh] overflow-y-auto">
          <p v-if="error" class="px-4 py-3 text-sm text-red-500 dark:text-red-400">{{ error }}</p>
          <p v-else-if="q.trim().length < 2" class="px-4 py-6 text-sm text-slate-400 text-center">{{ $t('Mindestens 2 Zeichen eingeben – z. B. den Namen eines Switches, um zu sehen, wo er steht.') }}</p>
          <p v-else-if="!busy && !flat.length" class="px-4 py-6 text-sm text-slate-400 text-center">{{ $t('Nichts gefunden.') }}</p>

          <template v-for="g in groups" :key="g.key">
            <div v-if="g.items.length" class="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{{ g.label }}</div>
            <button v-for="it in g.items" :key="it.key" type="button" @click="open(it)" @mousemove="cur = it.idx"
              class="w-full text-left px-4 py-2 flex items-start gap-3 transition-colors" :class="cur === it.idx ? 'bg-ks-50 dark:bg-ks-900/30' : ''">
              <div class="min-w-0 flex-1">
                <div class="text-sm text-slate-800 dark:text-slate-100 truncate"><span :class="it.mono ? 'font-mono' : 'font-medium'">{{ it.title }}</span>
                  <span v-if="it.badge" class="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300">{{ it.badge }}</span></div>
                <div v-if="it.where" class="text-xs text-ks-700 dark:text-ks-300 truncate">📍 {{ it.where }}</div>
                <div v-if="it.sub" class="text-xs text-slate-400 truncate">{{ it.sub }}</div>
              </div>
              <router-link v-if="it.detail" :to="it.detail" class="text-xs text-ks-600 dark:text-ks-400 hover:underline flex-shrink-0 mt-0.5" @click.stop="$emit('close')">{{ $t('Details') }}</router-link>
            </button>
          </template>
        </div>
        <div class="px-4 py-1.5 text-[11px] text-slate-400 border-t border-slate-100 dark:border-slate-700 flex gap-4"><span>{{ $t('↑↓ wählen') }}</span><span>{{ $t('Enter öffnen') }}</span><span>{{ $t('Strg+K oder / öffnet die Suche') }}</span></div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, errText } from '../api.js'
import { card, typeLabel, kindLabel, statusLabel } from '../ui.js'
import { t } from '../i18n.js'

const emit = defineEmits(['close'])
const router = useRouter()
const input = ref(null), q = ref(''), res = ref(null), busy = ref(false), error = ref(''), cur = ref(0)
let timer, seq = 0

const STATUS = { planned: 'planned', retired: 'retired' }               // nur diese Status werden angezeigt
const groups = computed(() => {
  const r = res.value
  if (!r || q.value.trim().length < 2) return []
  let n = 0
  const mk = (key, label, items) => ({ key, label, items: items.map(x => ({ ...x, idx: n++ })) })
  return [
    mk('devices', t('Geräte'), r.devices.map(d => ({
      key: 'd' + d.id, title: d.hostname, mono: true, badge: [typeLabel(d.type), STATUS[d.status] && statusLabel(d.status)].filter(Boolean).join(' · '),
      where: d.location ? `${d.site ? d.site + ' · ' : ''}${d.location}${d.position ? ` · ${t('HE')} ${d.position}${d.height_u > 1 ? '–' + (d.position + d.height_u - 1) : ''}` : ''}` : t('ohne Standort/Location'),
      sub: [d.model, d.mgmt_ip].filter(Boolean).join(' · '), to: d.location_id ? `/racks?device=${d.id}` : `/devices/${d.id}`, detail: `/devices/${d.id}` }))),
    mk('sites', t('Standorte'), r.sites.map(s => ({ key: 's' + s.id, title: `${s.code} – ${s.name}`, sub: s.address, to: '/sites', query: { site: s.id } }))),
    mk('locations', t('Orte'), r.locations.map(l => ({ key: 'l' + l.id, title: l.name, badge: kindLabel(l.kind), sub: l.path, to: `/racks?location=${l.id}` }))),
    mk('wan', t('WAN-Verbindungen'), r.wan.map(w => ({ key: 'w' + w.id, title: w.name, sub: [w.provider, w.circuit_id].filter(Boolean).join(' · '), to: `/wan?id=${w.id}` }))),
    mk('trunks', t('SIP-Trunks'), (r.trunks || []).map(x => ({ key: 't' + x.id, title: x.name, sub: [x.provider, x.trunk_ident].filter(Boolean).join(' · '), to: `/telephony?id=${x.id}` }))),
    mk('orders', t('Patchaufträge'), r.orders.map(o => ({ key: 'o' + o.id, title: `${o.number} ${o.title}`, badge: o.status, to: `/workorders/${o.id}` }))),
    mk('cables', t('Kabel'), r.cables.map(c => ({ key: 'c' + c.id, title: c.label, mono: true, sub: `${c.a} ↔ ${c.b}`, to: `/devices/${c.device_id}` }))),
  ]
})
const flat = computed(() => groups.value.flatMap(g => g.items))

function soon() { clearTimeout(timer); timer = setTimeout(run, 180) }
async function run() {
  const text = q.value.trim(), mine = ++seq
  if (text.length < 2) { res.value = null; return }
  busy.value = true; error.value = ''
  try { const r = await api.search(text); if (mine === seq) { res.value = r; cur.value = 0 } }
  catch (e) { if (mine === seq) error.value = errText(e) }
  finally { if (mine === seq) busy.value = false }
}
function move(d) { if (flat.value.length) cur.value = (cur.value + d + flat.value.length) % flat.value.length }
function open(it) { if (!it) return; emit('close'); router.push(it.query ? { path: it.to, query: it.query } : it.to) }
onMounted(() => input.value?.focus())
</script>
