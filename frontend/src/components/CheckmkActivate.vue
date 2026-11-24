<template>
  <div class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2 text-sm">
    <div class="flex items-center justify-between">
      <span :class="lbl" class="!mb-0">Ausstehende Änderungen in Checkmk</span>
      <button :class="btnLink" :disabled="busy" @click="load">neu prüfen</button>
    </div>
    <p v-if="loading" class="text-slate-400">Prüfe …</p>
    <p v-else-if="error" class="text-red-500 dark:text-red-400">{{ error }}</p>
    <template v-else-if="p">
      <p v-if="!p.count" class="text-slate-500">Keine ausstehenden Änderungen.</p>
      <template v-else>
        <p class="text-slate-700 dark:text-slate-200"><b>{{ p.count }}</b> ausstehend<span class="text-slate-500"> · {{ p.own }} von Portwerk<template v-if="p.foreign">, <b class="text-amber-600 dark:text-amber-400">{{ p.foreign }} von anderen</b></template></span></p>
        <ul class="text-xs text-slate-500 dark:text-slate-400 max-h-28 overflow-y-auto space-y-0.5">
          <li v-for="(c, i) in p.changes" :key="i"><span class="font-mono">{{ c.user }}</span> · {{ c.text }}</li>
        </ul>
        <p v-if="p.foreign" class="text-xs text-amber-700 dark:text-amber-300">Es gibt fremde Änderungen. Portwerk aktiviert dann nicht – bitte in Checkmk prüfen und dort aktivieren.</p>
        <button :class="btnPrimary" :disabled="busy || p.foreign > 0" @click="activate">In Checkmk aktivieren</button>
      </template>
    </template>
    <p v-if="msg" class="text-green-600 dark:text-green-400">{{ msg }}</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api, errText } from '../api.js'
import { lbl, btnLink, btnPrimary } from '../ui.js'

/** Ausstehende Änderungen in Checkmk anzeigen und – ohne fremde Änderungen – aktivieren. */
const emit = defineEmits(['activated'])
const p = ref(null), loading = ref(false), busy = ref(false), error = ref(''), msg = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { p.value = await api.checkmkPending() } catch (e) { p.value = null; error.value = errText(e) } finally { loading.value = false }
}
async function activate() {
  if (!confirm(`${p.value.count} ausstehende Änderung(en) in Checkmk (Site ${p.value.site}) jetzt aktivieren?`)) return
  busy.value = true; error.value = ''; msg.value = ''
  try { const r = await api.checkmkActivate(); msg.value = r.message; emit('activated'); await load() } catch (e) { error.value = errText(e) } finally { busy.value = false }
}
onMounted(load)
</script>
