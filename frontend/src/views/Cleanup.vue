<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Aufräumen</h1>
      <div class="flex gap-2 items-center flex-wrap text-sm">
        <select v-model="siteId" :class="inp" class="!w-48 !py-1.5" @change="load">
          <option :value="null">alle Standorte</option>
          <option v-for="s in allSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option>
        </select>
        <label class="text-slate-500">alt ab</label>
        <select v-model.number="days" :class="inp" class="!w-28 !py-1.5" @change="load">
          <option v-for="d in [7, 14, 30, 60, 90]" :key="d" :value="d">{{ d }} Tagen</option>
        </select>
        <button v-if="admin" :class="btnGhost" class="!py-1.5" :disabled="busy" title="Den Wochenbericht jetzt an die globalen Administratoren senden" @click="mailNow">Bericht mailen</button>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Stellen im Bestand, die nachgepflegt oder bereinigt werden sollten. Globale Administratoren bekommen montags eine Zusammenfassung per E-Mail
      (abbestellbar unter „Mein Profil“).
    </p>
    <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>

    <div v-if="data" class="grid grid-cols-2 sm:grid-cols-5 gap-3">
      <a v-for="(title, k) in data.sections" :key="k" :href="`#${k}`" :class="card" class="p-3 hover:border-ks-400 transition-colors">
        <div class="text-2xl font-semibold tabular-nums" :class="data.counts[k] ? 'text-amber-600 dark:text-amber-400' : 'text-green-600 dark:text-green-400'">{{ data.counts[k] }}</div>
        <div class="text-xs text-slate-500 dark:text-slate-400">{{ title }}</div>
      </a>
    </div>

    <template v-if="data">
      <!-- vorläufige Kabel -->
      <section id="provisional" :class="card" class="p-4">
        <h2 :class="h2">Vorläufige Kabel <span class="text-slate-400 font-normal">({{ data.provisional.length }})</span></h2>
        <p :class="hint">Aus dem Soll/Ist-Abgleich als Direktkabel übernommen – Dosen und Patchfelder dazwischen fehlen ggf. noch.
          Im Strecken-Editor nachtragen und dort „Strecke vollständig“ wählen.</p>
        <p v-if="!data.provisional.length" :class="none">Keine vorläufigen Kabel.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Von</th><th :class="th">Nach</th><th :class="th">Übernommen</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="c in data.provisional" :key="c.cable_id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${c.a.device_id}`" :class="link">{{ c.a.text }}</router-link></td>
              <td :class="td" class="font-mono"><router-link :to="`/devices/${c.b.device_id}`" :class="link">{{ c.b.text }}</router-link></td>
              <td :class="td" class="whitespace-nowrap">
                <span :class="c.old ? 'text-amber-700 dark:text-amber-300 font-medium' : 'text-slate-600 dark:text-slate-300'">{{ ago(c.age_days) }}</span>
                <span v-if="c.created_by" class="text-slate-400"> · {{ c.created_by }}</span></td>
              <td :class="td" class="text-right"><button :class="btnLink" @click="strecke = c.port_id">Strecke</button></td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- von LLDP nicht gesehen -->
      <section id="not_seen" :class="card" class="p-4">
        <h2 :class="h2">Verbindungen, die LLDP nicht sieht <span class="text-slate-400 font-normal">({{ data.not_seen.length }})</span></h2>
        <p :class="hint">Dokumentiert, aber keines der beiden Geräte meldet den Nachbarn, obwohl beide LLDP/CDP-Daten liefern. Oft eine tote Patchung
          (abgezogen, Gerät ausgeschaltet) – vor Ort prüfen und ggf. per Auftrag trennen.</p>
        <p v-if="!data.not_seen.length" :class="none">Nichts gefunden.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Port</th><th :class="th">Dokumentiertes Gegenüber</th><th :class="th">LLDP-Stand</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="r in data.not_seen" :key="r.port_id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${r.device_id}`" :class="link">{{ r.device }}:{{ r.port }}</router-link></td>
              <td :class="td" class="font-mono">{{ r.soll }}<span v-if="r.via.length" class="text-xs text-slate-400"> über {{ r.via.join(', ') }}</span></td>
              <td :class="td" class="text-slate-500 whitespace-nowrap">{{ fmtTime(r.seen_at) }}</td>
              <td :class="td" class="text-right"><button :class="btnLink" @click="strecke = r.port_id">Strecke</button></td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- abgelaufene Reservierungen -->
      <section id="expired" :class="card" class="p-4">
        <div class="flex items-center justify-between gap-2">
          <h2 :class="h2">Abgelaufene Reservierungen <span class="text-slate-400 font-normal">({{ data.expired.length }})</span></h2>
          <button v-if="data.expired.length" :class="btnGhost" class="!py-1" :disabled="busy" @click="releaseExpired">alle löschen</button>
        </div>
        <p :class="hint">Blockieren nichts mehr, stehen aber noch in der Liste. Löschen dürfen Ersteller und Planer am Standort.</p>
        <p v-if="!data.expired.length" :class="none">Keine abgelaufenen Reservierungen.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Port</th><th :class="th">Zweck</th><th :class="th">Von</th><th :class="th">Bis</th></tr></thead>
          <tbody>
            <tr v-for="r in data.expired" :key="r.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${r.device_id}`" :class="link">{{ r.text }}</router-link></td>
              <td :class="td">{{ r.purpose }}</td>
              <td :class="td" class="text-slate-500">{{ r.reserved_by }}</td>
              <td :class="td" class="text-slate-500 whitespace-nowrap">{{ fmtDay(r.until) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- liegengebliebene Aufträge -->
      <section id="stale_orders" :class="card" class="p-4">
        <h2 :class="h2">Liegengebliebene Aufträge <span class="text-slate-400 font-normal">({{ data.stale_orders.length }})</span></h2>
        <p :class="hint">Offene Patchaufträge, die seit mindestens {{ data.days }} Tagen nicht geändert wurden. Sie halten ihre Ports als „verplant“ fest.</p>
        <p v-if="!data.stale_orders.length" :class="none">Keine.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Auftrag</th><th :class="th">Status</th><th :class="th">Angelegt von</th><th :class="th">Zuletzt geändert</th></tr></thead>
          <tbody>
            <tr v-for="w in data.stale_orders" :key="w.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td"><router-link :to="`/workorders/${w.id}`" :class="link">{{ w.number }}</router-link> {{ w.title }}</td>
              <td :class="td">{{ w.status_label }}</td>
              <td :class="td" class="text-slate-500">{{ w.created_by }}</td>
              <td :class="td" class="text-amber-700 dark:text-amber-300 whitespace-nowrap">{{ ago(w.age_days) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- geplante Geräte -->
      <section id="planned" :class="card" class="p-4">
        <h2 :class="h2">Geplante Geräte ohne Auftrag <span class="text-slate-400 font-normal">({{ data.planned.length }})</span></h2>
        <p :class="hint">Status „geplant“, aber kein offener Patchauftrag verwendet das Gerät. Entweder in Betrieb nehmen (Status „aktiv“) oder löschen.</p>
        <p v-if="!data.planned.length" :class="none">Keine.</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">Gerät</th><th :class="th">Typ</th><th :class="th">Ort</th></tr></thead>
          <tbody>
            <tr v-for="d in data.planned" :key="d.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${d.id}`" :class="link">{{ d.hostname }}</router-link></td>
              <td :class="td">{{ typeLabel(d.type) }}</td>
              <td :class="td" class="text-slate-500">{{ d.location || '–' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <PathEditor :open="!!strecke" :port-id="strecke" @close="strecke = null" @changed="load" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import PathEditor from '../components/PathEditor.vue'
import { api, errText, defaultSite, isAdmin } from '../api.js'
import { inp, card, th, td, btnLink, btnGhost, fmtTime, typeLabel } from '../ui.js'

/** Aufräumbericht: vorläufige Kabel, von LLDP nicht gesehene Verbindungen, abgelaufene Reservierungen, liegengebliebene Aufträge, geplante Geräte. */
const h2 = 'text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-500 dark:text-slate-400 mt-1 mb-2'
const none = 'text-sm text-green-600 dark:text-green-400'
const link = 'text-ks-600 dark:text-ks-400 hover:underline'

const data = ref(null), err = ref(''), msg = ref(''), busy = ref(false)
const siteId = ref(defaultSite()), days = ref(30), allSites = ref([]), strecke = ref(null)
const admin = isAdmin()

const ago = d => d == null ? '–' : d === 0 ? 'heute' : d === 1 ? 'vor 1 Tag' : `vor ${d} Tagen`
const fmtDay = s => s ? new Date(s + 'T00:00:00').toLocaleDateString('de-DE') : '–'

async function load() {
  err.value = ''
  try { data.value = await api.cleanup({ site_id: siteId.value || undefined, days: days.value }) } catch (e) { err.value = errText(e) }
}
async function releaseExpired() {
  if (!confirm(`${data.value.expired.length} abgelaufene Reservierung(en) löschen?`)) return
  busy.value = true; msg.value = ''
  try { await api.releaseReservations(data.value.expired.map(r => r.id)); msg.value = 'Abgelaufene Reservierungen gelöscht.'; await load() }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
async function mailNow() {
  busy.value = true; msg.value = ''; err.value = ''
  try { const r = await api.cleanupMail(); msg.value = `Bericht an ${r.recipients} Empfänger gesendet.` }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
onMounted(async () => { try { allSites.value = await api.sites() } catch {} ; load() })
</script>
