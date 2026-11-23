<template>
  <div class="max-w-5xl space-y-4">
    <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Verwaltung</h1>

    <div class="flex gap-1 border-b border-slate-200 dark:border-slate-700">
      <button v-for="t in tabs" :key="t[0]" @click="tab = t[0]"
        class="px-4 py-2 text-sm -mb-px border-b-2 transition-colors"
        :class="tab === t[0] ? 'border-ks-600 text-ks-700 dark:text-ks-300 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'">{{ t[1] }}</button>
    </div>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

    <AdminLdap v-if="tab === 'ldap'" />
    <AdminTls v-if="tab === 'tls'" />
    <AdminBackup v-if="tab === 'backup'" />
    <AdminMail v-if="tab === 'mail'" />
    <AdminCheckmk v-if="tab === 'checkmk'" />
    <AdminOpenPlan v-if="tab === 'openplan'" />

    <!-- Benutzer -->
    <div v-if="tab === 'users'" class="space-y-3">
      <div class="text-right"><button :class="btnPrimary" @click="openUser()">+ Benutzer</button></div>
      <div :class="card" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Benutzer</th><th :class="th">Rollen</th><th :class="th">Letzte Anmeldung</th><th :class="th">Status</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="u in users" :key="u.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td"><div class="font-medium text-slate-800 dark:text-slate-100">{{ u.username }} <span v-if="u.source === 'ldap'" class="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-ks-50 dark:bg-ks-900/30 text-ks-700 dark:text-ks-300 font-normal" title="Anmeldung über Active Directory; Rollen kommen aus den AD-Gruppen">AD</span></div><div class="text-xs text-slate-400">{{ u.full_name }} {{ u.email }}</div></td>
              <td :class="td"><div v-if="u.roles.length">{{ u.roles.map(roleLabel).join(', ') }} <span class="text-[10px] text-slate-400">(global)</span></div>
                <div class="flex flex-wrap gap-1 mt-0.5"><span v-for="s in u.scopes" :key="s.id" class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300" :title="s.source === 'ldap' ? 'aus AD-Gruppe' : 'manuell vergeben'">{{ scopeText(s) }}<span v-if="s.source === 'ldap'"> · AD</span></span></div>
                <div v-if="!u.roles.length && !u.scopes.length" class="text-xs text-slate-400">–</div></td>
              <td :class="td" class="text-slate-500">{{ fmtTime(u.last_login) }}</td>
              <td :class="td">{{ u.active ? 'aktiv' : 'gesperrt' }}</td>
              <td :class="td" class="text-right whitespace-nowrap">
                <button :class="btnLink" @click="openUser(u)">Bearbeiten</button>
                <button v-if="u.source !== 'ldap' && !u.limited" :class="btnLink" class="ml-3" @click="openReset(u)">Passwort</button>
                <button v-if="!u.limited" :class="btnLink" class="ml-3" @click="revoke(u)">Sitzungen beenden</button>
                <button v-if="!u.limited" :class="btnDanger" class="ml-3" @click="removeUser(u)">Löschen</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- API-Zugänge -->
    <div v-if="tab === 'tokens'" class="space-y-3">
      <div class="text-right"><button :class="btnPrimary" @click="openToken">+ API-Zugang</button></div>
      <div v-if="newToken" class="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-3 text-sm">
        <p class="font-medium text-amber-800 dark:text-amber-300">Token „{{ newToken.name }}“ – wird nur jetzt angezeigt. Jetzt kopieren und sicher ablegen:</p>
        <code class="block mt-2 p-2 rounded bg-white dark:bg-slate-900 break-all select-all text-xs">{{ newToken.token }}</code>
        <button :class="btnLink" class="mt-2" @click="newToken = null">Ausblenden</button>
      </div>
      <div :class="card" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Name</th><th :class="th">Präfix</th><th :class="th">Umfang</th><th :class="th">Erstellt</th><th :class="th">Läuft ab</th><th :class="th">Zuletzt benutzt</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-if="!tokens.length"><td colspan="7" class="px-3 py-6 text-center text-slate-400">Noch keine API-Zugänge.</td></tr>
            <tr v-for="t in tokens" :key="t.id" class="border-t border-slate-100 dark:border-slate-700" :class="t.revoked ? 'opacity-50' : ''">
              <td :class="td">{{ t.name }}</td><td :class="td" class="font-mono text-xs">{{ t.prefix }}…</td><td :class="td">{{ t.scope }}</td>
              <td :class="td" class="text-slate-500">{{ fmtTime(t.created_at) }}</td><td :class="td" class="text-slate-500">{{ t.expires_at ? fmtTime(t.expires_at) : 'nie' }}</td>
              <td :class="td" class="text-slate-500">{{ fmtTime(t.last_used_at) }}</td>
              <td :class="td" class="text-right"><span v-if="t.revoked" class="text-xs text-slate-400">widerrufen</span><button v-else :class="btnDanger" @click="revokeToken(t)">Widerrufen</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Audit -->
    <div v-if="tab === 'audit'" class="space-y-3">
      <form :class="card" class="p-3 flex flex-wrap gap-2 items-end" @submit.prevent="loadAudit()">
        <div class="grow min-w-56"><label :class="lbl">Suche</label><input v-model="af.q" :class="inp" placeholder="Benutzer, Aktion, Objekt oder Detail …" /></div>
        <div><label :class="lbl">Benutzer</label>
          <select v-model="af.actor" :class="inp"><option value="">alle</option><option v-for="a in auditFacets.actors" :key="a" :value="a">{{ a }}</option></select></div>
        <div><label :class="lbl">Aktion</label>
          <select v-model="af.action" :class="inp"><option value="">alle</option>
            <optgroup label="Bereich"><option v-for="g in auditGroups" :key="g" :value="g">{{ g }}.*</option></optgroup>
            <optgroup label="Aktion"><option v-for="a in auditFacets.actions" :key="a" :value="a">{{ a }}</option></optgroup></select></div>
        <div><label :class="lbl">Objekt</label>
          <select v-model="af.entity" :class="inp"><option value="">alle</option><option v-for="e in auditFacets.entities" :key="e" :value="e">{{ e }}</option></select></div>
        <div><label :class="lbl">Von</label><input v-model="af.date_from" type="date" :class="inp" /></div>
        <div><label :class="lbl">Bis</label><input v-model="af.date_to" type="date" :class="inp" /></div>
        <button type="submit" :class="btnPrimary">Suchen</button>
        <button type="button" :class="btnGhost" @click="resetAudit">Zurücksetzen</button>
      </form>
      <p class="text-xs text-slate-400">{{ audit.length }} Einträge{{ auditFiltered ? ' (gefiltert)' : '' }}{{ auditMore ? ' – weitere vorhanden' : '' }}</p>
      <div :class="card" class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Zeit</th><th :class="th">Benutzer</th><th :class="th">Aktion</th><th :class="th">Objekt</th><th :class="th">Detail</th></tr></thead>
          <tbody>
            <tr v-if="!audit.length"><td colspan="5" class="px-3 py-6 text-center text-slate-400">Keine Einträge{{ auditFiltered ? ' für diese Suche' : '' }}.</td></tr>
            <tr v-for="a in audit" :key="a.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="whitespace-nowrap">{{ fmtTime(a.ts) }}</td><td :class="td">{{ a.actor }}</td><td :class="td" class="font-mono">{{ a.action }}</td>
              <td :class="td">{{ a.entity }} {{ a.entity_id }}</td><td :class="td" class="text-slate-500">{{ a.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="auditMore" class="text-center"><button type="button" :class="btnGhost" @click="loadAudit(true)">Mehr laden</button></div>
    </div>

    <ModalDialog v-if="userForm" :title="userForm.id ? `Benutzer ${userForm.username}` : 'Neuer Benutzer'" :error="formError" @close="userForm = null">
      <div v-if="!userForm.id"><label :class="lbl">Benutzername</label><input v-model="userForm.username" :class="inp" /></div>
      <div v-if="!userForm.id"><label :class="lbl">Passwort</label><input v-model="userForm.password" type="password" autocomplete="new-password" :class="inp" /></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Name</label><input v-model="userForm.full_name" :class="inp" /></div>
        <div><label :class="lbl">E-Mail</label><input v-model="userForm.email" :class="inp" /></div>
      </div>
      <div v-if="globalAdmin"><label :class="lbl">Globale Rollen <span class="normal-case text-slate-300">– gelten für alle Standorte, Benutzer sehen alles</span></label>
        <label v-for="[k, l, desc] in ROLES" :key="k" class="flex items-center gap-2 text-sm py-0.5 text-slate-700 dark:text-slate-200">
          <input type="checkbox" :value="k" v-model="userForm.roles" class="rounded text-ks-600" /> {{ l }} <span class="text-xs text-slate-400">– {{ desc }}</span></label></div>
      <div>
        <div class="flex items-center justify-between"><label :class="lbl" class="!mb-0">Rechte pro Standort <span class="normal-case text-slate-300">– Benutzer ohne globale Rolle sehen nur diese Standorte</span></label>
          <button type="button" :class="btnLink" @click="addScope">+ Standort-Recht</button></div>
        <p v-if="!userForm.scopes.length && !userForm.ldapScopes.length" class="text-xs text-slate-400 mt-1">Keine Standort-Rechte.</p>
        <div v-for="(sc, i) in userForm.scopes" :key="i" class="flex gap-2 mt-1.5 items-center">
          <select v-model="sc.role" :class="inp" class="!w-44"><option v-for="[k, l] in ROLES" :key="k" :value="k">{{ l }}</option></select>
          <label v-if="globalAdmin" class="flex items-center gap-1.5 text-xs whitespace-nowrap text-slate-600 dark:text-slate-300" title="Rolle gilt für alle Standorte (wird als globale Rolle gespeichert)"><input type="checkbox" v-model="sc.all" class="rounded text-ks-600" /> alle Standorte</label>
          <select v-model="sc.site_id" :class="inp" :disabled="sc.all"><option :value="null" disabled>Standort wählen …</option><option v-for="s in siteChoices()" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option></select>
          <button type="button" :class="btnDanger" @click="userForm.scopes.splice(i, 1)">✕</button>
        </div>
        <p v-if="userForm.ldapScopes.length" class="text-xs text-slate-400 mt-2">Aus AD-Gruppen (nicht änderbar): {{ userForm.ldapScopes.map(scopeText).join(', ') }}</p>
        <p v-if="!globalAdmin" class="text-xs text-slate-400 mt-1">Du kannst Rechte nur für Standorte vergeben, für die du Administrator bist.</p>
      </div>
      <p v-if="userForm.source === 'ldap'" class="text-xs text-slate-400">AD-Konto: Sind unter AD / LDAP Gruppen zugeordnet, werden die Rollen bei jeder Anmeldung aus dem Verzeichnis gesetzt; ohne Gruppen-Zuordnung bleiben die hier vergebenen Rollen bestehen.</p>
      <label v-if="userForm.id && !userForm.limited" class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="userForm.active" class="rounded text-ks-600" /> Konto aktiv</label>
      <p v-if="userForm.id && userForm.limited" class="text-xs text-slate-400">Dieser Benutzer gehört auch zu anderen Bereichen: Du siehst und änderst nur die Rechte deiner Standorte.</p>
      <template #footer>
        <button @click="userForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveUser" :class="btnPrimary" :disabled="!canSave">Speichern</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="resetForm" :title="`Neues Passwort für ${resetForm.username}`" :error="formError" @close="resetForm = null">
      <div><label :class="lbl">Neues Passwort</label><input v-model="resetForm.pw" type="password" autocomplete="new-password" :class="inp" /></div>
      <p class="text-xs text-slate-400">Alle Sitzungen des Benutzers werden beendet.</p>
      <template #footer>
        <button @click="resetForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveReset" :class="btnPrimary" :disabled="!resetForm.pw">Setzen</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="tokenForm" title="Neuer API-Zugang" :error="formError" @close="tokenForm = null">
      <div><label :class="lbl">Name</label><input v-model="tokenForm.name" :class="inp" placeholder="z. B. checkmk-export" /></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Umfang</label><select v-model="tokenForm.scope" :class="inp"><option value="read">read – nur lesen</option><option value="write">write – lesen und schreiben</option></select></div>
        <div><label :class="lbl">Gültig (Tage)</label><input v-model.number="tokenForm.expires_days" type="number" min="1" :class="inp" placeholder="unbegrenzt" /></div>
      </div>
      <template #footer>
        <button @click="tokenForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveToken" :class="btnPrimary" :disabled="!tokenForm.name">Erstellen</button>
      </template>
    </ModalDialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ModalDialog from '../components/ModalDialog.vue'
import AdminLdap from '../components/AdminLdap.vue'
import AdminTls from '../components/AdminTls.vue'
import AdminBackup from '../components/AdminBackup.vue'
import AdminMail from '../components/AdminMail.vue'
import AdminCheckmk from '../components/AdminCheckmk.vue'
import AdminOpenPlan from '../components/AdminOpenPlan.vue'
import { helpContext } from '../content/helpContext.js'
import { api, errText, isAdmin, siteAdminIds } from '../api.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnDanger, btnLink, ROLES, roleLabel, fmtTime } from '../ui.js'

const globalAdmin = isAdmin()
const tabs = globalAdmin ? [['users', 'Benutzer'], ['tokens', 'API-Zugänge'], ['ldap', 'AD / LDAP'], ['tls', 'Zertifikat (ACME)'], ['backup', 'Sicherung'], ['mail', 'E-Mail'], ['checkmk', 'Checkmk'], ['openplan', 'OpenPlan'], ['audit', 'Audit-Log']] : [['users', 'Benutzer']]
const sites = ref([])
const siteChoices = () => globalAdmin ? sites.value : sites.value.filter(s => siteAdminIds().includes(s.id))
const scopeText = s => `${roleLabel(s.role)} @ ${s.site_code}`
const tab = ref('users')
const users = ref([]), tokens = ref([]), audit = ref([])
const AUDIT_PAGE = 200
const emptyFilter = () => ({ q: '', actor: '', action: '', entity: '', date_from: '', date_to: '' })
const af = ref(emptyFilter())
const auditFacets = ref({ actors: [], actions: [], entities: [] })
const auditMore = ref(false)
const auditFiltered = computed(() => Object.values(af.value).some(v => v))
const auditGroups = computed(() => [...new Set(auditFacets.value.actions.filter(a => a.includes('.')).map(a => a.split('.')[0]))])
async function loadAudit(append = false) {
  error.value = ''
  try {
    const params = { limit: AUDIT_PAGE, offset: append === true ? audit.value.length : 0 }
    for (const [k, v] of Object.entries(af.value)) if (v) params[k] = v
    const rows = await api.audit(params)
    audit.value = append === true ? [...audit.value, ...rows] : rows
    auditMore.value = rows.length === AUDIT_PAGE
  } catch (e) { error.value = errText(e) }
}
function resetAudit() { af.value = emptyFilter(); loadAudit() }
let auditTimer = null
watch(af, () => { clearTimeout(auditTimer); auditTimer = setTimeout(() => { if (tab.value === 'audit') loadAudit() }, 400) }, { deep: true })
const error = ref(''), formError = ref('')
const userForm = ref(null), resetForm = ref(null), tokenForm = ref(null), newToken = ref(null)

async function load() {
  error.value = ''
  try {
    if (tab.value === 'users') { users.value = await api.users(); sites.value = await api.sites() }
    else if (tab.value === 'tokens') tokens.value = await api.tokens()
    else if (tab.value === 'audit') { auditFacets.value = await api.auditFacets(); await loadAudit() }
  } catch (e) { error.value = errText(e) }
}
watch(tab, t => { helpContext.value = t; load() }, { immediate: true })

function openUser(u) {
  formError.value = ''
  userForm.value = u
    ? { ...u, roles: [...u.roles], scopes: u.scopes.filter(s => s.source === 'manual').map(s => ({ role: s.role, site_id: s.site_id, all: false })), ldapScopes: u.scopes.filter(s => s.source === 'ldap') }
    : { username: '', password: '', full_name: '', email: '', roles: globalAdmin ? ['viewer'] : [], scopes: [], ldapScopes: [] }
}
function addScope() { userForm.value.scopes.push({ role: 'viewer', site_id: null, all: false }) }
const canSave = computed(() => {
  const f = userForm.value
  if (!f) return false
  const scopes = f.scopes.filter(s => s.site_id || s.all)
  if (f.scopes.length !== scopes.length) return false                                   // unvollständige Zeile
  if (!f.id && (!f.username || !f.password)) return false
  return f.roles.length > 0 || scopes.length > 0 || f.ldapScopes.length > 0 || (f.id && f.source === 'ldap')
})
async function saveUser() {
  try {
    const f = userForm.value
    const allRoles = f.scopes.filter(s => s.all).map(s => s.role)                       // „alle Standorte“ = globale Rolle
    const roles = globalAdmin ? [...new Set([...f.roles, ...allRoles])] : f.roles
    const body = { roles: globalAdmin ? roles : undefined, scopes: f.scopes.filter(s => s.site_id && !s.all).map(s => ({ role: s.role, site_id: s.site_id })), full_name: f.full_name, email: f.email }
    f.id ? await api.updateUser(f.id, { ...body, active: f.limited ? undefined : f.active }) : await api.createUser({ ...body, roles: globalAdmin ? roles : [], username: f.username, password: f.password })
    userForm.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}
function openReset(u) { formError.value = ''; resetForm.value = { id: u.id, username: u.username, pw: '' } }
async function saveReset() {
  try { await api.resetPassword(resetForm.value.id, resetForm.value.pw); resetForm.value = null } catch (e) { formError.value = errText(e) }
}
async function revoke(u) {
  if (!confirm(`Alle Sitzungen von ${u.username} beenden?`)) return
  try { await api.revokeSessions(u.id) } catch (e) { error.value = errText(e) }
}
async function removeUser(u) {
  if (!confirm(`Benutzer ${u.username} löschen?`)) return
  try { await api.deleteUser(u.id); await load() } catch (e) { error.value = errText(e) }
}

function openToken() { formError.value = ''; tokenForm.value = { name: '', scope: 'read', expires_days: null } }
async function saveToken() {
  try {
    newToken.value = await api.createToken({ ...tokenForm.value, expires_days: tokenForm.value.expires_days || null })
    tokenForm.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}
async function revokeToken(t) {
  if (!confirm(`API-Zugang „${t.name}“ widerrufen?`)) return
  try { await api.revokeToken(t.id); await load() } catch (e) { error.value = errText(e) }
}
</script>
