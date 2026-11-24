<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">Mit der Adresse Ihrer Checkmk-Site erscheint bei Geräten (Racks, Gerätedetails) ein Link
      <b>„In Checkmk öffnen“</b>, der direkt die Host-Seite öffnet. Leer = kein Link.</p>
    <div class="max-w-xl space-y-3">
      <div><label :class="lbl">Adresse der Checkmk-Site</label>
        <input v-model="f.base_url" :class="inp" placeholder="https://monitoring.example.test/prod" />
        <p class="text-xs text-slate-400 mt-1">Mit Site-Namen, ohne Parameter. Der Hostname in Checkmk muss dem Hostnamen hier entsprechen.</p></div>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="f.link_all" /> Link auch für manuell angelegte Geräte (sonst nur Geräte aus dem Checkmk-Import)</label>
    </div>
    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">Speichern</button>
      <a v-if="f.base_url" :href="f.base_url + '/check_mk/'" target="_blank" rel="noopener" :class="btnLink">Site öffnen ↗</a>
      <span v-if="msg" class="text-sm text-green-600">{{ msg }}</span><span v-if="err" class="text-sm text-red-500">{{ err }}</span>
    </div>
    <div class="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700 pt-3 max-w-2xl space-y-1">
      <p><b>Soll/Ist-Abgleich:</b> Die LLDP-/CDP-Nachbarn kommen mit dem Checkmk-Import (<code>tools/checkmk_export.py</code> auf dem Checkmk-Server; Beschreibung in <code>docs/checkmk-import.md</code>).
        Jeder Import ersetzt die Nachbarn der enthaltenen Geräte. Das Ergebnis steht unter „Soll/Ist“.</p>
    </div>
  </form>

  <form class="space-y-4 mt-6 border-t border-slate-200 dark:border-slate-700 pt-5" @submit.prevent="saveApi">
    <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">REST-API: Hosts prüfen und anlegen</h2>
    <p class="text-sm text-slate-500 dark:text-slate-400">Mit einem Automation-User kann Portwerk prüfen, ob ein Gerät in Checkmk existiert, und es als Host mit reinem Host-Check (Ping) anlegen.
      Hosts werden nur als <b>ausstehende Änderung</b> angelegt, die Aktivierung erfolgt in Checkmk. Der User braucht Rechte zum Lesen und Anlegen von Hosts, aber keine zum Aktivieren.</p>
    <div class="max-w-xl space-y-3">
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="a.enabled" /> Anbindung aktiv</label>
      <div><label :class="lbl">Adresse der Site (API)</label><input v-model="a.api_url" :class="inp" placeholder="http://checkmk.example.test/site" />
        <p class="text-xs text-slate-400 mt-1">Ohne <code>/check_mk/api</code>. Die Anmeldedaten gehen mit jeder Anfrage mit – nach Möglichkeit https verwenden.</p></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Automation-User</label><input v-model="a.user" :class="inp" autocomplete="off" /></div>
        <div><label :class="lbl">Secret</label><input v-model="a.secret" type="password" :class="inp" autocomplete="new-password" :placeholder="a.secret_set ? '(gesetzt – leer lassen = unverändert)' : ''" /></div>
      </div>
      <div><label :class="lbl">Standardordner für neue Hosts</label><input v-model="a.default_folder" :class="inp" placeholder="/" />
        <p class="text-xs text-slate-400 mt-1">Pfad wie <code>/eu/de_germany</code>; im Dialog beim Anlegen änderbar.</p></div>
      <template v-if="a.api_url.startsWith('https')">
        <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="a.verify_tls" /> Zertifikat prüfen</label>
        <div><label :class="lbl">CA-Zertifikat (PEM, optional)</label><textarea v-model="a.ca_pem" rows="3" :class="inp" class="font-mono text-xs" placeholder="-----BEGIN CERTIFICATE-----"></textarea></div>
      </template>
    </div>
    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busyApi">Speichern</button>
      <button type="button" :class="btnLink" :disabled="busyApi || !a.secret_set" @click="testApi">Verbindung testen</button>
      <span v-if="msgApi" class="text-sm text-green-600">{{ msgApi }}</span><span v-if="errApi" class="text-sm text-red-500">{{ errApi }}</span>
    </div>
    <div v-if="a.enabled && a.secret_set" class="max-w-xl space-y-2">
      <CheckmkActivate />
      <p class="text-xs text-slate-400">Zum Aktivieren aus Portwerk braucht der Automation-User das Recht <code>wato.activate</code> (nicht <code>wato.activateforeign</code>). Fremde Änderungen aktiviert Portwerk nie.</p>
    </div>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import CheckmkActivate from './CheckmkActivate.vue'
import { loadCheckmk } from '../checkmk.js'
import { inp, lbl, btnPrimary, btnLink } from '../ui.js'

const f = reactive({ base_url: '', link_all: true })
const busy = ref(false), msg = ref(''), err = ref('')
const a = reactive({ enabled: false, api_url: '', user: '', secret: '', secret_set: false, default_folder: '/', verify_tls: true, ca_pem: '' })
const busyApi = ref(false), msgApi = ref(''), errApi = ref('')
async function loadApi() { try { Object.assign(a, await api.checkmkApi(), { secret: '' }) } catch (e) { errApi.value = errText(e) } }
async function saveApi() {
  busyApi.value = true; msgApi.value = errApi.value = ''
  try { Object.assign(a, await api.saveCheckmkApi({ enabled: a.enabled, api_url: a.api_url, user: a.user, secret: a.secret || undefined, default_folder: a.default_folder,
    verify_tls: a.verify_tls, ca_pem: a.ca_pem }), { secret: '' }); msgApi.value = 'Gespeichert' }
  catch (e) { errApi.value = errText(e) } finally { busyApi.value = false }
}
async function testApi() {
  busyApi.value = true; msgApi.value = errApi.value = ''
  try { const r = await api.testCheckmkApi(); msgApi.value = `Verbunden: Checkmk ${r.version}${r.edition ? ' (' + r.edition + ')' : ''}, ${r.folders} Ordner sichtbar` }
  catch (e) { errApi.value = errText(e) } finally { busyApi.value = false }
}
onMounted(async () => { loadApi(); try { const c = await api.checkmkLink(); f.base_url = c.base_url; f.link_all = c.link_all } catch (e) { err.value = errText(e) } })
async function save() {
  busy.value = true; msg.value = err.value = ''
  try { await api.saveCheckmkLink({ base_url: f.base_url, link_all: f.link_all }); await loadCheckmk(true); msg.value = 'Gespeichert' }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
</script>
