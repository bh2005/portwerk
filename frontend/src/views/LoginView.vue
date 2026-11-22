<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 px-4">
    <form @submit.prevent="submit" :class="card" class="w-full max-w-sm p-6 space-y-4">
      <div class="text-center">
        <img src="/logo.svg" alt="" class="w-14 h-14 mx-auto mb-2" />
        <div class="text-lg font-bold text-ks-700 dark:text-ks-300">Portwerk</div>
        <div class="text-xs text-slate-400">Patchplanung</div>
      </div>
      <p v-if="error" class="text-sm bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300 rounded-lg px-3 py-2">{{ error }}</p>
      <div><label :class="lbl">Benutzername</label><input v-model="username" autocomplete="username" autofocus :class="inp" /></div>
      <div><label :class="lbl">Passwort</label><input v-model="password" type="password" autocomplete="current-password" :class="inp" /></div>
      <button :disabled="busy || !username || !password" :class="btnPrimary" class="w-full">{{ busy ? 'Anmelden…' : 'Anmelden' }}</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api, setToken, setUser, errText, hasRole } from '../api.js'
import { inp, lbl, card, btnPrimary } from '../ui.js'

const router = useRouter(), route = useRoute()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')

async function submit() {
  busy.value = true; error.value = ''
  try {
    const r = await api.login(username.value, password.value)
    setToken(r.token); setUser(r.user)
    const to = String(route.query.redirect || '')
    const phone = window.matchMedia?.('(max-width: 640px)').matches && hasRole('techniker')     // Techniker am Handy: mobile Ansicht
    router.push(to.startsWith('/') && !to.startsWith('//') ? to : phone ? '/m' : '/dashboard')
  } catch (e) { error.value = errText(e, 'Anmeldung fehlgeschlagen') }
  finally { busy.value = false }
}
</script>
