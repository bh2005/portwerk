<template>
  <form class="space-y-4" @submit.prevent="save">
    <p class="text-sm text-slate-500 dark:text-slate-400">Damit lassen sich Patchaufträge und Patchlisten per E-Mail senden und Benutzern zugewiesene Aufträge melden. Der Versand ist standardmäßig <b>aus</b>.
      <span v-if="!meta.configured">Noch nichts eingerichtet.</span></p>
    <label class="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.enabled" /> E-Mail-Versand aktivieren</label>

    <fieldset :class="box">
      <legend :class="legend">SMTP-Server</legend>
      <div class="grid sm:grid-cols-3 gap-3">
        <div class="sm:col-span-2"><label :class="lbl">Server</label><input v-model="f.host" :class="inp" placeholder="mail.example.test" /></div>
        <div><label :class="lbl">Port</label><input v-model.number="f.port" type="number" min="1" max="65535" :class="inp" /></div>
        <div><label :class="lbl">Verschlüsselung</label>
          <select v-model="f.security" :class="inp"><option value="none">keine (z. B. internes Relay, Port 25)</option><option value="starttls">STARTTLS (Port 587)</option><option value="ssl">SSL/TLS (Port 465)</option></select></div>
        <div><label :class="lbl">Benutzer (optional)</label><input v-model="f.username" :class="inp" autocomplete="off" /></div>
        <div><label :class="lbl">Passwort</label><input v-model="f.password" type="password" autocomplete="new-password" :class="inp" :placeholder="meta.password_set ? '●●●●●● gespeichert – leer lassen zum Beibehalten' : ''" />
          <label v-if="meta.password_set" class="flex items-center gap-2 text-xs text-slate-500 mt-1"><input type="checkbox" v-model="f.clear_password" /> gespeichertes Passwort entfernen</label></div>
      </div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Absender und Links</legend>
      <div class="grid sm:grid-cols-2 gap-3">
        <div><label :class="lbl">Absenderadresse</label><input v-model="f.from_addr" :class="inp" placeholder="opp@example.test" /></div>
        <div><label :class="lbl">Absendername</label><input v-model="f.from_name" :class="inp" /></div>
        <div><label :class="lbl">Antwortadresse (optional)</label><input v-model="f.reply_to" :class="inp" /></div>
        <div><label :class="lbl">Öffentliche URL der Anwendung</label><input v-model="f.public_url" :class="inp" placeholder="https://opp.example.test" />
          <p :class="hint">Wird für die Links in den E-Mails verwendet. Leer = keine Links.</p></div>
      </div>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Automatische Benachrichtigungen</legend>
      <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input type="checkbox" v-model="f.notify_confirm_suggest" />
        Freigeber informieren, wenn ein ausgeführter Auftrag zur Bestätigung vorgeschlagen wird (LLDP-Prüfung stimmt)</label>
      <p :class="hint">Empfänger: Benutzer mit der Rolle Freigeber (global oder am Standort des Auftrags) und E-Mail-Adresse, außer wer den Auftrag ausgeführt hat.
        Versand einmal je Auftrag, wenn die Prüfung auf „stimmt“ wechselt.</p>
    </fieldset>

    <fieldset :class="box">
      <legend :class="legend">Schutz</legend>
      <div><label :class="lbl">Erlaubte Empfänger-Domains (eine pro Zeile, leer = alle)</label>
        <textarea v-model="domains" rows="3" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="example.test&#10;corp.example"></textarea>
        <p :class="hint">Empfehlung: Nur eigene Domains freigeben, damit keine Auftragsdaten an fremde Adressen gehen. Außerdem gelten höchstens 20 Empfänger je Versand und 10 Versände je Benutzer in 10 Minuten; jeder Versand steht im Audit-Log.</p></div>
    </fieldset>

    <div class="flex items-center gap-3">
      <button :class="btnPrimary" :disabled="busy">Speichern</button>
      <span v-if="msg" class="text-sm text-green-600">{{ msg }}</span><span v-if="err" class="text-sm text-red-500">{{ err }}</span>
    </div>

    <fieldset :class="box">
      <legend :class="legend">Testnachricht</legend>
      <div class="flex gap-3 flex-wrap items-end">
        <input v-model="testTo" :class="inp" class="!w-72" placeholder="empfaenger@example.test" />
        <button type="button" :class="btnGhost" :disabled="busy || !testTo" @click="test">Senden</button>
        <span v-if="testMsg" class="text-sm" :class="testOk ? 'text-green-600' : 'text-red-500'">{{ testMsg }}</span>
      </div>
      <p :class="hint">Speichere die Einstellungen zuerst, der Test nutzt die gespeicherten Werte.</p>
    </fieldset>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3'
const legend = 'px-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-400 mt-1'

const f = reactive({ enabled: false, host: '', port: 25, security: 'none', username: '', password: '', clear_password: false, from_addr: '', from_name: 'Portwerk', reply_to: '', public_url: '', notify_confirm_suggest: true })
const domains = ref(''), meta = reactive({ password_set: false, configured: false })
const busy = ref(false), msg = ref(''), err = ref(''), testTo = ref(''), testMsg = ref(''), testOk = ref(false)

function fill(s) {
  const { password_set, allowed_domains, ...rest } = s
  Object.assign(f, rest, { password: '', clear_password: false })
  domains.value = (allowed_domains || []).join('\n')
  Object.assign(meta, { password_set, configured: !!(rest.host || rest.enabled) })
}
const payload = () => ({ ...f, password: f.password || undefined, allowed_domains: domains.value.split(/[\n,;\s]+/).map(x => x.trim()).filter(Boolean) })
onMounted(async () => { try { fill(await api.mailSettings()) } catch (e) { err.value = errText(e) } })

async function save() {
  busy.value = true; msg.value = err.value = ''
  try { fill(await api.saveMailSettings(payload())); msg.value = 'Gespeichert' } catch (e) { err.value = errText(e) } finally { busy.value = false }
}
async function test() {
  busy.value = true; testMsg.value = ''
  try { await api.testMail(testTo.value); testOk.value = true; testMsg.value = 'Testnachricht gesendet' } catch (e) { testOk.value = false; testMsg.value = errText(e) } finally { busy.value = false }
}
</script>
