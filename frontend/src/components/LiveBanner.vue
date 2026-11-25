<template>
  <div role="status" class="mb-4 flex items-center gap-3 flex-wrap rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-4 py-2 text-sm text-amber-900 dark:text-amber-100 print:hidden">
    <span class="flex-1 min-w-[12rem]">
      <b>{{ info.by || $t('Jemand') }}</b>{{ ' ' + $t('hat Daten geändert') }}<template v-if="ago"> ({{ ago }})</template>. {{ $t('Diese Ansicht zeigt ggf. nicht mehr den aktuellen Stand.') }}
    </span>
    <button class="bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors" @click="$emit('reload')">{{ $t('Neu laden') }}</button>
    <button class="text-xs text-amber-800 dark:text-amber-200 hover:underline" :title="$t('Hinweis ausblenden, bis wieder jemand etwas ändert')" @click="$emit('dismiss')">{{ $t('Ausblenden') }}</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { t } from '../i18n.js'

/** Hinweis „Andere haben Daten geändert“ (Änderungs-Revision, siehe App.vue): statt stiller Überschreibung bietet er „Neu laden“ an. */
const props = defineProps({ info: { type: Object, required: true } })
defineEmits(['reload', 'dismiss'])

const ago = computed(() => {
  if (!props.info.at) return ''
  const s = Math.max(0, Math.round(Date.now() / 1000 - props.info.at))
  if (s < 60) return t('gerade eben')
  const m = Math.round(s / 60)
  return m < 60 ? t('vor {n} Min', { n: m }) : t('vor {n} Std', { n: Math.round(m / 60) })
})
</script>
