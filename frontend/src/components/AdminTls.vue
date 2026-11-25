<template>
  <div class="space-y-4">
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Portwerk holt sich sein Server-Zertifikat selbst per ACME (z. B. von einer internen step-ca) und erneuert es automatisch. Die CA prüft per HTTP-01.
    </p>

    <section :class="box" class="border-l-4" :style="{ borderLeftColor: levelColor }">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">Aktuelles Zertifikat</h3>
      <table v-if="cert" class="text-sm w-full">
        <tr v-for="[k, v] in rows" :key="k"><th class="text-left font-normal text-slate-400 w-36 py-0.5 align-top">{{ k }}</th><td class="py-0.5 break-all">{{ v }}</td></tr>
        <tr><th class="text-left font-normal text-slate-400 w-36 py-0.5">Gültig bis</th>
          <td class="py-0.5">{{ when(cert.not_after) }} <span class="ml-1 px-2 py-0.5 rounded-full text-[11px] text-white" :style="{ background: levelColor }">noch {{ cert.days_left }} Tage</span></td></tr>
        <tr><th class="text-left font-normal text-slate-400 w-36 py-0.5">HTTPS-Listener</th>
          <td class="py-0.5">{{ st?.serving ? $t('aktiv (lädt erneuerte Zertifikate automatisch)') : $t('nicht aktiv – Umgebungsvariable TLS_PORT im Container setzen') }}</td></tr>
      </table>
      <p v-else class="text-sm text-slate-400">Noch kein Zertifikat ausgestellt.</p>
      <p v-if="st?.running" class="text-sm mt-2">⏳ {{ st.message || $t('Anforderung läuft …') }}</p>
      <p v-else-if="st?.state?.ts" class="text-sm mt-2" :class="st.state.ok ? 'text-green-600' : 'text-red-500'">
        Letzter Lauf ({{ when(st.state.ts) }}, {{ st.state.trigger }}): {{ st.state.message }}</p>
      <div class="flex gap-2 mt-3 flex-wrap">
        <button :class="btnPrimary" :disabled="busy || st?.running" @click="issue">{{ cert ? $t('Jetzt erneuern') : $t('Zertifikat anfordern') }}</button>
        <button v-if="cert" :class="btnGhost" @click="download">Zertifikatskette herunterladen</button>
      </div>
    </section>

    <form @submit.prevent="save" class="space-y-4">
      <fieldset :class="box" class="space-y-3" @input="dirty = true" @change="dirty = true">
        <legend class="px-2 text-sm font-semibold text-slate-700 dark:text-slate-200">ACME-Einstellungen</legend>
        <div><label :class="lbl">ACME-Directory-URL</label><input v-model="f.directory_url" :class="inp" placeholder="https://ca.example.test/acme/acme/directory" /></div>
        <div><label :class="lbl">Domains (eine pro Zeile; die erste ist der Hauptname)</label>
          <textarea v-model="f.domains" rows="3" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="opp.example.test&#10;opp&#10;10.0.0.84" />
          <p :class="hint">Empfohlen: Kurzname, FQDN und IP-Adresse des Servers. Wildcards gehen mit HTTP-01 nicht.</p></div>
        <div><label :class="lbl">E-Mail für Ablaufwarnungen (optional)</label><input v-model="f.email" type="email" :class="inp" placeholder="it-ops@example.test" /></div>
        <div><label :class="lbl">CA-Kette der ACME-Schnittstelle (PEM: Root + Intermediate)</label>
          <textarea v-model="f.ca_pem" rows="4" :class="inp" class="font-mono text-xs" spellcheck="false" placeholder="-----BEGIN CERTIFICATE-----&#10;…&#10;-----END CERTIFICATE-----" />
          <p :class="hint">Nutzt die CA eine eigene (interne) PKI, ist die Kette <b>nötig</b>; sonst scheitert die Anmeldung mit „unable to get local issuer certificate“.</p></div>
        <div class="flex gap-3 items-end flex-wrap">
          <div class="flex-1 min-w-[220px]"><label :class="lbl">CA-Kette von URL laden</label><input v-model="caUrl" :class="inp" placeholder="http://ca.example.test/chain.pem" /></div>
          <button type="button" :class="btnGhost" @click="fetchCa">Laden</button>
        </div>
        <ul v-if="caInfo.length" class="text-xs space-y-1"><li v-for="c in caInfo" :key="c.fingerprint"><b>{{ c.subject }}</b><br /><span class="font-mono break-all text-slate-500">SHA-256 {{ c.fingerprint }}</span></li></ul>
        <p v-if="caInfo.length && caUrl.startsWith('http://')" class="text-xs text-amber-600 dark:text-amber-400">⚠ Per http:// geladen: Fingerabdrücke bitte gegen die bekannten Werte der CA prüfen, bevor du speicherst.</p>
        <div class="flex gap-5 items-center flex-wrap text-sm text-slate-600 dark:text-slate-300">
          <label class="flex items-center gap-2"><input type="checkbox" v-model="f.auto_renew" /> automatisch erneuern</label>
          <label class="flex items-center gap-2">erneuern ab <input v-model.number="f.renew_days" type="number" min="1" max="60" :class="inp" class="!w-20 !py-1" /> Tagen vor Ablauf</label>
        </div>
      </fieldset>
      <div class="flex items-center gap-3">
        <button :class="btnPrimary" :disabled="busy">Speichern</button>
        <span v-if="dirty" class="text-xs text-slate-400">ungespeicherte Änderungen</span>
        <span v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</span><span v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</span>
      </div>
    </form>

    <details class="text-sm text-slate-500 dark:text-slate-400">
      <summary class="cursor-pointer">Voraussetzungen im Betrieb</summary>
      <ul class="list-disc pl-5 mt-2 space-y-1">
        <li><b>HTTP-01:</b> Die CA ruft <code>http://&lt;Domain&gt;:80/.well-known/acme-challenge/…</code> ab. Port 80 der Domain muss zur App (Container-Port 8084) weitergeleitet werden, z. B. <code>80:8084</code> in der Compose-Datei oder per Reverse-Proxy.</li>
        <li><b>HTTPS:</b> Mit der Umgebungsvariable <code>TLS_PORT=8443</code> startet der Container zusätzlich einen HTTPS-Listener. Er lädt ein erneuertes Zertifikat innerhalb einer Minute ohne Neustart. Alternativ liegen Kette und Schlüssel in <code>data/tls/</code> für einen Reverse-Proxy.</li>
        <li>Der private Schlüssel verlässt den Server nie; heruntergeladen wird nur die öffentliche Kette.</li>
      </ul>
    </details>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, errText } from '../api.js'
import { inp, lbl, btnPrimary, btnGhost } from '../ui.js'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4'
const hint = 'text-xs text-slate-400 mt-1'

const st = ref(null)
const f = reactive({ directory_url: '', domains: '', email: '', ca_pem: '', auto_renew: true, renew_days: 30 })
const caUrl = ref(''), caInfo = ref([])
const dirty = ref(false), busy = ref(false), msg = ref(''), err = ref('')
let timer

function fill(s) {
  st.value = s
  if (!dirty.value) Object.assign(f, s.settings, { domains: s.settings.domains.join('\n') })
}
async function refresh() { try { fill(await api.tls()) } catch (e) { err.value = errText(e) } }
function schedule() { clearInterval(timer); timer = setInterval(async () => { await refresh(); if (!st.value?.running) clearInterval(timer) }, 2000) }
onMounted(async () => { await refresh(); if (st.value?.running) schedule() })
onBeforeUnmount(() => clearInterval(timer))

const payload = () => ({ ...f, domains: f.domains.split(/[\n,;\s]+/).map(s => s.trim()).filter(Boolean) })
async function save() {
  busy.value = true; msg.value = err.value = ''
  try { dirty.value = false; fill(await api.saveTls(payload())); msg.value = 'Gespeichert'; return true }
  catch (e) { dirty.value = true; err.value = errText(e); return false }
  finally { busy.value = false }
}
async function fetchCa() {
  err.value = ''
  try { const r = await api.fetchTlsCa(caUrl.value); f.ca_pem = r.pem; caInfo.value = r.certs; dirty.value = true }
  catch (e) { err.value = errText(e) }
}
async function issue() {
  if (dirty.value && !(await save())) return
  err.value = ''
  try { await api.issueTls(); await refresh(); schedule() } catch (e) { err.value = errText(e) }
}
async function download() {
  try {
    const blob = await api.tlsCert()
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'portwerk-fullchain.pem'; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { err.value = errText(e) }
}

const cert = computed(() => st.value?.cert ?? null)
const rows = computed(() => cert.value ? [['Domains', cert.value.san.join(', ')], ['Aussteller', cert.value.issuer], ['Fingerabdruck', cert.value.fingerprint]] : [])
const when = iso => (iso ? new Date(iso).toLocaleString('de-DE') : '')
const level = computed(() => (!cert.value ? 'none' : cert.value.days_left < 7 ? 'bad' : cert.value.days_left < f.renew_days ? 'warn' : 'ok'))
const levelColor = computed(() => ({ ok: '#16a34a', warn: '#d97706', bad: '#dc2626', none: '#94a3b8' }[level.value]))
</script>
