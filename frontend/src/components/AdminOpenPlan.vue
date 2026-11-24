<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">Verbindet Portwerk mit <b>OpenPlan</b> (Projektplanung): Für Patchaufträge entstehen Vorgänge im Projektplan, Status und Fortschritt werden automatisch abgeglichen,
      und Projekte lassen sich aus der Vorlage „Einbau Patchfelder / Verkabelung“ anlegen. Standardmäßig <b>aus</b>.
      <span v-if="!meta.configured">Noch nichts eingerichtet.</span></p>
    <label class="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.enabled" /> OpenPlan-Anbindung aktivieren</label>

    <fieldset :class="box">
      <legend :class="legend">Zugang zu OpenPlan</legend>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">OpenPlan-Adresse (für die API)</label><input v-model="f.base_url" :class="inp" placeholder="https://openplan.example.test" /></div>
        <div><label :class="lbl">OpenPlan-Adresse für Links (Browser, optional)</label><input v-model="f.link_url" :class="inp" placeholder="leer = wie API-Adresse" />
          <p :class="hint">Nur nötig, wenn Portwerk OpenPlan unter einer anderen Adresse erreicht als die Benutzer – z. B. im Docker-Netz <code>http://openplan:8080</code>, im Browser <code>https://openplan.example.test</code>.</p></div>
        <div><label :class="lbl">API-Token (Dienstkonto)</label><input v-model="f.token" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.token_set ? '●●●●●● gespeichert – leer lassen zum Beibehalten' : 'op_…'" />
          <label v-if="meta.token_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_token" /> gespeichertes Token entfernen</label></div>
        <div><label :class="lbl">Standard-Projekt (ID, optional)</label><input v-model="f.default_project_id" :class="inp" placeholder="z. B. 7" /></div>
        <div class="flex items-end gap-5 text-sm text-slate-600 dark:text-slate-300 pb-2">
          <label class="flex items-center gap-2"><input type="checkbox" v-model="f.auto_sync" /> automatisch abgleichen</label>
          <label class="flex items-center gap-2"><input type="checkbox" v-model="f.verify_tls" /> TLS-Zertifikat prüfen</label></div>
      </div>
      <p :class="hint">In OpenPlan unter <i>Verwaltung → API-Zugänge</i> ein Dienstkonto mit Umfang <b>write</b> und Rolle <b>Bearbeiter</b> anlegen; das Konto muss im Projekt als <b>Mitglied (Bearbeiter)</b> eingetragen sein. Neue Projekte aus der Vorlage legt das Dienstkonto an (es darf dazu nicht auf einzelne Projekte beschränkt sein).</p>
      <div><label :class="lbl">CA-Zertifikat von OpenPlan (PEM, optional)</label>
        <textarea v-model="f.ca_pem" rows="3" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="-----BEGIN CERTIFICATE-----&#10;…&#10;-----END CERTIFICATE-----"></textarea></div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Rückrichtung (optional): Webhook von OpenPlan</legend>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">Adresse dieser Anwendung (für Links in OpenPlan)</label><input v-model="f.own_url" :class="inp" placeholder="https://opp.example.test" />
          <p :class="hint">Leer = öffentliche URL aus den E-Mail-Einstellungen. Den Webhook in OpenPlan auf die Adresse richten, unter der <i>OpenPlan</i> Portwerk erreicht (im Docker-Netz z. B. <code>http://portwerk:8084/api/integrations/openplan/webhook</code>).</p></div>
        <div><label :class="lbl">Webhook-Geheimnis</label><input v-model="f.webhook_secret" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.webhook_secret_set ? '●●●●●● gespeichert' : 'whsec_…'" />
          <label v-if="meta.webhook_secret_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_webhook_secret" /> entfernen</label></div>
      </div>
      <p :class="hint">In OpenPlan unter <i>Verwaltung → Webhooks</i> einen Webhook auf <code class="break-all">{{ meta.webhook_url || '<Adresse>/api/integrations/openplan/webhook' }}</code> anlegen (Ereignis <code>task.status</code>) und das angezeigte Geheimnis (<code>whsec_…</code>) hier eintragen.
        Dann zeigt der Patchauftrag den Status der OpenPlan-Aufgabe auch dann, wenn dort etwas geändert wurde. OpenPlan verlangt für Webhooks <code>https://</code>.</p>
    </fieldset>

    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">Speichern</button>
      <button type="button" :class="btnGhost" :disabled="busy" @click="test">Verbindung testen</button>
      <span v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</span><span v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</span>
    </div>
    <div v-if="result" class="rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 p-3 text-sm space-y-1">
      <p class="text-green-700 dark:text-green-300">✓ Verbunden als <b>{{ result.account }}</b> ({{ result.role }}) – {{ result.projects.length }} Projekt(e) sichtbar:</p>
      <ul class="text-xs text-slate-600 dark:text-slate-300 list-disc pl-5"><li v-for="p in result.projects.slice(0, 12)" :key="p.id">{{ p.name }} <span class="text-slate-400">(ID {{ p.id }}, {{ p.access }})</span></li></ul>
      <p v-if="!result.projects.length" class="text-amber-600 dark:text-amber-400">Das Dienstkonto sieht noch kein Projekt – bitte in OpenPlan als Mitglied eintragen.</p>
    </div>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3'
const legend = 'px-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-400 mt-1'

const f = reactive({ enabled: false, base_url: '', link_url: '', token: '', clear_token: false, default_project_id: '', ca_pem: '', verify_tls: true, auto_sync: true, own_url: '', webhook_secret: '', clear_webhook_secret: false })
const meta = reactive({ token_set: false, webhook_secret_set: false, webhook_url: '', configured: false })
const busy = ref(false), msg = ref(''), err = ref(''), result = ref(null)

function fill(s) {
  const { token_set, webhook_secret_set, webhook_url, account, ...rest } = s
  Object.assign(f, rest, { token: '', webhook_secret: '', clear_token: false, clear_webhook_secret: false })
  Object.assign(meta, { token_set, webhook_secret_set, webhook_url, configured: !!(rest.base_url || rest.enabled) })
}
const payload = () => ({ ...f, token: f.token || undefined, webhook_secret: f.webhook_secret || undefined })
onMounted(async () => { try { fill(await api.openplanSettings()) } catch (e) { err.value = errText(e) } })

async function save() {
  busy.value = true; msg.value = err.value = ''
  try { fill(await api.saveOpenplanSettings(payload())); msg.value = 'Gespeichert' } catch (e) { err.value = errText(e) } finally { busy.value = false }
}
async function test() {
  busy.value = true; result.value = null; err.value = ''
  try { result.value = await api.testOpenplan() } catch (e) { err.value = errText(e) + ' (Einstellungen zuerst speichern)' } finally { busy.value = false }
}
</script>
