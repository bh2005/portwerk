<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Mitarbeiter melden sich mit ihrem Windows-Benutzernamen und -Passwort an. Das Konto entsteht beim ersten Login; Name, E-Mail und Rollen
      werden bei jeder Anmeldung aus dem Verzeichnis übernommen. Lokale Konten (auch der Start-Admin) bleiben immer als Notzugang erhalten.
      <span v-if="!meta.from_db">Es sind noch keine Werte gespeichert – die AD-Anmeldung ist aus.</span>
    </p>
    <label class="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.enabled" /> Anmeldung über Active Directory aktivieren</label>

    <fieldset :class="box">
      <legend :class="legend">Server</legend>
      <div><label :class="lbl">LDAP-URL</label><input v-model="f.url" :class="inp" placeholder="ldaps://dc01.example.test:636 ldaps://dc02.example.test:636" />
        <p :class="hint">Mehrere Server mit Leerzeichen oder Komma trennen: Der nächste wird nur bei Verbindungsproblemen versucht (nie bei falschem Passwort).</p></div>
      <p v-if="unencrypted" class="text-xs text-amber-600 dark:text-amber-400">⚠ ldap:// überträgt Passwörter unverschlüsselt – bitte ldaps:// verwenden.</p>
      <div><label :class="lbl">Base-DN</label><input v-model="f.base_dn" :class="inp" placeholder="DC=example,DC=test" /></div>
      <div><label :class="lbl">CA-Zertifikat für LDAPS (PEM, optional)</label>
        <textarea v-model="f.ca_pem" rows="4" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="-----BEGIN CERTIFICATE-----&#10;…&#10;-----END CERTIFICATE-----" />
        <p :class="hint">Nötig, wenn die Domänencontroller ein Zertifikat einer internen CA nutzen (Root + Intermediate hintereinander einfügen).</p></div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Anmeldung prüfen</legend>
      <p :class="hint">Entweder direkt als <code>benutzer@domain</code> binden (Domain eintragen) oder über einen Service-Account den Benutzer suchen.</p>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">Domain (UPN-Suffix)</label><input v-model="f.domain" :class="inp" placeholder="example.test" /></div>
        <div><label :class="lbl">Benutzerfilter</label><input v-model="f.user_filter" :class="inp" /><p :class="hint">{username} wird durch den Anmeldenamen ersetzt.</p></div>
        <div><label :class="lbl">Service-Account (Bind-DN, optional)</label><input v-model="f.bind_dn" :class="inp" autocomplete="off" placeholder="CN=svc-opp,OU=Service,DC=example,DC=test" /></div>
        <div><label :class="lbl">Service-Account-Passwort</label>
          <input v-model="f.bind_password" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.bind_password_set ? '●●●●●● gespeichert – leer lassen zum Beibehalten' : ''" />
          <label v-if="meta.bind_password_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_bind_password" /> gespeichertes Passwort entfernen</label></div>
      </div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Berechtigung und Rollen</legend>
      <div><label :class="lbl">Pflichtgruppe (DN, optional)</label><input v-model="f.required_group" :class="inp" placeholder="CN=OPP-Users,OU=Groups,DC=example,DC=test" />
        <p :class="hint">Nur Mitglieder dürfen sich anmelden. Leer = jeder Benutzer im Verzeichnis.</p></div>
      <p :class="hint">Je Rolle eine AD-Gruppe (DN). Ein Benutzer erhält alle Rollen, deren Gruppe er angehört; die Rollen werden bei jeder Anmeldung abgeglichen.</p>
      <div class="grid sm:grid-cols-2 gap-3">
        <div v-for="[k, l, d] in ROLES" :key="k"><label :class="lbl">{{ $t(l) }} <span class="normal-case text-slate-300">– {{ $t(d) }}</span></label>
          <input v-model="f.group_roles[k]" :class="inp" :placeholder="`CN=OPP-${l},OU=Groups,DC=example,DC=test`" /></div>
      </div>
      <div>
        <div class="flex items-center justify-between"><label :class="lbl" class="!mb-0">Rechte nur für einen Standort (Gruppe → Rolle @ Standort)</label>
          <button type="button" class="text-xs text-ks-600 dark:text-ks-400 hover:underline" @click="f.scoped_groups.push({ group: '', role: 'viewer', site_id: null })">+ Zuordnung</button></div>
        <p :class="hint">Mitglieder der Gruppe erhalten die Rolle nur für diesen Standort und sehen auch nur ihn. Wer nur solche Gruppen hat, bekommt keine globale Rolle (auch nicht die „Rolle ohne passende Gruppe“).</p>
        <div v-for="(x, i) in f.scoped_groups" :key="i" class="grid grid-cols-12 gap-2 mt-1.5">
          <input v-model="x.group" :class="inp" class="col-span-6" placeholder="CN=Standort-A-Admins,OU=Groups,DC=example,DC=test" />
          <select v-model="x.role" :class="inp" class="col-span-2"><option v-for="[k, l] in ROLES" :key="k" :value="k">{{ $t(l) }}</option></select>
          <select v-model="x.site_id" :class="inp" class="col-span-3"><option :value="null" disabled>Standort …</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }}</option></select>
          <button type="button" class="col-span-1 text-xs text-red-500 hover:text-red-700 dark:text-red-400" @click="f.scoped_groups.splice(i, 1)">✕</button>
        </div>
      </div>
      <p class="text-xs text-slate-400">Sind oben Gruppen zugeordnet, werden die Rollen bei <b>jeder Anmeldung</b> aus dem Verzeichnis übernommen (manuelle Änderungen an AD-Konten werden dann überschrieben). Ohne Gruppen-Zuordnung liefert das Verzeichnis nur die Anmeldung: neue Konten bekommen die Rolle unten, danach pflegt der Administrator die Rollen unter Benutzer.</p>
      <div class="grid sm:grid-cols-2 gap-3 items-end">
        <div><label :class="lbl">Rolle ohne passende Gruppe</label>
          <select v-model="f.default_role" :class="inp"><option value="">keine – Konto ohne Rechte, Hinweis zur Freischaltung</option>
            <option v-for="[k, l] in ROLES.filter(r => r[0] !== 'admin')" :key="k" :value="k">{{ $t(l) }}</option></select></div>
        <div class="space-y-1">
          <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="f.auto_create" /> Konto beim ersten Login automatisch anlegen</label>
          <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="f.nested_groups" /> verschachtelte Gruppen auflösen (AD)</label>
        </div>
      </div>
    </fieldset>

    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">Speichern</button>
      <span v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</span><span v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</span>
    </div>

    <fieldset :class="box">
      <legend :class="legend">Verbindung testen</legend>
      <p :class="hint">Testet mit den Werten oben (auch ungespeichert). Ohne Benutzer wird nur der Service-Account geprüft; mit Benutzer der komplette Ablauf inklusive Gruppen und Rollen.
        Die angezeigten Gruppen-DNs lassen sich direkt oben eintragen.</p>
      <div class="flex gap-3 flex-wrap items-end">
        <input v-model="t.username" :class="inp" class="!w-48" placeholder="Test-Benutzer (optional)" autocomplete="off" />
        <input v-model="t.password" type="password" :class="inp" class="!w-48" placeholder="Passwort" autocomplete="new-password" />
        <button type="button" :class="btnGhost" :disabled="busy" @click="test">Testen</button>
      </div>
      <ul v-if="result" class="text-sm space-y-0.5 mt-2">
        <li v-for="(s, i) in result.steps" :key="i" :class="s.ok ? 'text-green-600' : 'text-red-500'"><b>{{ s.ok ? '✓' : '✗' }} {{ s.step }}</b><span v-if="s.detail" class="text-slate-500 dark:text-slate-400 break-all"> – {{ s.detail }}</span></li>
        <li :class="result.ok ? 'text-green-600' : 'text-red-500'" class="font-semibold">{{ result.ok ? 'Test erfolgreich' : 'Test fehlgeschlagen' }}</li>
      </ul>
    </fieldset>
  </form>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost, ROLES } from '../ui.js'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3'
const legend = 'px-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-400 mt-1'

const f = reactive({
  enabled: false, url: '', base_dn: '', domain: '', bind_dn: '', bind_password: '', clear_bind_password: false,
  user_filter: '(&(objectClass=user)(sAMAccountName={username}))', ca_pem: '', required_group: '',
  group_roles: Object.fromEntries(ROLES.map(r => [r[0], ''])), scoped_groups: [], default_role: '', auto_create: true, nested_groups: true,
})
const meta = reactive({ bind_password_set: false, from_db: false })
const t = reactive({ username: '', password: '' })
const result = ref(null), busy = ref(false), msg = ref(''), err = ref('')
const sites = ref([])
const unencrypted = computed(() => /(^|[\s,;])ldap:\/\//i.test(f.url))

function fill(s) {
  const { bind_password_set, from_db, ...rest } = s
  Object.assign(f, rest, { bind_password: '', clear_bind_password: false, group_roles: { ...f.group_roles, ...(rest.group_roles || {}) } })
  Object.assign(meta, { bind_password_set, from_db })
}
const payload = () => ({ ...f, bind_password: f.bind_password || undefined, scoped_groups: f.scoped_groups.filter(x => x.group.trim() && x.site_id) })

onMounted(async () => { try { sites.value = await api.sites(); fill(await api.ldapSettings()) } catch (e) { err.value = errText(e) } })

async function save() {
  busy.value = true; msg.value = err.value = ''
  try { fill(await api.saveLdapSettings(payload())); msg.value = 'Gespeichert' }
  catch (e) { err.value = errText(e) }
  finally { busy.value = false }
}
async function test() {
  busy.value = true; result.value = null; err.value = ''
  try { result.value = await api.testLdap(payload(), t.username, t.password) }
  catch (e) { err.value = errText(e) }
  finally { busy.value = false }
}
</script>
