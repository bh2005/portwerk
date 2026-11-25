<template>
  <aside
    class="flex flex-col bg-ks-700 h-screen flex-shrink-0 transition-all duration-200 overflow-hidden z-40"
    :class="collapsed ? 'w-14' : 'w-56'"
  >
    <!-- Kopf -->
    <div class="flex items-center gap-2 h-14 px-2 border-b border-white/10 flex-shrink-0">
      <button @click="collapsed = !collapsed"
        class="p-1.5 rounded text-white/60 hover:text-white hover:bg-white/10 transition-colors flex-shrink-0"
        :title="collapsed ? $t('Aufklappen') : $t('Einklappen')">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
      </button>
      <img src="/logo.svg" alt="" class="w-7 h-7 flex-shrink-0" />
      <div v-show="!collapsed" class="leading-tight min-w-0 overflow-hidden">
        <div class="text-white font-bold text-sm tracking-wide whitespace-nowrap">Portwerk</div>
        <div class="text-white/50 text-[10px] italic tracking-wide whitespace-nowrap" :title="$t('Patchplanung – Soll und Ist der Verkabelung')">– so isses.</div>
      </div>
    </div>

    <!-- Schnellsuche -->
    <div class="px-1.5 pt-2">
      <button @click="$emit('open-search')" :title="$t('Suche (Strg+K oder /)')"
        class="w-full flex items-center gap-2 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors px-2.5 py-1.5 text-sm">
        <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z"/></svg>
        <span v-show="!collapsed" class="flex-1 text-left whitespace-nowrap">{{ $t('Suchen …') }}</span>
        <kbd v-show="!collapsed" class="text-[10px] text-white/40 border border-white/20 rounded px-1">{{ $t('Strg K') }}</kbd>
      </button>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 overflow-y-auto overflow-x-hidden py-2 space-y-0.5 px-1.5">
      <NavLink v-for="link in visibleLinks" :key="link.to" :link="link" :collapsed="collapsed" />
    </nav>

    <!-- Unten -->
    <div class="border-t border-white/10 px-2 py-2 flex-shrink-0 space-y-1">
      <div class="flex items-center" :class="collapsed ? 'flex-col gap-1' : 'justify-between'">
        <button @click="toggleTheme"
          class="p-1.5 rounded text-white/60 hover:text-white hover:bg-white/10 transition-colors"
          :title="isDark ? $t('Light Mode') : $t('Dark Mode')">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path v-if="isDark" fill-rule="evenodd" clip-rule="evenodd"
              d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"/>
            <path v-else d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/>
          </svg>
        </button>

        <button @click="$emit('toggle-help')"
          class="p-1.5 rounded text-white/60 hover:text-white hover:bg-white/10 transition-colors font-bold text-[15px] leading-none w-7 h-7"
          :title="$t('Hilfe (F1)')">?</button>

        <button @click="$emit('open-profile')"
          class="p-1.5 rounded text-white/50 hover:text-white hover:bg-white/10 transition-colors"
          :title="$t('Mein Profil – Passwort ändern')">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
          </svg>
        </button>

        <button @click="doLogout"
          class="p-1.5 rounded text-white/50 hover:text-white hover:bg-white/10 transition-colors" :title="$t('Abmelden')">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
          </svg>
        </button>
      </div>

      <button v-if="!collapsed" @click="$emit('open-profile')" class="group w-full text-left px-1 pb-0.5" :title="$t('Mein Profil – Passwort ändern')">
        <div class="text-white/40 group-hover:text-white/80 text-[10px] uppercase tracking-wide truncate transition-colors">
          {{ user.username }}<span v-if="roleText"> · {{ roleText }}</span> <span class="opacity-60">⚙</span>
        </div>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import NavLink from './SidebarNavLink.vue'
import { api, clearToken, isAdmin, hasRole, canAdministerUsers, getUser } from '../api.js'
import { roleLabel } from '../ui.js'
import { t } from '../i18n.js'

defineEmits(['open-profile', 'toggle-help', 'open-search'])
const router = useRouter()
const collapsed = ref(false)
const isDark = ref(false)
const user = getUser()
const roleText = computed(() => (user.roles || []).map(roleLabel).join(', '))

const IC = {
  dash:   'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
  site:   'M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z',
  device: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01',
  vlan: 'M4 7h16M4 12h16M4 17h10M17 15l3 3-3 3',
  clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  capacity: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  rack:   'M4 6h16M4 10h16M4 14h16M4 18h16M7 4v16M17 4v16',
  catalog: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
  cleanup: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
  compare: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  wan:    'M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  reserve: 'M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z',
  order:  'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
  import: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12',
  admin:  'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z',
}

const allLinks = [
  { to: '/dashboard',   label: 'Übersicht',   icon: IC.dash,   desc: 'Kennzahlen und letzte Importe' },
  { to: '/sites',       label: 'Standorte',   icon: IC.site,   desc: 'Standorte, Gebäude, Räume und Racks' },
  { to: '/devices',     label: 'Geräte',      icon: IC.device, desc: 'Geräte mit Ports, Patchfelder und Dosen' },
  { to: '/racks',       label: 'Racks',       icon: IC.rack,   desc: 'Schrankansicht mit Höheneinheiten' },
  { to: '/vlans',       label: 'VLANs & Profile', icon: IC.vlan, desc: 'VLAN-Katalog und Portprofile (Dokumentation)' },
  { to: '/capacity',    label: 'Kapazität',   icon: IC.capacity, desc: 'Freie Ports und Höheneinheiten, Engpässe' },
  { to: '/timetravel',  label: 'Zeitreise',   icon: IC.clock, desc: 'Verkabelung zu einem Zeitpunkt, Änderungen zwischen zwei Zeitpunkten' },
  { to: '/compare',     label: 'Soll/Ist',    icon: IC.compare, desc: 'Dokumentierte Verkabelung gegen LLDP/CDP-Nachbarn abgleichen' },
  { to: '/cleanup',     label: 'Aufräumen',   icon: IC.cleanup, desc: 'Vorläufige Kabel, tote Patchungen, abgelaufene Reservierungen, liegengebliebene Aufträge' },
  { to: '/wan',         label: 'WAN',         icon: IC.wan,    desc: 'WAN-Verbindungen: Provider, Leitungen, Verträge' },
  { to: '/catalog',     label: 'Katalog',     icon: IC.catalog, desc: 'Gerätemodelle mit Port-Vorlagen und Kabelarten' },
  { to: '/reservations', label: 'Reservierungen', icon: IC.reserve, desc: 'Ports für Projekte freihalten', roleAny: ['planer','freigeber','techniker','viewer','admin'] },
  { to: '/workorders',  label: 'Patchaufträge', icon: IC.order, desc: 'Patchaufträge planen, freigeben und ausführen', roleAny: ['planer','freigeber','techniker','viewer','admin'] },
  { to: '/import',      label: 'Import',      icon: IC.import, desc: 'Geräte und Ports aus CSV, JSON oder Checkmk importieren', adminOnly: true },
  { to: '/admin',       label: 'Verwaltung',  icon: IC.admin,  desc: 'Benutzer und Rechte, API-Zugänge, AD-Anmeldung, Zertifikat und Audit-Log', userAdmin: true },
]
const visibleLinks = computed(() => allLinks.filter(l => {
  if (l.adminOnly) return isAdmin()
  if (l.userAdmin) return canAdministerUsers()
  if (l.roleAny)   return isAdmin() || hasRole(...l.roleAny)
  return true
}).map(l => ({ ...l, label: t(l.label), desc: t(l.desc) })))

function toggleTheme() {
  isDark.value = !isDark.value
  localStorage.setItem('opp_theme', isDark.value ? 'dark' : 'light')
  window.dispatchEvent(new Event('storage'))
}

async function doLogout() {
  try { await api.logout() } catch {}
  clearToken()
  router.push('/login')
}

onMounted(() => { isDark.value = localStorage.getItem('opp_theme') === 'dark' })
</script>
