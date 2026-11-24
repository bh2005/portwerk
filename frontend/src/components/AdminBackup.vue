<template>
  <div class="space-y-4">
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Eine Sicherung enthält die komplette Datenbank (Bestand, Aufträge, Historie, Benutzer, Einstellungen) und das Server-Zertifikat.
      Sie liegt im Datenverzeichnis unter <code>backups/</code>. Lade sie herunter und bewahre sie außerhalb des Servers auf.
      <b>Sie enthält Passwort-Hashes und Zugangsdaten</b> – vertraulich behandeln.
    </p>
    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
    <p v-if="msg" class="text-sm text-green-600">{{ msg }}</p>

    <section :class="box">
      <div class="flex items-center justify-between gap-3 flex-wrap mb-3">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Sicherungen auf dem Server</h3>
        <button :class="btnPrimary" :disabled="!!busy" @click="create">{{ busy === 'create' ? 'Sichere …' : 'Jetzt sichern' }}</button>
      </div>
      <p v-if="!items.length" class="text-sm text-slate-400">Noch keine Sicherung vorhanden.</p>
      <table v-else class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Zeitpunkt</th><th :class="th">Art</th><th :class="th">Von</th>
          <th :class="th">Größe</th><th :class="th">Version</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="b in items" :key="b.name" class="border-t border-slate-100 dark:border-slate-700">
            <td :class="td" class="whitespace-nowrap" :title="b.name">{{ fmtTime(b.created_at) }}</td>
            <td :class="td">{{ b.kind_label }}<span v-if="b.damaged" class="ml-1 text-red-500">(beschädigt)</span></td>
            <td :class="td" class="text-slate-500">{{ b.created_by || '–' }}</td>
            <td :class="td" class="whitespace-nowrap">{{ size(b.size) }}</td>
            <td :class="td" class="text-slate-500">{{ b.version || '–' }}</td>
            <td :class="td" class="text-right whitespace-nowrap">
              <button v-if="hasTargets && !b.damaged && b.kind !== 'before-restore'" :class="btnLink" :disabled="!!busy" title="Auf die aktiven externen Ziele übertragen" @click="push(b)">Extern ablegen</button>
              <button :class="btnLink" class="ml-3" @click="download(b)">Herunterladen</button>
              <button :class="btnLink" class="ml-3" :disabled="!!busy || b.damaged" @click="restore(b)">Wiederherstellen</button>
              <button :class="btnDanger" class="ml-3" :disabled="!!busy" @click="remove(b)">Löschen</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <form :class="box" class="space-y-3" @submit.prevent="saveSettings">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Automatische Sicherung</h3>
      <label class="flex items-center gap-2 text-sm"><input v-model="s.auto" type="checkbox" /> täglich automatisch sichern</label>
      <div class="grid grid-cols-2 gap-3 max-w-md">
        <div><label :class="lbl">ab Uhrzeit (Stunde)</label><input v-model.number="s.hour" type="number" min="0" max="23" :class="inp" :disabled="!s.auto" /></div>
        <div><label :class="lbl">aufbewahren (Anzahl)</label><input v-model.number="s.keep" type="number" min="1" max="365" :class="inp" :disabled="!s.auto" /></div>
      </div>
      <p :class="hint">Ältere automatische Sicherungen werden gelöscht; manuelle und die vor einer Wiederherstellung angelegten bleiben.</p>
      <button :class="btnPrimary" :disabled="!!busy">Speichern</button>
    </form>

    <BackupTargets @restored="relogin" @changed="l => hasTargets = l.some(t => t.enabled)" />

    <section :class="box" class="border-l-4 border-l-amber-500 space-y-3">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Aus Datei wiederherstellen</h3>
      <p class="text-sm text-slate-500 dark:text-slate-400">
        Ersetzt den <b>gesamten</b> aktuellen Bestand. Vorher wird automatisch eine Sicherung des jetzigen Stands angelegt
        („vor Wiederherstellung“). Danach müssen sich alle neu anmelden. Sicherungen aus einer neueren Portwerk-Version werden abgelehnt.
      </p>
      <div class="flex items-center gap-3 flex-wrap">
        <input ref="fileInput" type="file" accept=".zip,.db,.sqlite" class="text-sm" @change="file = $event.target.files[0] || null" />
        <button :class="btnGhost" :disabled="!file || !!busy" @click="restoreUpload">{{ busy === 'upload' ? 'Stelle wieder her …' : 'Wiederherstellen' }}</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText, clearToken } from '../api.js'
import { inp, lbl, th, td, btnPrimary, btnGhost, btnDanger, btnLink, fmtTime } from '../ui.js'
import BackupTargets from './BackupTargets.vue'

const box = 'border border-slate-200 dark:border-slate-700 rounded-xl p-4'
const hint = 'text-xs text-slate-400'
const items = ref([]), s = reactive({ auto: true, hour: 2, keep: 14 })
const busy = ref(''), err = ref(''), msg = ref(''), file = ref(null), fileInput = ref(null), hasTargets = ref(false)

const size = n => n >= 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`

async function load() {
  try { const r = await api.backups(); items.value = r.items; Object.assign(s, r.settings) } catch (e) { err.value = errText(e) }
}
async function run(kind, fn, okMsg) {
  busy.value = kind; err.value = ''; msg.value = ''
  try { await fn(); if (okMsg) msg.value = okMsg; await load() } catch (e) { err.value = errText(e) } finally { busy.value = '' }
}
const create = () => run('create', () => api.createBackup(), hasTargets.value ? 'Sicherung angelegt; die Übertragung auf die externen Ziele läuft im Hintergrund (Status siehe unten).' : 'Sicherung angelegt.')
async function push(b) {
  busy.value = 'push'; err.value = msg.value = ''
  try { const r = await api.pushBackup(b.name); msg.value = r.results.map(x => `${x.target}: ${x.ok ? '✓' : '✗ ' + x.error}`).join(' · ') } catch (e) { err.value = errText(e) } finally { busy.value = '' }
}
const saveSettings = () => run('settings', () => api.saveBackupSettings({ ...s }), 'Gespeichert.')
function remove(b) {
  if (confirm(`Sicherung vom ${fmtTime(b.created_at)} löschen?`)) run('delete', () => api.deleteBackup(b.name), 'Sicherung gelöscht.')
}
async function download(b) {
  try {
    const blob = await api.downloadBackup(b.name)
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = b.name; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { err.value = errText(e) }
}

function relogin(r) {
  alert(`Wiederhergestellt (${r.devices} Geräte${r.migrated.length ? `, ${r.migrated.length} Migrationen nachgezogen` : ''}).\n`
      + `Der vorherige Stand liegt als „${r.safety_backup}“ bereit.\n\nBitte neu anmelden.`)
  clearToken(); location.href = '/login'
}
const ASK = 'Den GESAMTEN aktuellen Bestand durch diese Sicherung ersetzen?\n\nDer jetzige Stand wird vorher automatisch gesichert. Danach müssen sich alle neu anmelden.'
async function restore(b) {
  if (!confirm(`Sicherung vom ${fmtTime(b.created_at)}:\n\n${ASK}`)) return
  busy.value = 'restore'; err.value = ''
  try { relogin(await api.restoreBackup(b.name)) } catch (e) { err.value = errText(e); busy.value = '' }
}
async function restoreUpload() {
  if (!file.value || !confirm(`Datei „${file.value.name}“:\n\n${ASK}`)) return
  busy.value = 'upload'; err.value = ''
  try { relogin(await api.restoreBackupUpload(file.value)) } catch (e) { err.value = errText(e); busy.value = '' }
}

onMounted(load)
</script>
