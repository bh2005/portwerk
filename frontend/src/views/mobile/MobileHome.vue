<template>
  <div class="min-h-screen bg-slate-100 dark:bg-slate-900 pb-24">
    <MobileBar title="Meine Aufträge" :subtitle="userName">
      <router-link to="/dashboard" class="text-xs underline text-white/80">Vollansicht</router-link>
    </MobileBar>

    <div class="p-3 space-y-4">
      <p v-if="err" class="text-sm text-red-600 bg-red-50 rounded-lg p-3 dark:text-red-400">{{ err }}</p>
      <p v-if="loading" class="text-slate-500">Lade …</p>

      <section v-for="sec in sections" :key="sec.key" v-show="sec.orders.length">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2 px-1">{{ sec.label }} ({{ sec.orders.length }})</h2>
        <div class="space-y-2">
          <router-link v-for="w in sec.orders" :key="w.id" :to="`/m/wo/${w.id}`"
            class="block bg-white dark:bg-slate-800 rounded-2xl p-4 shadow-sm active:bg-slate-50 dark:active:bg-slate-700">
            <div class="flex items-center gap-2">
              <span class="font-mono text-sm text-slate-500">{{ w.number }}</span>
              <span v-if="w.priority === 'high' || w.priority === 'critical'" class="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:text-red-400">{{ w.priority === 'critical' ? 'kritisch' : 'hoch' }}</span>
              <span v-if="isMine(w)" class="ml-auto text-xs px-2 py-0.5 rounded-full bg-ks-100 text-ks-700">mir zugewiesen</span>
            </div>
            <div class="text-lg font-semibold text-slate-800 dark:text-slate-100 mt-1 leading-snug">{{ w.title }}</div>
            <div class="text-sm text-slate-500 mt-1">
              {{ w.location ? w.location.name : '' }}<template v-if="w.planned_from"> · {{ fmtDate(w.planned_from) }}</template>
              <template v-if="w.depends_on && w.depends_on.blocking"> · <span class="text-amber-600 dark:text-amber-400">wartet auf {{ w.depends_on.number }}</span></template>
            </div>
            <div class="mt-3 flex items-center gap-3">
              <div class="flex-1 h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                <div class="h-full bg-green-500" :style="{ width: pct(w) + '%' }"></div>
              </div>
              <span class="text-sm text-slate-600 dark:text-slate-300 tabular-nums">{{ w.progress.done }}/{{ w.progress.total }}</span>
            </div>
          </router-link>
        </div>
      </section>

      <p v-if="!loading && !sections.some(s => s.orders.length)" class="text-center text-slate-500 py-12">Keine Aufträge zur Ausführung.</p>
    </div>

    <div v-if="scanner?.supported" class="fixed bottom-0 inset-x-0 p-3 bg-slate-100/95 dark:bg-slate-900/95 backdrop-blur border-t border-slate-200 dark:border-slate-700">
      <button class="w-full bg-ks-600 text-white text-lg font-semibold py-4 rounded-2xl shadow-lg" @click="scanner.start()">Etikett scannen</button>
    </div>
    <QrScanner ref="scanner" @result="onScan" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errText, getUser } from '../../api.js'
import MobileBar from '../../components/mobile/MobileBar.vue'
import QrScanner from '../../components/mobile/QrScanner.vue'
import { pathFromScan } from './scan.js'

const router = useRouter()
const orders = ref([]), err = ref(''), loading = ref(true), scanner = ref(null)
const user = getUser(), userName = user.full_name || user.username || ''
const isMine = w => w.assigned_to && w.assigned_to.username === user.username
const pct = w => Math.round(100 * w.progress.done / Math.max(1, w.progress.total))
const fmtDate = s => s ? s.split('-').reverse().join('.') : ''
const sort = list => [...list].sort((a, b) => (isMine(b) - isMine(a)) || (a.planned_from || '9').localeCompare(b.planned_from || '9') || a.id - b.id)

const sections = computed(() => [
  { key: 'run', label: 'In Ausführung', orders: sort(orders.value.filter(w => w.status === 'in_progress')) },
  { key: 'rework', label: 'Nacharbeit', orders: sort(orders.value.filter(w => w.status === 'rework')) },
  { key: 'ready', label: 'Freigegeben – bereit zum Start', orders: sort(orders.value.filter(w => w.status === 'approved')) },
])

async function load() {
  loading.value = true
  try {
    const all = await Promise.all(['in_progress', 'rework', 'approved'].map(status => api.workorders({ status })))
    orders.value = all.flat(); err.value = ''
  } catch (e) { err.value = errText(e) } finally { loading.value = false }
}
function onScan(text) {
  const path = pathFromScan(text)
  if (path) router.push(path)
  else err.value = `Unbekannter Code: ${text}`
}
onMounted(load)
</script>
