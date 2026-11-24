<template>
  <SidePanel :open="open" title="Verbindungs-Historie" @close="$emit('close')">
    <template #title>
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Verbindungs-Historie</h2>
      <p class="text-xs text-slate-500 dark:text-slate-400 truncate">{{ subtitle }}</p>
    </template>
    <div class="flex flex-wrap items-end gap-2">
      <div><label :class="lbl">Stand am</label><input v-model="at" type="datetime-local" :class="inp" class="!py-1" @change="load" /></div>
      <button v-if="at" :class="btnLink" @click="at = ''; load()">alle Zeitpunkte</button>
      <button v-if="portId && deviceId" :class="btnLink" @click="$emit('all-ports')">alle Ports des Geräts</button>
    </div>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
    <p v-else-if="loading" class="text-sm text-slate-400">Lade …</p>
    <p v-else-if="!rows.length" class="text-sm text-slate-400">{{ at ? 'Zu diesem Zeitpunkt war nichts verbunden.' : 'Noch keine Verbindungen.' }}</p>
    <ul v-else class="space-y-2">
      <li v-for="h in rows" :key="h.id" class="rounded-lg border px-3 py-2 text-sm"
          :class="h.active ? 'border-green-300 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'">
        <div class="font-mono text-xs flex flex-wrap items-center gap-x-2">
          <span>{{ h.local.hostname !== hostname ? h.local.hostname + ':' : '' }}{{ h.local.port_name }}</span>
          <span class="text-slate-400">↔</span>
          <router-link v-if="h.remote.device_id" :to="`/devices/${h.remote.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline" @click="$emit('close')">{{ h.remote.hostname }}:{{ h.remote.port_name }}</router-link>
          <span v-else title="Port existiert nicht mehr">{{ h.remote.hostname }}:{{ h.remote.port_name }}</span>
          <span v-if="h.active" class="ml-auto text-green-600 dark:text-green-400 font-sans font-medium">steckt</span>
        </div>
        <div class="text-xs text-slate-500 dark:text-slate-400 mt-1">
          {{ fmtTime(h.valid_from) }}<template v-if="!h.active"> – {{ fmtTime(h.valid_to) }}</template>
          <template v-if="h.cable_label || (h.cable_type && h.cable_type !== 'other')"> · {{ [h.cable_label, h.cable_type !== 'other' ? h.cable_type : ''].filter(Boolean).join(' ') }}</template>
        </div>
        <div class="text-xs text-slate-400 mt-0.5">
          hergestellt:
          <router-link v-if="h.workorder" :to="`/workorders/${h.workorder.id}`" class="text-ks-600 dark:text-ks-400 hover:underline" @click="$emit('close')">{{ h.workorder.number }}</router-link>
          <template v-else>{{ h.created_by || '–' }}</template>
          <template v-if="!h.active">
            · getrennt:
            <router-link v-if="h.ended_workorder" :to="`/workorders/${h.ended_workorder.id}`" class="text-ks-600 dark:text-ks-400 hover:underline" @click="$emit('close')">{{ h.ended_workorder.number }}</router-link>
            <template v-else>{{ h.ended_by || '–' }}</template>
            {{ END_REASONS[h.end_reason] || '' }}
          </template>
        </div>
      </li>
    </ul>
  </SidePanel>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import SidePanel from './SidePanel.vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnLink, fmtTime } from '../ui.js'

/** Verbindungs-Historie als Seitenleiste von rechts – für einen Port (portId) oder alle Ports eines Geräts (deviceId). */
const props = defineProps({ open: Boolean, portId: { type: Number, default: null }, deviceId: { type: Number, default: null },
                            hostname: { type: String, default: '' }, portName: { type: String, default: '' } })
defineEmits(['close', 'all-ports'])

const END_REASONS = { manual: '(direkt)', workorder: '', wizard: '(Assistent)', retire: '(Rückbau)', '': '(Port/Gerät gelöscht)' }
const rows = ref([]), at = ref(''), error = ref(''), loading = ref(false)
const subtitle = computed(() => props.portId ? `${props.hostname}:${props.portName}` : props.hostname)

async function load() {
  if (!props.open || !(props.portId || props.deviceId)) return
  loading.value = true
  try {
    const params = props.portId ? { port_id: props.portId } : { device_id: props.deviceId }
    if (at.value) params.at = at.value
    rows.value = await api.cableHistory(params); error.value = ''
  } catch (e) { rows.value = []; error.value = errText(e) } finally { loading.value = false }
}
watch(() => [props.open, props.portId, props.deviceId], ([o]) => { if (o) load() }, { immediate: true })
</script>
