<template>
  <div class="space-y-2 rounded-lg border border-slate-200 dark:border-slate-700 p-3">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ label }}</span>
      <div class="inline-flex rounded overflow-hidden border border-slate-300 dark:border-slate-600 text-xs">
        <button v-for="[k, l] in [['device', 'Ein Gerät'], ['location', 'Alle Geräte einer Location']]" :key="k" type="button" @click="setMode(k)"
          class="px-2 py-1" :class="mode === k ? 'bg-ks-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300'">{{ $t(l) }}</button>
      </div>
    </div>

    <template v-if="mode === 'device'">
      <div v-if="!device" class="space-y-1">
        <input v-model="q" :class="inp" :placeholder="$t('Gerät suchen (Hostname, mind. 2 Zeichen)')" @input="search" />
        <div v-if="results.length" class="max-h-32 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
          <button v-for="d in results" :key="d.id" type="button" @click="pick(d)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/40">
            {{ d.hostname }} <span class="text-xs text-slate-400">· {{ typeLabel(d.type) }} · {{ d.location_path }}</span></button>
        </div>
      </div>
      <div v-else class="flex items-center justify-between text-sm">
        <span class="font-medium text-slate-800 dark:text-slate-100">{{ device.hostname }} <span class="text-xs font-normal text-slate-400">· {{ typeLabel(device.type) }} · {{ device.location_path }}</span></span>
        <button type="button" :class="btnLink" @click="clear">{{ $t('anderes Gerät') }}</button>
      </div>
      <div v-if="device" class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Seite (Patchfeld)') }}</label>
          <select v-model="side" :class="inp" @change="load"><option value="all">{{ $t('alle Ports') }}</option><option value="front">{{ $t('Vorderseite') }}</option><option value="back">{{ $t('Rückseite') }}</option></select></div>
        <label class="flex items-end gap-2 text-sm text-slate-600 dark:text-slate-300 pb-2"><input type="checkbox" v-model="onlyFree" @change="load" />{{ ' ' + $t('nur freie Ports') }}</label>
      </div>
    </template>

    <template v-else>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Location') }}</label>
          <select v-model="locationId" :class="inp" @change="load"><option :value="null" disabled>{{ $t('wählen …') }}</option>
            <option v-for="l in locations" :key="l.id" :value="l.id">{{ kindLabel(l.kind) }}: {{ l.path }}</option></select></div>
        <div><label :class="lbl">{{ $t('Gerätetyp') }}</label>
          <select v-model="types" :class="inp" @change="load"><option value="outlet">{{ $t('Datendosen') }}</option><option value="">{{ $t('alle Geräte') }}</option><option value="patchpanel">{{ $t('Patchfelder') }}</option><option value="switch">{{ $t('Switches') }}</option></select></div>
      </div>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="onlyFree" @change="load" />{{ ' ' + $t('nur freie Ports') }}</label>
    </template>

    <p v-if="error" class="text-xs text-red-500 dark:text-red-400">{{ error }}</p>
    <p v-else-if="loading" class="text-xs text-slate-400">{{ $t('Lade Ports …') }}</p>
    <p v-else-if="ports !== null" class="text-xs" :class="ports.length ? 'text-green-600' : 'text-slate-400'">{{ ports.length }} {{ $t('Ports') }}<template v-if="ports.length"> · {{ ports[0].hostname }}:{{ ports[0].name }} … {{ ports[ports.length - 1].hostname }}:{{ ports[ports.length - 1].name }}</template><template v-if="truncated">{{ ' ' + $t('(gekürzt auf 2000)') }}</template></p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnLink, typeLabel, kindLabel, PLACE_KINDS } from '../ui.js'

const props = defineProps({
  label: { type: String, default: 'Quelle' },
  siteId: { type: Number, default: null },
  initialMode: { type: String, default: 'device' },
  initialSide: { type: String, default: 'all' },
  initialTypes: { type: String, default: 'outlet' },
  presetDeviceId: { type: Number, default: null },
})
const emit = defineEmits(['update:ports'])

const mode = ref(props.initialMode)
const q = ref(''), results = ref([]), device = ref(null)
const side = ref(props.initialSide), onlyFree = ref(true)
const locations = ref([]), locationId = ref(null), types = ref(props.initialTypes)
const ports = ref(null), truncated = ref(false), loading = ref(false), error = ref('')

let timer
function search() {
  clearTimeout(timer)
  if (q.value.trim().length < 2) { results.value = []; return }
  timer = setTimeout(async () => { try { results.value = (await api.devices({ q: q.value.trim(), site_id: props.siteId || undefined, limit: 15 })).items } catch { results.value = [] } }, 250)
}
async function pick(d) { device.value = d; results.value = []; q.value = ''; await load() }
function clear() { device.value = null; ports.value = null; emit('update:ports', []) }
function setMode(m) { mode.value = m; ports.value = null; emit('update:ports', []); if (m === 'location') loadLocations() }

async function loadLocations() {
  if (locations.value.length) return
  try { locations.value = (await api.locations(props.siteId || undefined)).filter(l => PLACE_KINDS.includes(l.kind) || l.kind === 'floor' || l.kind === 'building') } catch (e) { error.value = errText(e) }
}
async function load() {
  error.value = ''
  const spec = mode.value === 'device'
    ? (device.value ? { device_id: device.value.id, side: side.value, only_free: onlyFree.value } : null)
    : (locationId.value ? { location_id: locationId.value, device_types: types.value ? [types.value] : [], only_free: onlyFree.value } : null)
  if (!spec) return
  loading.value = true
  try { const r = await api.portList(spec); ports.value = r.ports; truncated.value = r.truncated; emit('update:ports', r.ports) }
  catch (e) { error.value = errText(e); ports.value = []; emit('update:ports', []) }
  finally { loading.value = false }
}

onMounted(async () => {
  if (mode.value === 'location') await loadLocations()
  if (props.presetDeviceId) { try { await pick(await api.device(props.presetDeviceId)) } catch (e) { error.value = errText(e) } }
})
</script>
