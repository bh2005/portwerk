<template>
  <div class="space-y-2">
    <label :class="lbl">{{ label }}</label>
    <div v-if="!device" class="space-y-1">
      <input v-model="q" :class="inp" :placeholder="$t('Gerät suchen (Hostname, mind. 2 Zeichen)')" @input="search" />
      <div v-if="results.length" class="max-h-36 overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg divide-y divide-slate-100 dark:divide-slate-700">
        <button v-for="d in results" :key="d.id" type="button" @click="pickDevice(d.id)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-700/40">
          {{ d.hostname }} <span class="text-xs text-slate-400">· {{ typeLabel(d.type) }} · {{ d.location_path || 'ohne Location' }}</span></button>
      </div>
    </div>
    <template v-else>
      <div class="flex items-center justify-between gap-2 text-sm">
        <span class="font-medium text-slate-800 dark:text-slate-100">{{ device.hostname }} <span class="text-xs font-normal text-slate-400">· {{ typeLabel(device.type) }}</span></span>
        <button v-if="!locked" type="button" :class="btnLink" @click="reset">{{ $t('anderes Gerät') }}</button>
      </div>
      <select :value="modelValue" :class="inp" @change="choose($event.target.value)">
        <option :value="''" disabled>{{ $t('Port wählen …') }}</option>
        <option v-for="p in shown" :key="p.id" :value="p.id">{{ p.name }} · {{ p.medium }}{{ p.cable ? ` – belegt (${p.cable.device_hostname}:${p.cable.port_name})` : '' }}{{ fits(p) ? '' : ' – Medium passt nicht' }}</option>
      </select>
      <label class="flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" v-model="onlyFree" />{{ ' ' + $t('nur freie Ports zeigen') }}</label>
      <p v-if="!shown.length" class="text-xs text-slate-400">{{ $t('Keine passenden Ports.') }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api.js'
import { inp, lbl, btnLink, typeLabel } from '../ui.js'

const props = defineProps({
  modelValue: { type: [Number, String], default: '' },
  label: { type: String, default: 'Port' },
  siteId: { type: Number, default: null },
  allowed: { type: Array, default: null },            // Medien, die zur Kabelart passen (null = alle)
  presetDeviceId: { type: Number, default: null },
  presetPortId: { type: Number, default: null },
  locked: { type: Boolean, default: false },           // Gerät fest vorgegeben
})
const emit = defineEmits(['update:modelValue', 'select'])

const q = ref(''), results = ref([]), device = ref(null), ports = ref([]), onlyFree = ref(false)
const fits = p => !props.allowed || p.medium === 'other' || props.allowed.includes(p.medium)
const shown = computed(() => ports.value.filter(p => (!onlyFree.value || !p.cable)))

let timer
function search() {
  clearTimeout(timer)
  if (q.value.trim().length < 2) { results.value = []; return }
  timer = setTimeout(async () => { try { results.value = (await api.devices({ q: q.value.trim(), site_id: props.siteId || undefined, limit: 15 })).items } catch { results.value = [] } }, 250)
}
async function pickDevice(id) {
  const d = await api.device(id)
  device.value = d; ports.value = d.ports; results.value = []; q.value = ''
  emit('update:modelValue', ''); emit('select', null)
}
function reset() { device.value = null; ports.value = []; emit('update:modelValue', ''); emit('select', null) }
function choose(v) {
  const p = ports.value.find(x => x.id === Number(v))
  emit('update:modelValue', p ? p.id : ''); emit('select', p ? { ...p, device: device.value } : null)
}

watch(() => props.presetPortId, async v => { if (v) await applyPreset() })
async function applyPreset() {
  if (!props.presetDeviceId) return
  await pickDevice(props.presetDeviceId)
  if (props.presetPortId) choose(props.presetPortId)
}
onMounted(applyPreset)
</script>
