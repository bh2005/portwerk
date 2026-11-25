<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Aufräumen') }}</h1>
      <div class="flex gap-2 items-center flex-wrap text-sm">
        <select v-model="siteId" :class="inp" class="!w-48 !py-1.5" @change="load">
          <option :value="null">{{ $t('alle Standorte') }}</option>
          <option v-for="s in allSites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option>
        </select>
        <label class="text-slate-500">{{ $t('alt ab') }}</label>
        <select v-model.number="days" :class="inp" class="!w-28 !py-1.5" @change="load">
          <option v-for="d in [7, 14, 30, 60, 90]" :key="d" :value="d">{{ $t('{n} Tagen', { n: d }) }}</option>
        </select>
        <button v-if="admin" :class="btnGhost" class="!py-1.5" :disabled="busy" :title="$t('Den Wochenbericht jetzt an die globalen Administratoren senden')" @click="mailNow">{{ $t('Bericht mailen') }}</button>
      </div>
    </div>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      {{ $t('Stellen im Bestand, die nachgepflegt oder bereinigt werden sollten. Globale Administratoren bekommen montags eine Zusammenfassung per E-Mail (abbestellbar unter „Mein Profil“).') }}
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
        <h2 :class="h2">{{ $t('Vorläufige Kabel') + ' ' }}<span class="text-slate-400 font-normal">({{ data.provisional.length }})</span></h2>
        <p :class="hint">{{ $t('Aus dem Soll/Ist-Abgleich als Direktkabel übernommen – Dosen und Patchfelder dazwischen fehlen ggf. noch. Im Strecken-Editor nachtragen und dort „Strecke vollständig“ wählen.') }}</p>
        <p v-if="!data.provisional.length" :class="none">{{ $t('Keine vorläufigen Kabel.') }}</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Von') }}</th><th :class="th">{{ $t('Nach') }}</th><th :class="th">{{ $t('Übernommen') }}</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="c in data.provisional" :key="c.cable_id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${c.a.device_id}`" :class="link">{{ c.a.text }}</router-link></td>
              <td :class="td" class="font-mono"><router-link :to="`/devices/${c.b.device_id}`" :class="link">{{ c.b.text }}</router-link></td>
              <td :class="td" class="whitespace-nowrap">
                <span :class="c.old ? 'text-amber-700 dark:text-amber-300 font-medium' : 'text-slate-600 dark:text-slate-300'">{{ ago(c.age_days) }}</span>
                <span v-if="c.created_by" class="text-slate-400"> · {{ c.created_by }}</span></td>
              <td :class="td" class="text-right"><button :class="btnLink" @click="strecke = c.port_id">{{ $t('Strecke') }}</button></td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- von LLDP nicht gesehen -->
      <section id="not_seen" :class="card" class="p-4">
        <h2 :class="h2">{{ $t('Verbindungen, die LLDP nicht sieht') + ' ' }}<span class="text-slate-400 font-normal">({{ data.not_seen.length }})</span></h2>
        <p :class="hint">{{ $t('Dokumentiert, aber keines der beiden Geräte meldet den Nachbarn, obwohl beide LLDP/CDP-Daten liefern. Oft eine tote Patchung (abgezogen, Gerät ausgeschaltet) – vor Ort prüfen und ggf. per Auftrag trennen. „Fehlt seit“ zählt ab dem ersten Import ohne die Verbindung; ab {n} Tagen hervorgehoben, die ältesten zuerst.', { n: data.days }) }}</p>
        <p v-if="!data.not_seen.length" :class="none">{{ $t('Nichts gefunden.') }}</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Port') }}</th><th :class="th">{{ $t('Dokumentiertes Gegenüber') }}</th><th :class="th">{{ $t('Fehlt seit') }}</th><th :class="th"></th></tr></thead>
          <tbody>
            <tr v-for="r in data.not_seen" :key="r.port_id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono"><router-link :to="`/devices/${r.device_id}`" :class="link">{{ r.device }}:{{ r.port }}</router-link></td>
              <td :class="td" class="font-mono">{{ r.soll }}<span v-if="r.via.length" class="text-xs text-slate-400">{{ ' ' + $t('über') }} {{ r.via.join(', ') }}</span></td>
              <td :class="td" class="whitespace-nowrap">
                <span :class="r.old ? 'text-amber-700 dark:text-amber-300 font-medium' : 'text-slate-600 dark:text-slate-300'">{{ r.missing_since ? ago(r.age_days) : $t('unbekannt') }}</span>
                <span class="block text-xs text-slate-400">{{ r.last_ok ? `zuletzt gesehen ${fmtDate(r.last_ok)}` : $t('nie gesehen') }}</span></td>
              <td :class="td" class="text-right"><button :class="btnLink" @click="strecke = r.port_id">{{ $t('Strecke') }}</button></td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- abgelaufene Reservierungen -->
      <section id="expired" :class="card" class="p-4">
        <div class="flex items-center justify-between gap-2">
          <h2 :class="h2">{{ $t('Abgelaufene Reservierungen') + ' ' }}<span class="text-slate-400 font-normal">({{ data.expired.length }})</span></h2>
          <button v-if="data.expired.length" :class="btnGhost" class="!py-1" :disabled="busy" @click="releaseExpired">{{ $t('alle löschen') }}</button>
        </div>
        <p :class="hint">{{ $t('Blockieren nichts mehr, stehen aber noch in der Liste. Löschen dürfen Ersteller und Planer am Standort.') }}</p>
        <p v-if="!data.expired.length" :class="none">{{ $t('Keine abgelaufenen Reservierungen.') }}</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Port') }}</th><th :class="th">{{ $t('Zweck') }}</th><th :class="th">{{ $t('Von') }}</th><th :class="th">{{ $t('Bis') }}</th></tr></thead>
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
        <h2 :class="h2">{{ $t('Liegengebliebene Aufträge') + ' ' }}<span class="text-slate-400 font-normal">({{ data.stale_orders.length }})</span></h2>
        <p :class="hint">{{ $t('Offene Patchaufträge, die seit mindestens {n} Tagen nicht geändert wurden. Sie halten ihre Ports als „verplant“ fest.', { n: data.days }) }}</p>
        <p v-if="!data.stale_orders.length" :class="none">{{ $t('Keine.') }}</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Auftrag') }}</th><th :class="th">{{ $t('Status') }}</th><th :class="th">{{ $t('Angelegt von') }}</th><th :class="th">{{ $t('Zuletzt geändert') }}</th></tr></thead>
          <tbody>
            <tr v-for="w in data.stale_orders" :key="w.id" class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td"><router-link :to="`/workorders/${w.id}`" :class="link">{{ w.number }}</router-link> {{ w.title }}</td>
              <td :class="td">{{ $t(w.status_label) }}</td>
              <td :class="td" class="text-slate-500">{{ w.created_by }}</td>
              <td :class="td" class="text-amber-700 dark:text-amber-300 whitespace-nowrap">{{ ago(w.age_days) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- geplante Geräte -->
      <section id="planned" :class="card" class="p-4">
        <h2 :class="h2">{{ $t('Geplante Geräte ohne Auftrag') + ' ' }}<span class="text-slate-400 font-normal">({{ data.planned.length }})</span></h2>
        <p :class="hint">{{ $t('Status „geplant“, aber kein offener Patchauftrag verwendet das Gerät. Entweder in Betrieb nehmen (Status „aktiv“) oder löschen.') }}</p>
        <p v-if="!data.planned.length" :class="none">{{ $t('Keine.') }}</p>
        <table v-else class="w-full text-sm">
          <thead><tr><th :class="th">{{ $t('Gerät') }}</th><th :class="th">{{ $t('Typ') }}</th><th :class="th">{{ $t('Ort') }}</th></tr></thead>
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
import { t } from '../i18n.js'
import { onMounted, ref } from 'vue'
import PathEditor from '../components/PathEditor.vue'
import { api, errText, defaultSite, isAdmin } from '../api.js'
import { inp, card, th, td, btnLink, btnGhost, typeLabel } from '../ui.js'

/** Aufräumbericht: vorläufige Kabel, von LLDP nicht gesehene Verbindungen, abgelaufene Reservierungen, liegengebliebene Aufträge, geplante Geräte. */
const h2 = 'text-sm font-semibold text-slate-700 dark:text-slate-200'
const hint = 'text-xs text-slate-500 dark:text-slate-400 mt-1 mb-2'
const none = 'text-sm text-green-600 dark:text-green-400'
const link = 'text-ks-600 dark:text-ks-400 hover:underline'

const data = ref(null), err = ref(''), msg = ref(''), busy = ref(false)
const siteId = ref(defaultSite()), days = ref(30), allSites = ref([]), strecke = ref(null)
const admin = isAdmin()

const ago = d => d == null ? '–' : d === 0 ? 'heute' : d === 1 ? 'vor 1 Tag' : `vor ${d} Tagen`
const fmtDate = ts => new Date(ts * 1000).toLocaleDateString('de-DE')
const fmtDay = s => s ? new Date(s + 'T00:00:00').toLocaleDateString('de-DE') : '–'

async function load() {
  err.value = ''
  try { data.value = await api.cleanup({ site_id: siteId.value || undefined, days: days.value }) } catch (e) { err.value = errText(e) }
}
async function releaseExpired() {
  if (!confirm(t('{n} abgelaufene Reservierung(en) löschen?', { n: data.value.expired.length }))) return
  busy.value = true; msg.value = ''
  try { await api.releaseReservations(data.value.expired.map(r => r.id)); msg.value = t('Abgelaufene Reservierungen gelöscht.'); await load() }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
async function mailNow() {
  busy.value = true; msg.value = ''; err.value = ''
  try { const r = await api.cleanupMail(); msg.value = t('Bericht an {n} Empfänger gesendet.', { n: r.recipients }) }
  catch (e) { err.value = errText(e) } finally { busy.value = false }
}
onMounted(async () => { try { allSites.value = await api.sites() } catch {} ; load() })
</script>
