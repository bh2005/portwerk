<template>
  <div class="max-w-5xl space-y-4">
    <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Import</h1>

    <div class="flex gap-1 border-b border-slate-200 dark:border-slate-700">
      <button v-for="t in tabs" :key="t[0]" @click="tab = t[0]"
        class="px-4 py-2 text-sm -mb-px border-b-2 transition-colors"
        :class="tab === t[0] ? 'border-ks-600 text-ks-700 dark:text-ks-300 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'">{{ t[1] }}</button>
    </div>

    <!-- Gemeinsame Optionen -->
    <div v-if="tab !== 'checkmk' && tab !== 'runs'" :class="card" class="p-4 flex flex-wrap gap-5 text-sm text-slate-600 dark:text-slate-300">
      <label class="flex items-center gap-2"><input type="checkbox" v-model="opts.atomic" class="rounded text-ks-600" /> Atomar (bei Fehler nichts speichern)
        <HelpHint text="Gibt es mindestens einen fehlerhaften Datensatz, wird gar nichts übernommen. So bleibt der Bestand konsistent." /></label>
      <label class="flex items-center gap-2"><input type="checkbox" v-model="opts.create_locations" class="rounded text-ks-600" /> Fehlende Locations anlegen
        <HelpHint text="Pfade wie SITE-A/Gebäude 1/Raum 2 werden bei Bedarf angelegt. Ohne Häkchen gilt ein unbekannter Pfad als Fehler." /></label>
    </div>

    <!-- CSV -->
    <div v-if="tab === 'csv'" :class="card" class="p-4 space-y-4">
      <div class="flex flex-wrap items-end gap-4">
        <div><label :class="lbl">Art</label>
          <select v-model="csv.kind" :class="inp" class="!w-40" @change="resetCsv"><option value="devices">Geräte</option><option value="ports">Ports</option></select></div>
        <div><label :class="lbl">CSV-Datei</label><input type="file" accept=".csv,.txt,text/csv" @change="pickCsv" class="text-sm" /></div>
        <div class="flex items-end">
          <a :href="`/api/import/template/${csv.kind}`" :download="`opp_template_${csv.kind}.csv`"
             class="text-xs px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700">
            ↓ Vorlage herunterladen
          </a>
        </div>
      </div>
      <template v-if="csv.preview">
        <p class="text-xs text-slate-400">{{ csv.preview.rows }} Zeilen erkannt. Ordne den Feldern Spalten zu:</p>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div v-for="fld in csv.preview.fields" :key="fld">
            <label :class="lbl">{{ fld }}<span v-if="csv.preview.required.includes(fld)" class="text-red-500 dark:text-red-400"> *</span></label>
            <select v-model="csv.mapping[fld]" :class="inp"><option value="">(nicht importieren)</option>
              <option v-for="h in csv.preview.headers" :key="h" :value="h">{{ h }}</option></select>
          </div>
        </div>
        <div class="overflow-x-auto"><table class="text-xs w-full">
          <thead><tr><th v-for="h in csv.preview.headers" :key="h" :class="th">{{ h }}</th></tr></thead>
          <tbody><tr v-for="(r, i) in csv.preview.sample" :key="i" class="border-t border-slate-100 dark:border-slate-700">
            <td v-for="h in csv.preview.headers" :key="h" :class="td">{{ r[h] }}</td></tr></tbody>
        </table></div>
        <div class="flex gap-2">
          <button :class="btnGhost" :disabled="busy" @click="runCsv(true)">Trockenlauf</button>
          <button :class="btnPrimary" :disabled="busy" @click="runCsv(false)">Importieren</button>
        </div>
      </template>
    </div>

    <!-- JSON -->
    <div v-if="tab === 'json'" :class="card" class="p-4 space-y-3">
      <div class="flex items-center gap-3">
        <input type="file" accept=".json,application/json" @change="pickJson" class="text-sm" />
        <button :class="btnLink" @click="jsonText = JSON.stringify(example, null, 2)">Beispiel einfügen</button>
      </div>
      <textarea v-model="jsonText" rows="12" :class="inp" class="font-mono text-xs" placeholder='{"devices": [ … ]}'></textarea>
      <div class="flex gap-2">
        <button :class="btnGhost" :disabled="busy || !jsonText" @click="runJson(true)">Trockenlauf</button>
        <button :class="btnPrimary" :disabled="busy || !jsonText" @click="runJson(false)">Importieren</button>
      </div>
    </div>

    <!-- Checkmk -->
    <div v-if="tab === 'checkmk'" :class="card" class="p-4 space-y-3 text-sm text-slate-600 dark:text-slate-300">
      <p>Der Checkmk-Import läuft über ein kleines Skript, das das HW/SW-Inventar der Hosts liest und an diese Anwendung sendet. Der Aufruf ist idempotent und kann regelmäßig laufen (z. B. per Cron).</p>
      <ol class="list-decimal pl-5 space-y-1">
        <li>Unter <b>Verwaltung → API-Zugänge</b> einen Zugang mit Schreibrecht (<code>write</code>) anlegen.</li>
        <li>Das Skript <code>tools/checkmk_export.py</code> auf einem Rechner mit Zugriff auf Checkmk und auf diese Anwendung ausführen.</li>
        <li>Zuerst mit <code>--dry-run</code> prüfen, danach ohne.</li>
      </ol>
      <pre class="bg-slate-100 dark:bg-slate-900 rounded p-3 text-xs overflow-x-auto">python3 checkmk_export.py --help</pre>
      <p>Das Ergebnis erscheint unter „Verlauf“. Details stehen im Handbuch.</p>
    </div>

    <!-- Verlauf -->
    <div v-if="tab === 'runs'" :class="card" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Zeit</th><th :class="th">Quelle</th><th :class="th">Durch</th><th :class="th">Art</th><th :class="th">Ergebnis</th></tr></thead>
        <tbody>
          <tr v-if="!runs.length"><td colspan="5" class="px-3 py-6 text-center text-slate-400">Noch keine Importe.</td></tr>
          <tr v-for="r in runs" :key="r.id" class="border-t border-slate-100 dark:border-slate-700">
            <td :class="td">{{ fmtTime(r.started_at) }}</td><td :class="td">{{ sourceLabel(r.source) }}</td><td :class="td">{{ r.actor || '–' }}</td>
            <td :class="td">{{ r.dry_run ? $t('Trockenlauf') : (r.stats.applied ? 'angewendet' : $t('nicht angewendet')) }}</td>
            <td :class="td" class="text-slate-500">{{ r.stats.created }} neu · {{ r.stats.updated }} geändert · {{ r.stats.unchanged }} gleich<span v-if="r.stats.errors" class="text-red-500 dark:text-red-400"> · {{ r.stats.errors }} Fehler</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <!-- Ergebnis -->
    <div v-if="result && tab !== 'runs'" :class="card" class="p-4 space-y-3">
      <div class="flex items-center gap-3 flex-wrap">
        <h2 class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ result.dry_run ? $t('Ergebnis des Trockenlaufs') : $t('Ergebnis') }}</h2>
        <span class="text-[11px] px-2 py-0.5 rounded-full" :class="result.applied ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'">
          {{ result.applied ? 'gespeichert' : $t('nichts gespeichert') }}</span>
        <span class="text-sm text-slate-500">{{ result.stats.created }} neu · {{ result.stats.updated }} geändert · {{ result.stats.unchanged }} gleich · {{ result.stats.errors }} Fehler</span>
      </div>
      <p v-if="!result.dry_run && !result.applied && result.stats.errors" class="text-sm text-amber-600 dark:text-amber-400">Wegen der Fehler wurde nichts gespeichert (atomar).</p>
      <div class="overflow-x-auto max-h-96 overflow-y-auto"><table class="w-full text-xs">
        <thead><tr><th :class="th">Zeile</th><th :class="th">Hostname</th><th :class="th">Ergebnis</th><th :class="th">Hinweis</th></tr></thead>
        <tbody><tr v-for="it in result.items" :key="it.row" class="border-t border-slate-100 dark:border-slate-700">
          <td :class="td">{{ it.row }}</td><td :class="td">{{ it.hostname }}</td>
          <td :class="td" :class2="''"><span :class="it.outcome === 'error' ? 'text-red-500' : ''">{{ outcomeLabel[it.outcome] || it.outcome }}</span></td>
          <td :class="td" class="text-slate-500">{{ it.message || (it.changes ? JSON.stringify(it.changes) : '') }}</td></tr></tbody>
      </table></div>
      <p v-if="result.truncated" class="text-xs text-slate-400">Die Liste ist gekürzt.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import HelpHint from '../components/HelpHint.vue'
import { helpContext } from '../content/helpContext.js'
import { api, errText } from '../api.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnLink, sourceLabel, fmtTime } from '../ui.js'

const tabs = [['csv', 'CSV'], ['json', 'JSON'], ['checkmk', 'Checkmk'], ['runs', 'Verlauf']]
const tab = ref('csv')
const opts = reactive({ atomic: true, create_locations: true })
const csv = reactive({ kind: 'devices', file: null, preview: null, mapping: {} })
const jsonText = ref(''), example = ref({})
const result = ref(null), error = ref(''), busy = ref(false), runs = ref([])
const outcomeLabel = { created: 'neu', updated: 'geändert', unchanged: 'gleich', error: 'Fehler' }

watch(tab, t => { helpContext.value = t === 'runs' ? '' : t; result.value = null; error.value = ''; if (t === 'runs') loadRuns() }, { immediate: true })

function resetCsv() { csv.file = null; csv.preview = null; csv.mapping = {}; result.value = null }

async function pickCsv(e) {
  const file = e.target.files[0]
  resetCsv()
  if (!file) return
  try {
    csv.file = file
    csv.preview = await api.csvPreview(file, csv.kind)
    csv.mapping = { ...csv.preview.suggested_mapping }
    error.value = ''
  } catch (err) { error.value = errText(err); csv.file = null }
}

async function runCsv(dry) {
  busy.value = true; error.value = ''
  try {
    const mapping = Object.fromEntries(Object.entries(csv.mapping).filter(([, v]) => v))
    result.value = await api.csvImport(csv.file, csv.kind, mapping, { ...opts, dry_run: dry })
  } catch (err) { error.value = errText(err) }
  finally { busy.value = false }
}

function pickJson(e) {
  const file = e.target.files[0]
  if (!file) return
  const r = new FileReader()
  r.onload = () => { jsonText.value = String(r.result) }
  r.readAsText(file)
}

async function runJson(dry) {
  busy.value = true; error.value = ''
  try {
    let body = JSON.parse(jsonText.value)
    if (Array.isArray(body)) body = { devices: body }
    result.value = await api.jsonImport({ ...body, ...opts, dry_run: dry })
  } catch (err) { error.value = err instanceof SyntaxError ? `Kein gültiges JSON: ${err.message}` : errText(err) }
  finally { busy.value = false }
}

async function loadRuns() { try { runs.value = await api.importRuns() } catch (e) { error.value = errText(e) } }

onMounted(async () => { try { example.value = (await api.importFields()).json_example } catch {} })
</script>
