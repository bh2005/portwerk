<template>
  <div class="space-y-4 max-w-3xl">
    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
    <p v-else-if="!data" class="text-sm text-slate-400">Lade …</p>
    <template v-else>
      <p class="text-sm text-slate-500 dark:text-slate-400">Installierte Version: <b class="text-slate-800 dark:text-slate-100">{{ data.version }}</b>
        <span v-if="!data.releases.length"> – keine Release-Hinweise hinterlegt.</span></p>
      <section v-for="(r, i) in data.releases" :key="r.version" :class="card" class="p-4">
        <h2 class="flex items-baseline gap-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
          Version {{ r.version }}
          <span v-if="i === 0" class="text-[10px] font-medium px-1.5 py-0.5 rounded bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">aktuell</span>
          <span class="ml-auto text-xs font-normal text-slate-400">{{ fmtDay(r.date) }}</span>
        </h2>
        <ul class="mt-3 space-y-2">
          <li v-for="(it, n) in r.items" :key="n" class="text-sm text-slate-600 dark:text-slate-300">
            <span v-if="it.title" class="font-medium text-slate-800 dark:text-slate-100">{{ it.title }}</span><template v-if="it.title && it.text"> – </template>{{ it.text }}
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api, errText } from '../api.js'
import { card } from '../ui.js'

const data = ref(null), err = ref('')
const fmtDay = d => d.split('-').reverse().join('.')
onMounted(async () => { try { data.value = await api.releases() } catch (e) { err.value = errText(e) } })
</script>
