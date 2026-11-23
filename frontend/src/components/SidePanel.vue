<template>
  <Transition name="side">
    <div v-if="open" class="fixed inset-0 z-40 bg-slate-900/40" @click.self="$emit('close')">
      <aside class="side-panel absolute right-0 top-0 bottom-0 w-full max-w-xl flex flex-col bg-white dark:bg-slate-800 border-l border-slate-200 dark:border-slate-700 shadow-2xl"
             role="dialog" aria-modal="true" :aria-label="title">
        <div class="flex items-start justify-between gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-700">
          <div class="min-w-0 flex-1"><slot name="title"><h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ title }}</h2></slot></div>
          <button type="button" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0" title="Schließen (Esc)" @click="$emit('close')">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4"><slot /></div>
        <div v-if="$slots.footer" class="px-5 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800"><slot name="footer" /></div>
      </aside>
    </div>
  </Transition>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'

const props = defineProps({ open: { type: Boolean, default: false }, title: { type: String, default: '' }, closeOnEsc: { type: Boolean, default: true } })
const emit = defineEmits(['close'])

function onKey(e) { if (e.key === 'Escape' && props.open && props.closeOnEsc) emit('close') }
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<style>
.side-enter-active, .side-leave-active { transition: opacity .2s ease; }
.side-enter-from, .side-leave-to { opacity: 0; }
.side-enter-active .side-panel, .side-leave-active .side-panel { transition: transform .25s ease; }
.side-enter-from .side-panel, .side-leave-to .side-panel { transform: translateX(100%); }
</style>
