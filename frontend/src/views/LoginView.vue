<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 px-4">
    <form @submit.prevent="submit" :class="card" class="w-full max-w-sm p-6 space-y-4">
      <div class="text-center">
        <img src="/logo.svg" alt="" class="w-14 h-14 mx-auto mb-2" />
        <div class="text-lg font-bold text-ks-700 dark:text-ks-300">Portwerk</div>
        <div class="text-sm italic text-slate-500 dark:text-slate-400">– so isses.</div>
        <div class="text-[11px] uppercase tracking-widest text-slate-400 mt-1">{{ $t('Patchplanung') }}</div>
      </div>
      <p v-if="error" class="text-sm bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300 rounded-lg px-3 py-2">{{ error }}</p>
      <div><label :class="lbl">{{ $t('Benutzername') }}</label><input v-model="username" autocomplete="username" autofocus :class="inp" /></div>
      <div><label :class="lbl">{{ $t('Passwort') }}</label><input v-model="password" type="password" autocomplete="current-password" :class="inp" /></div>
      <button :disabled="busy || !username || !password" :class="btnPrimary" class="w-full">{{ busy ? $t('Anmelden…') : $t('Anmelden') }}</button>
      <div class="text-center"><button type="button" class="text-xs text-slate-400 hover:text-ks-600 dark:hover:text-ks-300" @click="setLang(lang === 'en' ? 'de' : 'en')">{{ lang === 'en' ? 'Deutsch' : 'English' }}</button></div>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api, setToken, setUser, errText, startPage } from '../api.js'
import { inp, lbl, card, btnPrimary } from '../ui.js'
import { lang, setLang } from '../i18n.js'

const router = useRouter(), route = useRoute()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')

async function submit() {
  busy.value = true; error.value = ''
  try {
    const r = await api.login(username.value, password.value)
    setToken(r.token); setUser(r.user)
    const to = String(route.query.redirect || '')
    router.push(to.startsWith('/') && !to.startsWith('//') ? to : startPage())          // eigene Startseite bzw. Techniker am Handy: mobil
  } catch (e) { error.value = errText(e, 'Anmeldung fehlgeschlagen') }
  finally { busy.value = false }
}
</script>
