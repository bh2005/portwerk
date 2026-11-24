<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 p-6">
    <div class="w-full max-w-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-sm p-8 text-center space-y-4">
      <div class="mx-auto w-12 h-12 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 flex items-center justify-center">
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4" /></svg>
      </div>
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Noch keine Berechtigung</h1>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        Sie sind als <b>{{ user.full_name || user.username }}</b><span v-if="user.full_name" class="text-slate-400"> ({{ user.username }})</span> angemeldet,
        haben in Portwerk aber noch keine Rechte.
      </p>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        Bitte wenden Sie sich für die Vergabe von Rechten an einen <b>Administrator</b>. Nennen Sie dabei Ihren Benutzernamen und den Standort, für den Sie Zugriff brauchen.
      </p>
      <p v-if="msg" class="text-sm text-amber-700 dark:text-amber-300">{{ msg }}</p>
      <div class="flex justify-center gap-2 pt-2">
        <button :class="btnGhost" :disabled="busy" @click="$emit('recheck')">{{ busy ? 'Prüfe …' : 'Erneut prüfen' }}</button>
        <button :class="btnPrimary" @click="$emit('logout')">Abmelden</button>
      </div>
      <p class="text-xs text-slate-400">Sobald Ihnen Rechte zugewiesen wurden, klicken Sie auf „Erneut prüfen“ (oder melden sich neu an).</p>
    </div>
  </div>
</template>

<script setup>
import { btnPrimary, btnGhost } from '../ui.js'

/** Hinweisseite für Benutzer ohne jede Rolle und ohne Standort-Rechte (z. B. neu angelegte AD-Konten). */
defineProps({ user: { type: Object, required: true }, msg: { type: String, default: '' }, busy: Boolean })
defineEmits(['recheck', 'logout'])
</script>
