<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">{{ $t('Mit der Adresse Ihrer Checkmk-Site erscheint bei Geräten (Racks, Gerätedetails) ein Link') }}
      <b>{{ $t('„In Checkmk öffnen“') }}</b>{{ $t(', der direkt die Host-Seite öffnet. Leer = kein Link.') }}</p>
    <div class="max-w-xl space-y-3">
      <div><label :class="lbl">{{ $t('Adresse der Checkmk-Site') }}</label>
        <input v-model="f.base_url" :class="inp" :placeholder="$t('https://monitoring.example.test/prod')" />
        <p class="text-xs text-slate-400 mt-1">{{ $t('Mit Site-Namen, ohne Parameter. Der Hostname in Checkmk muss dem Hostnamen hier entsprechen.') }}</p></div>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="f.link_all" />{{ ' ' + $t('Link auch für manuell angelegte Geräte (sonst nur Geräte aus dem Checkmk-Import)') }}</label>
    </div>
    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">{{ $t('Speichern') }}</button>
      <a v-if="f.base_url" :href="f.base_url + '/check_mk/'" target="_blank" rel="noopener" :class="btnLink">{{ $t('Site öffnen ↗') }}</a>
      <span v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</span><span v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</span>
    </div>
    <div class="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700 pt-3 max-w-2xl space-y-1">
      <p><b>{{ $t('Soll/Ist-Abgleich:') }}</b>{{ ' ' + $t('Die LLDP-/CDP-Nachbarn kommen mit dem Checkmk-Import (') }}<code>{{ $t('tools/checkmk_export.py') }}</code>{{ ' ' + $t('auf dem Checkmk-Server; Beschreibung in') + ' ' }}<code>{{ $t('docs/checkmk-import.md') }}</code>{{ $t('). Jeder Import ersetzt die Nachbarn der enthaltenen Geräte. Das Ergebnis steht unter „Soll/Ist“.') }}</p>
    </div>
  </form>

  <form class="space-y-4 mt-6 border-t border-slate-200 dark:border-slate-700 pt-5" @submit.prevent="saveApi">
    <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ $t('REST-API: Hosts prüfen und anlegen') }}</h2>
    <p class="text-sm text-slate-500 dark:text-slate-400">{{ $t('Mit einem Automation-User kann Portwerk prüfen, ob ein Gerät in Checkmk existiert, und es als Host mit reinem Host-Check (Ping) anlegen. Hosts werden nur als') + ' ' }}<b>{{ $t('ausstehende Änderung') }}</b>{{ ' ' + $t('angelegt, die Aktivierung erfolgt in Checkmk. Der User braucht Rechte zum Lesen und Anlegen von Hosts, aber keine zum Aktivieren.') }}</p>
    <div class="max-w-xl space-y-3">
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="a.enabled" />{{ ' ' + $t('Anbindung aktiv') }}</label>
      <div><label :class="lbl">{{ $t('Adresse der Site (API)') }}</label><input v-model="a.api_url" :class="inp" :placeholder="$t('https://checkmk.example.test/site')" />
        <p class="text-xs text-slate-400 mt-1">{{ $t('Ohne') + ' ' }}<code>{{ $t('/check_mk/api') }}</code>{{ $t('. Die Anmeldedaten gehen mit jeder Anfrage mit – nach Möglichkeit https verwenden.') }}</p>
        <p v-if="plainHttp" class="mt-2 text-sm rounded-md px-3 py-2 bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-800">
          ⚠ {{ $t('Unverschlüsselt: Automation-User und Secret gehen bei jeder Anfrage im Klartext über das Netz. Die Checkmk-Site auf HTTPS umstellen und hier https:// eintragen.') }}</p></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Automation-User') }}</label><input v-model="a.user" :class="inp" autocomplete="off" /></div>
        <div><label :class="lbl">{{ $t('Secret') }}</label><input v-model="a.secret" type="password" :class="inp" autocomplete="new-password" :placeholder="a.secret_set ? $t('(gesetzt – leer lassen = unverändert)') : ''" /></div>
      </div>
      <div><label :class="lbl">{{ $t('Standardordner für neue Hosts') }}</label><input v-model="a.default_folder" :class="inp" placeholder="/" />
        <p class="text-xs text-slate-400 mt-1">{{ $t('Pfad wie') + ' ' }}<code>{{ $t('/eu/de_germany') }}</code>{{ $t('; im Dialog beim Anlegen änderbar.') }}</p></div>
      <template v-if="a.api_url.startsWith('https')">
        <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="a.verify_tls" />{{ ' ' + $t('Zertifikat prüfen') }}</label>
        <div><label :class="lbl">{{ $t('CA-Zertifikat (PEM, optional)') }}</label><textarea v-model="a.ca_pem" rows="3" :class="inp" class="font-mono text-xs" :placeholder="$t('-----BEGIN CERTIFICATE-----')"></textarea></div>
      </template>
    </div>
    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busyApi">{{ $t('Speichern') }}</button>
      <button type="button" :class="btnLink" :disabled="busyApi || !a.secret_set" @click="testApi">{{ $t('Verbindung testen') }}</button>
      <span v-if="msgApi" class="text-sm text-green-600 dark:text-green-400">{{ msgApi }}</span><span v-if="errApi" class="text-sm text-red-500 dark:text-red-400">{{ errApi }}</span>
    </div>
    <div v-if="a.enabled && a.secret_set" class="max-w-xl space-y-2">
      <CheckmkActivate />
      <p class="text-xs text-slate-400">{{ $t('Zum Aktivieren aus Portwerk braucht der Automation-User das Recht') + ' ' }}<code>{{ $t('wato.activate') }}</code>{{ ' ' + $t('(nicht') + ' ' }}<code>{{ $t('wato.activateforeign') }}</code>{{ $t('). Fremde Änderungen aktiviert Portwerk nie.') }}</p>
    </div>
  </form>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import CheckmkActivate from './CheckmkActivate.vue'
import { loadCheckmk } from '../checkmk.js'
import { inp, lbl, btnPrimary, btnLink } from '../ui.js'

const f = reactive({ base_url: '', link_all: true })
const busy = ref(false), msg = ref(''), err = ref('')
const a = reactive({ enabled: false, api_url: '', user: '', secret: '', secret_set: false, default_folder: '/', verify_tls: true, ca_pem: '' })
const busyApi = ref(false), msgApi = ref(''), errApi = ref('')
const plainHttp = computed(() => /^\s*http:\/\//i.test(a.api_url))
async function loadApi() { try { Object.assign(a, await api.checkmkApi(), { secret: '' }) } catch (e) { errApi.value = errText(e) } }
async function saveApi() {
  busyApi.value = true; msgApi.value = errApi.value = ''
  try { Object.assign(a, await api.saveCheckmkApi({ enabled: a.enabled, api_url: a.api_url, user: a.user, secret: a.secret || undefined, default_folder: a.default_folder,
    verify_tls: a.verify_tls, ca_pem: a.ca_pem }), { secret: '' }); msgApi.value = t('Gespeichert') }
  catch (e) { errApi.value = errText(e) } finally { busyApi.value = false }
}
async function testApi() {
  busyApi.value = true; msgApi.value = errApi.value = ''
  try { const r = await api.testCheckmkApi(); msgApi.value = t('Verbunden: Checkmk {v}, {n} Ordner sichtbar', { v: r.version + (r.edition ? ' (' + r.edition + ')' : ''), n: r.folders }) + (r.plain_http ? ' – ' + t('unverschlüsselt (http)') : '') }
  catch (e) { errApi.value = errText(e) } finally { busyApi.value = false }
}
onMounted(async () => { loadApi(); try { const c = await api.checkmkLink(); f.base_url = c.base_url; f.link_all = c.link_all } catch (e) { err.value = errText(e) } })
async function save() {
  busy.value = true; msg.value = err.value = ''
  try { await api.saveCheckmkLink({ base_url: f.base_url, link_all: f.link_all }); await loadCheckmk(true); msg.value = t('Gespeichert') }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
</script>
