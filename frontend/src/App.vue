<template>
  <div :class="{ dark: isDark }">
    <!-- Login-Seite und mobile Seiten (Techniker, Scan-Ziel): ohne Seitenleiste -->
    <router-view v-if="$route.path === '/login'" />

    <!-- Angemeldet, aber ohne jede Rolle und ohne Standort-Rechte (z. B. neues AD-Konto): nur der Hinweis -->
    <NoRights v-else-if="noRights" :user="user" :msg="noRightsMsg" :busy="checking" @recheck="recheck" @logout="logoutNow" />

    <router-view v-else-if="$route.meta.bare" />

    <!-- Normales Layout mit Sidebar -->
    <div v-else class="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-900 print:block print:h-auto print:overflow-visible print:bg-white">
      <AppSidebar class="print:hidden" @open-profile="showProfile = true" @toggle-help="showHelp = !showHelp" @open-search="showSearch = true" />
      <main class="flex-1 overflow-y-auto px-6 py-5 print:overflow-visible print:p-0">
        <router-view />
      </main>
    </div>
    <ProfileModal v-if="showProfile" @close="showProfile = false" />
    <HelpPanel :open="showHelp" @close="showHelp = false" />
    <QuickSearch v-if="showSearch && $route.path !== '/login'" @close="showSearch = false" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, getUser, setUser, getToken, clearToken } from './api.js'
import NoRights from './views/NoRights.vue'
import AppSidebar from './components/AppSidebar.vue'
import ProfileModal from './components/ProfileModal.vue'
import HelpPanel from './components/HelpPanel.vue'
import QuickSearch from './components/QuickSearch.vue'

const route = useRoute(), router = useRouter()
const isDark = ref(false)

// Angemeldet, aber ohne jede Rolle und ohne Standort-Rechte (z. B. neu angelegtes AD-Konto): nur ein Hinweis zur Freischaltung
const user = ref(getUser()), token = ref(getToken())
const sync = () => { user.value = getUser(); token.value = getToken() }
watch(() => route.fullPath, sync)
const noRights = computed(() => !!token.value && !!user.value?.id && !(user.value.roles || []).length && !(user.value.scopes || []).length)
const noRightsMsg = ref(''), checking = ref(false)
async function recheck() {
  checking.value = true; noRightsMsg.value = ''
  try { setUser(await api.me()); sync(); if (noRights.value) noRightsMsg.value = 'Es wurden noch keine Rechte vergeben.' }
  catch { /* abgelaufene Sitzung: der Interceptor leitet zur Anmeldung */ } finally { checking.value = false }
}
async function logoutNow() { try { await api.logout() } catch { /* egal */ } clearToken(); sync(); router.push('/login') }
const showProfile = ref(false)
const showHelp = ref(false)
const showSearch = ref(false)

function applyTheme() { isDark.value = localStorage.getItem('opp_theme') === 'dark' }

// F1 und ? schalten das Hilfe-Panel um (? nicht, wenn gerade in ein Eingabefeld getippt wird)
function onKey(e) {
  if (e.key === 'F1') { e.preventDefault(); showHelp.value = !showHelp.value; return }
  if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); showSearch.value = !showSearch.value; return }
  const t = e.target
  const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || t?.isContentEditable
  if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); showSearch.value = true; return }
  if (e.key === '?' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) showHelp.value = !showHelp.value
}

onMounted(() => { applyTheme(); window.addEventListener('keydown', onKey) })
onUnmounted(() => window.removeEventListener('keydown', onKey))
window.addEventListener('storage', applyTheme)
</script>
