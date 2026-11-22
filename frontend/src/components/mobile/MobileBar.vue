<template>
  <header class="sticky top-0 z-30 bg-ks-700 text-white px-4 py-3 flex items-center gap-3 shadow">
    <router-link v-if="back" :to="back" class="text-2xl leading-none -ml-1 px-1" aria-label="Zurück">‹</router-link>
    <div class="flex-1 min-w-0">
      <div class="font-semibold truncate">{{ title }}</div>
      <div v-if="subtitle" class="text-xs text-white/75 truncate">{{ subtitle }}</div>
    </div>
    <slot />
  </header>
</template>

<script setup>
defineProps({ title: String, subtitle: String, back: [String, Object] })
</script>
