<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4 py-6 overflow-y-auto" @click.self="$emit('close')">
    <div class="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden"
         :class="huge ? 'max-w-6xl' : wide ? 'max-w-2xl' : 'max-w-md'" role="dialog" aria-modal="true" :aria-label="title">
      <div class="flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-slate-700">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ title }}</h2>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" :title="$t('Schließen (Esc)')">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>
      <div class="px-5 py-4 space-y-3 max-h-[70vh] overflow-y-auto"><slot /></div>
      <div v-if="$slots.footer || error" class="px-5 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800">
        <p v-if="error" class="text-sm text-red-500 mb-2 dark:text-red-400">{{ error }}</p>
        <div class="flex items-center justify-end gap-3"><slot name="footer" /></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'

const emit = defineEmits(['close'])
defineProps({ title: String, wide: Boolean, huge: Boolean, error: String })

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
