<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">{{ $t('Verbindet Portwerk mit') + ' ' }}<b>{{ $t('OpenPlan') }}</b>{{ ' ' + $t('(Projektplanung): Für Patchaufträge entstehen Vorgänge im Projektplan, Status und Fortschritt werden automatisch abgeglichen, und Projekte lassen sich aus der Vorlage „Einbau Patchfelder / Verkabelung“ anlegen. Standardmäßig') + ' ' }}<b>{{ $t('aus') }}</b>.
      <span v-if="!meta.configured">{{ $t('Noch nichts eingerichtet.') }}</span></p>
    <label class="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.enabled" />{{ ' ' + $t('OpenPlan-Anbindung aktivieren') }}</label>

    <fieldset :class="box">
      <legend :class="legend">{{ $t('Zugang zu OpenPlan') }}</legend>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('OpenPlan-Adresse (für die API)') }}</label><input v-model="f.base_url" :class="inp" :placeholder="$t('https://openplan.example.test')" /></div>
        <div><label :class="lbl">{{ $t('OpenPlan-Adresse für Links (Browser, optional)') }}</label><input v-model="f.link_url" :class="inp" :placeholder="$t('leer = wie API-Adresse')" />
          <p :class="hint">{{ $t('Nur nötig, wenn Portwerk OpenPlan unter einer anderen Adresse erreicht als die Benutzer – z. B. im Docker-Netz') + ' ' }}<code>{{ $t('http://openplan:8080') }}</code>{{ $t(', im Browser') + ' ' }}<code>{{ $t('https://openplan.example.test') }}</code>.</p></div>
        <div><label :class="lbl">{{ $t('API-Token (Dienstkonto)') }}</label><input v-model="f.token" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.token_set ? $t('●●●●●● gespeichert – leer lassen zum Beibehalten') : 'op_…'" />
          <label v-if="meta.token_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_token" />{{ ' ' + $t('gespeichertes Token entfernen') }}</label></div>
        <div><label :class="lbl">{{ $t('Standard-Projekt (ID, optional)') }}</label><input v-model="f.default_project_id" :class="inp" placeholder="z. B. 7" /></div>
        <div class="flex items-end gap-5 text-sm text-slate-600 dark:text-slate-300 pb-2">
          <label class="flex items-center gap-2"><input type="checkbox" v-model="f.auto_sync" />{{ ' ' + $t('automatisch abgleichen') }}</label>
          <label class="flex items-center gap-2"><input type="checkbox" v-model="f.verify_tls" />{{ ' ' + $t('TLS-Zertifikat prüfen') }}</label></div>
      </div>
      <p :class="hint">{{ $t('In OpenPlan unter') + ' ' }}<i>{{ $t('Verwaltung → API-Zugänge') }}</i>{{ ' ' + $t('ein Dienstkonto mit Umfang') + ' ' }}<b>{{ $t('write') }}</b>{{ ' ' + $t('und Rolle') + ' ' }}<b>{{ $t('Bearbeiter') }}</b>{{ ' ' + $t('anlegen; das Konto muss im Projekt als') + ' ' }}<b>{{ $t('Mitglied (Bearbeiter)') }}</b>{{ ' ' + $t('eingetragen sein. Neue Projekte aus der Vorlage legt das Dienstkonto an (es darf dazu nicht auf einzelne Projekte beschränkt sein).') }}</p>
      <div><label :class="lbl">{{ $t('CA-Zertifikat von OpenPlan (PEM, optional)') }}</label>
        <textarea v-model="f.ca_pem" rows="3" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="-----BEGIN CERTIFICATE-----&#10;…&#10;-----END CERTIFICATE-----"></textarea></div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">{{ $t('Abwesenheiten aus OpenPlan (optional)') }}</legend>
      <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.sync_absences" />{{ ' ' + $t('Abwesenheiten übernehmen (stündlich)') }}</label>
      <p :class="hint">{{ $t('Urlaub, Schulung usw. aus „Mein Profil“ in OpenPlan gelten dann auch in Portwerk: Benachrichtigungen gehen an die') + ' ' }}<b>{{ $t('Standard-Vertretung') }}</b>{{ $t(', die jeder im Profil festlegt. Zuordnung über den Benutzernamen, sonst über die E-Mail-Adresse. Übernommen wird ein Jahr im Voraus; „krank“ erscheint nur als „abwesend“, Notizen nicht. In OpenPlan braucht der API-Zugang die Freigabe') + ' ' }}<b>{{ $t('„Abwesenheiten“') }}</b>{{ ' ' + $t('(Verwaltung → API-Zugänge). Ausschalten entfernt die übernommenen Einträge.') }}</p>
      <div class="flex items-center gap-3 flex-wrap text-sm">
        <button type="button" :class="btnGhost" class="!py-1.5" :disabled="busy || !meta.configured" @click="syncAbsences">{{ $t('jetzt abgleichen') }}</button>
        <span v-if="abs.at" :class="abs.ok ? 'text-slate-600 dark:text-slate-300' : 'text-red-500 dark:text-red-400'">
          {{ $t('Letzter Abgleich {t}:', { t: fmtTime(abs.at) }) }}
          <template v-if="abs.ok">{{ $t('{a} Abwesenheit(en) für {b} Benutzer übernommen', { a: abs.imported, b: abs.users }) }}</template><template v-else>{{ $tApi(abs.error) }}</template></span>
      </div>
      <p v-if="abs.ok && abs.unmatched?.length" class="text-xs text-amber-700 dark:text-amber-300">{{ $t('Ohne passenden Benutzer in Portwerk:') }} {{ abs.unmatched.join(', ') }}</p>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">{{ $t('Rückrichtung (optional): Webhook von OpenPlan') }}</legend>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Adresse dieser Anwendung (für Links in OpenPlan)') }}</label><input v-model="f.own_url" :class="inp" :placeholder="$t('https://opp.example.test')" />
          <p :class="hint">{{ $t('Leer = öffentliche URL aus den E-Mail-Einstellungen. Den Webhook in OpenPlan auf die Adresse richten, unter der') + ' ' }}<i>{{ $t('OpenPlan') }}</i>{{ ' ' + $t('Portwerk erreicht (im Docker-Netz z. B.') + ' ' }}<code>{{ $t('http://portwerk:8084/api/integrations/openplan/webhook') }}</code>).</p></div>
        <div><label :class="lbl">{{ $t('Webhook-Geheimnis') }}</label><input v-model="f.webhook_secret" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.webhook_secret_set ? $t('●●●●●● gespeichert') : 'whsec_…'" />
          <label v-if="meta.webhook_secret_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_webhook_secret" />{{ ' ' + $t('entfernen') }}</label></div>
      </div>
      <p :class="hint">{{ $t('In OpenPlan unter') + ' ' }}<i>{{ $t('Verwaltung → Webhooks') }}</i>{{ ' ' + $t('einen Webhook auf') + ' ' }}<code class="break-all">{{ meta.webhook_url || '<Adresse>/api/integrations/openplan/webhook' }}</code>{{ ' ' + $t('anlegen (Ereignis') + ' ' }}<code>{{ $t('task.status') }}</code>{{ $t(') und das angezeigte Geheimnis (') }}<code>{{ $t('whsec_…') }}</code>{{ $t(') hier eintragen. Dann zeigt der Patchauftrag den Status der OpenPlan-Aufgabe auch dann, wenn dort etwas geändert wurde. OpenPlan verlangt für Webhooks') + ' ' }}<code>{{ $t('https://') }}</code>.</p>
    </fieldset>

    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">{{ $t('Speichern') }}</button>
      <button type="button" :class="btnGhost" :disabled="busy" @click="test">{{ $t('Verbindung testen') }}</button>
      <span v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</span><span v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</span>
    </div>
    <div v-if="result" class="rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 p-3 text-sm space-y-1">
      <p class="text-green-700 dark:text-green-300">{{ $t('✓ Verbunden als') + ' ' }}<b>{{ result.account }}</b> ({{ result.role }}) – {{ $t('{n} Projekt(e) sichtbar:', { n: result.projects.length }) }}</p>
      <ul class="text-xs text-slate-600 dark:text-slate-300 list-disc pl-5"><li v-for="p in result.projects.slice(0, 12)" :key="p.id">{{ p.name }} <span class="text-slate-400">(ID {{ p.id }}, {{ p.access }})</span></li></ul>
      <p v-if="!result.projects.length" class="text-amber-600 dark:text-amber-400">{{ $t('Das Dienstkonto sieht noch kein Projekt – bitte in OpenPlan als Mitglied eintragen.') }}</p>
    </div>
  </form>
</template>

<script setup>
import { t } from '../i18n.js'
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost, fmtTime } from '../ui.js'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3'
const legend = 'px-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-400 mt-1'

const f = reactive({ enabled: false, base_url: '', link_url: '', token: '', clear_token: false, default_project_id: '', ca_pem: '', verify_tls: true, auto_sync: true, sync_absences: false, own_url: '', webhook_secret: '', clear_webhook_secret: false })
const meta = reactive({ token_set: false, webhook_secret_set: false, webhook_url: '', configured: false })
const busy = ref(false), msg = ref(''), err = ref(''), result = ref(null), abs = ref({})

function fill(s) {
  const { token_set, webhook_secret_set, webhook_url, account, absences_status, ...rest } = s
  abs.value = absences_status || {}
  Object.assign(f, rest, { token: '', webhook_secret: '', clear_token: false, clear_webhook_secret: false })
  Object.assign(meta, { token_set, webhook_secret_set, webhook_url, configured: !!(rest.base_url || rest.enabled) })
}
const payload = () => ({ ...f, token: f.token || undefined, webhook_secret: f.webhook_secret || undefined })
onMounted(async () => { try { fill(await api.openplanSettings()) } catch (e) { err.value = errText(e) } })

async function save() {
  busy.value = true; msg.value = err.value = ''
  try { fill(await api.saveOpenplanSettings(payload())); msg.value = t('Gespeichert') } catch (e) { err.value = errText(e) } finally { busy.value = false }
}
async function syncAbsences() {
  busy.value = true; msg.value = err.value = ''
  try { abs.value = await api.syncOpenplanAbsences(); msg.value = t('Abwesenheiten abgeglichen') }
  catch (e) { err.value = errText(e); try { abs.value = (await api.openplanSettings()).absences_status || {} } catch { /* bleibt */ } }
  finally { busy.value = false }
}
async function test() {
  busy.value = true; result.value = null; err.value = ''
  try { result.value = await api.testOpenplan() } catch (e) { err.value = errText(e) + ' (' + t('Einstellungen zuerst speichern') + ')' } finally { busy.value = false }
}
</script>
